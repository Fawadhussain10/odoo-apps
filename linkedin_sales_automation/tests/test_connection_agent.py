from datetime import timedelta

from odoo import fields
from odoo.tests import freeze_time, tagged

from .common import LiTransactionCase
from ..models.li_mcp_tools import ToolError

# Monday 2026-10-12 10:00 UTC
MONDAY_10_UTC = '2026-10-12 10:00:00'


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestConnectionAgent(LiTransactionCase):

    def _persona(self, name='Founders', profile=None, tz='UTC', days=None, **vals):
        values = dict(con_send_window_from=0.0, con_send_window_to=24.0, con_delay_min=0, con_delay_max=0)
        values.update(vals)
        persona = self._make_persona(name, profile=profile, tz=tz, days=days, **values)
        persona.action_connection_run()
        return persona

    def _queue(self, persona, count, prefix='p'):
        Prospect = self.env['li.prospect']
        return Prospect.create([{
            'name': '%s %s' % (prefix.title(), i), 'persona_id': persona.id,
            'linkedin_url': 'https://www.linkedin.com/in/%s-%s-%s/' % (prefix, persona.id, i),
        } for i in range(count)])

    def _work(self, **kw):
        return self.work_all(**kw)['items']

    def _of_type(self, items, work_type):
        return [i for i in items if i['type'] == work_type]

    def _send(self, item, status='connected', text=None):
        go = self.call('li_confirm_send', work_id=item['work_id'], **({'text': text} if text else {}))
        self.assertTrue(go['go'], go)
        return self.call('li_report_result', work_id=item['work_id'], status=status,
                         linkedin_profile=item['linkedin_profile'], text_sent=text or '', note_sent=bool(text),
                         retry_safe=True)

    # ------------------------------------------------------------------
    def test_runs_as_technical_user(self):
        persona = self._persona()
        self._queue(persona, 1)
        items = self._work()
        item = self.env['li.work.item'].browse(items[0]['work_id'])
        self.assertEqual(item.create_uid, self.tech_user)

    @freeze_time(MONDAY_10_UTC)
    def test_daily_limit_never_exceeded(self):
        persona = self._persona(con_daily_limit=3)
        self._queue(persona, 10)
        released = []
        for _i in range(6):
            released += self._of_type(self._work(), 'invite')
        self.assertEqual(len(released), 3)
        for item in released:
            self._send(item)
        self.assertFalse(self._of_type(self._work(), 'invite'))
        self.assertEqual(self.env['li.event'].search_count([('persona_id', '=', persona.id),
                                                            ('event_type', '=', 'invite_sent')]), 3)
        # next day: quota is back
        with freeze_time('2026-10-13 10:00:00'):
            self.assertEqual(len(self._of_type(self._work(), 'invite')), 3)

    def test_expired_claims_return_quota(self):
        with freeze_time(MONDAY_10_UTC):
            persona = self._persona(con_daily_limit=2)
            self._queue(persona, 5)
            first = self._of_type(self._work(), 'invite')
            self.assertEqual(len(first), 2)
            self.assertFalse(self._of_type(self._work(), 'invite'))
        with freeze_time('2026-10-12 10:16:00'):
            again = self._of_type(self._work(), 'invite')
            self.assertEqual(len(again), 2)
            expired = self.env['li.work.item'].browse([i['work_id'] for i in first])
            self.assertEqual(set(expired.mapped('state')), {'expired'})
            self.assertFalse(any(expired.mapped('quota_consumed')))
            # a report for an expired, never-confirmed item is refused
            with self.assertRaisesRegex(ToolError, 'never confirmed'):
                self.call('li_report_result', work_id=first[0]['work_id'], status='connected',
                          linkedin_profile='taha')

    @freeze_time(MONDAY_10_UTC)
    def test_weekly_limit(self):
        persona = self._persona(con_daily_limit=10, con_weekly_limit=4)
        self._queue(persona, 10)
        self.assertEqual(len(self._of_type(self._work(), 'invite')), 4)

    def test_time_zones_uae_and_usa_on_one_profile(self):
        uae = self._persona('UAE founders', tz='Asia/Dubai', days=self.sun_thu,
                            con_send_window_from=10.0, con_send_window_to=17.0)
        usa = self._persona('USA founders', tz='America/New_York', days=self.mon_fri,
                            con_send_window_from=10.0, con_send_window_to=17.0)
        self._queue(uae, 3, 'uae')
        self._queue(usa, 3, 'usa')

        def personas_with_work():
            items = self._of_type(self._work(), 'invite')
            names = {i['persona']['name'] for i in items}
            self.env['li.work.item'].search([('state', '=', 'released')])._close('cancelled')
            return names

        # Sunday 07:00 UTC = 11:00 Dubai (Sunday is a working day there), 03:00 New York (Sunday)
        with freeze_time('2026-10-11 07:00:00'):
            self.assertEqual(personas_with_work(), {'UAE founders'})
        # Monday 15:00 UTC = 19:00 Dubai (after its window), 11:00 New York
        with freeze_time('2026-10-12 15:00:00'):
            self.assertEqual(personas_with_work(), {'USA founders'})
        # Monday 13:30 UTC = 17:30 Dubai (closed), 09:30 New York (not open yet)
        with freeze_time('2026-10-12 13:30:00'):
            self.assertEqual(personas_with_work(), set())
        # Friday 08:00 UTC = 12:00 Dubai (Friday off), 04:00 New York
        with freeze_time('2026-10-16 08:00:00'):
            self.assertEqual(personas_with_work(), set())
        # Thursday 08:00 UTC = 12:00 Dubai, Thursday 14:30 UTC = 10:30 New York
        with freeze_time('2026-10-15 08:00:00'):
            self.assertEqual(personas_with_work(), {'UAE founders'})
        with freeze_time('2026-10-15 14:30:00'):
            self.assertEqual(personas_with_work(), {'USA founders'})

    def test_confirm_checks_window_at_call_time(self):
        with freeze_time('2026-10-12 16:59:00'):
            persona = self._persona(con_send_window_from=10.0, con_send_window_to=17.0)
            self._queue(persona, 1)
            item = self._of_type(self._work(), 'invite')[0]
        with freeze_time('2026-10-12 17:01:00'):
            answer = self.call('li_confirm_send', work_id=item['work_id'])
            self.assertFalse(answer['go'])
            self.assertIn('send window', answer['reason'])

    @freeze_time(MONDAY_10_UTC)
    def test_throughput_and_delay_gap(self):
        persona = self._persona(con_daily_limit=20, con_delay_min=60, con_delay_max=60)
        self._queue(persona, 10)
        items = self._of_type(self._work(), 'invite')
        self.assertEqual(len(items), 5, 'max_sends_per_account defaults to 5')
        # still 5 claimed: no more sends for that account until some are reported
        self.assertFalse(self._of_type(self._work(), 'invite'))
        self.assertTrue(self.call('li_confirm_send', work_id=items[0]['work_id'])['go'])
        self.call('li_report_result', work_id=items[0]['work_id'], status='connected',
                  linkedin_profile='taha', retry_safe=True)
        wait = self.call('li_confirm_send', work_id=items[1]['work_id'])
        self.assertFalse(wait['go'])
        self.assertEqual(wait['reason'], 'wait')
        self.assertTrue(0 < wait['wait_seconds'] <= 61)
        second = self.env['li.work.item'].browse(items[1]['work_id'])
        self.assertEqual(second.state, 'released', 'a waiting item stays claimed')
        self.assertTrue(second.quota_consumed)
        with freeze_time('2026-10-12 10:01:05'):
            self.assertTrue(self.call('li_confirm_send', work_id=items[1]['work_id'])['go'])
            self.call('li_report_result', work_id=items[1]['work_id'], status='connected',
                      linkedin_profile='taha', retry_safe=True)
            result = self.call('li_finish_run', summary='test run')
            self.assertEqual(result['released_sends'], 3)
            rest = self.env['li.work.item'].browse([i['work_id'] for i in items[2:]])
            self.assertEqual(set(rest.mapped('state')), {'cancelled'})
            self.assertFalse(any(rest.mapped('quota_consumed')))
            self.assertEqual(self.env['li.work.item'].sudo()._quota_used_today(persona, 'connection'), 2)
            taha = [a for a in result['accounts'] if a['linkedin_profile'] == 'taha'][0]
            self.assertEqual(taha['invites'], 2)

    @freeze_time(MONDAY_10_UTC)
    def test_note_text_rules(self):
        persona = self._persona(con_send_note=True, con_note_instructions='Mention their brand.')
        self._queue(persona, 1)
        item = self._of_type(self._work(), 'invite')[0]
        self.assertTrue(item['send_note'])
        answer = self.call('li_confirm_send', work_id=item['work_id'])
        self.assertFalse(answer['go'])
        self.assertIn('text is required', answer['reason'])
        answer = self.call('li_confirm_send', work_id=item['work_id'], text='x' * 201)
        self.assertIn('201 characters', answer['reason'])
        answer = self.call('li_confirm_send', work_id=item['work_id'], text='Hi {first_name}, love your brand')
        self.assertIn('{first_name}', answer['reason'])
        self.assertEqual(self.env['li.work.item'].browse(item['work_id']).state, 'released')
        note = 'Hi Ali, love what Brand X does with Shopify. Would be glad to connect.'
        self._send(item, text=note)
        prospect = self.env['li.prospect'].browse(item['prospect']['id'])
        self.assertEqual(prospect.stage, 'invited')
        self.assertEqual(prospect.message_ids_li.body, note)

    @freeze_time(MONDAY_10_UTC)
    def test_note_limit_rereleases_without_note(self):
        persona = self._persona(con_send_note=True, con_note_instructions='Short note.')
        self._queue(persona, 1)
        item = self._of_type(self._work(), 'invite')[0]
        self.call('li_confirm_send', work_id=item['work_id'], text='Hello, glad to connect.')
        self.call('li_report_result', work_id=item['work_id'], status='custom_note_limit_reached',
                  linkedin_profile='taha', retry_safe=True)
        again = self._of_type(self._work(), 'invite')
        self.assertEqual(len(again), 1)
        self.assertFalse(again[0]['send_note'])
        answer = self.call('li_confirm_send', work_id=again[0]['work_id'], text='a note')
        self.assertIn('without a note', answer['reason'])

    @freeze_time(MONDAY_10_UTC)
    def test_wrong_connector_refused(self):
        persona = self._persona()
        self._queue(persona, 1)
        item = self._of_type(self._work(), 'invite')[0]
        self.call('li_confirm_send', work_id=item['work_id'])
        with self.assertRaisesRegex(ToolError, 'Wrong LinkedIn profile'):
            self.call('li_report_result', work_id=item['work_id'], status='connected',
                      linkedin_profile='rep1', retry_safe=True)
        prospect = self.env['li.prospect'].browse(item['prospect']['id'])
        self.assertEqual(prospect.stage, 'queued')
        self.assertEqual(self.env['li.work.item'].browse(item['work_id']).state, 'released')

    @freeze_time(MONDAY_10_UTC)
    def test_takeover_after_release(self):
        persona = self._persona()
        prospects = self._queue(persona, 3)
        items = self._of_type(self._work(), 'invite')
        self.assertEqual(len(items), 3)
        taken = self.env['li.prospect'].browse(items[0]['prospect']['id'])
        taken.with_user(self.rep).action_take_over()
        answer = self.call('li_confirm_send', work_id=items[0]['work_id'])
        self.assertFalse(answer['go'])
        self.assertIn('taken over', answer['reason'])
        for other in items[1:]:
            self.assertTrue(self.call('li_confirm_send', work_id=other['work_id'])['go'])
        self.assertTrue(self.env['li.event'].search_count([('prospect_id', '=', taken.id),
                                                           ('event_type', '=', 'taken_over')]))
        self.assertEqual(len(prospects), 3)

    @freeze_time(MONDAY_10_UTC)
    def test_search_and_add_prospects(self):
        persona = self._persona(con_daily_limit=5, exclude_keywords='recruiter')
        other = self._persona('Other persona', profile=self.profile2)
        self._queue(other, 1, 'shared')
        dnc = self._queue(other, 1, 'dnc')
        dnc.stage = 'do_not_contact'
        items = self._work(linkedin_profile='taha')
        search = self._of_type(items, 'search_prospects')
        self.assertEqual(len(search), 1)
        self.assertIn('Founder', search[0]['keywords'])
        result = self.call('li_add_prospects', work_id=search[0]['work_id'], people=[
            {'name': 'Ali Raza', 'headline': 'Founder, Brand X', 'linkedin_url': 'https://www.linkedin.com/in/ali-raza/'},
            {'name': 'Ali Raza', 'linkedin_url': 'https://www.linkedin.com/in/ali-raza?trk=x'},
            {'name': 'Sara Khan', 'username': 'sara-khan'},
            {'name': 'Rec Ruiter', 'headline': 'Recruiter at Talent', 'username': 'rec'},
            {'name': 'Shared', 'linkedin_url': 'https://www.linkedin.com/in/shared-%s-0/' % other.id},
            {'name': 'Blocked', 'username': 'dnc-%s-0' % other.id},
            {'name': 'No url'},
        ])
        self.assertEqual((result['created'], result['duplicates'], result['excluded'], result['contacted_elsewhere'],
                          result['do_not_contact'], result['invalid']), (2, 1, 1, 1, 1, 1))
        queued = self.env['li.prospect'].search([('persona_id', '=', persona.id)])
        self.assertEqual(set(queued.mapped('linkedin_username')), {'ali-raza', 'sara-khan'})
        # no second search while the cooldown runs
        self.assertFalse(self._of_type(self._work(linkedin_profile='taha'), 'search_prospects'))

    @freeze_time(MONDAY_10_UTC)
    def test_acceptance_cycle_and_withdraw(self):
        persona = self._persona(con_stop_tracking_after_days=21)
        persona.chat_agent_id.first_message_delay = 4
        self._queue(persona, 3)
        for item in self._of_type(self._work(), 'invite'):
            self._send(item)
        check = self._of_type(self._work(), 'check_acceptance')
        self.assertEqual(len(check), 1)
        ids = [p['id'] for p in check[0]['pending_invites']]
        self.assertEqual(len(ids), 3)
        result = self.call('li_mark_accepted', work_id=check[0]['work_id'], accepted=[ids[0], 999999])
        self.assertEqual(result['accepted'], [ids[0]])
        self.assertEqual(result['ignored'], [999999])
        accepted = self.env['li.prospect'].browse(ids[0])
        self.assertEqual(accepted.stage, 'accepted')
        self.assertEqual(accepted.next_message_date, accepted.date_accepted + timedelta(hours=4))
        # the next check waits 6 hours
        self.assertFalse(self._of_type(self._work(), 'check_acceptance'))
        with freeze_time('2026-11-03 10:00:00'):
            self.env['li.mcp.tools']._cron_withdraw_old_invites()
        self.assertEqual(set(self.env['li.prospect'].browse(ids[1:]).mapped('stage')), {'withdrawn'})
        self.assertEqual(accepted.stage, 'accepted')

    @freeze_time(MONDAY_10_UTC)
    def test_unknown_outcome_is_never_retried(self):
        persona = self._persona()
        self._queue(persona, 1)
        item = self._of_type(self._work(), 'invite')[0]
        self.call('li_confirm_send', work_id=item['work_id'])
        self.call('li_report_result', work_id=item['work_id'], status='failed', retry_safe=False,
                  linkedin_profile='taha', error='timeout')
        prospect = self.env['li.prospect'].browse(item['prospect']['id'])
        self.assertTrue(prospect.needs_check)
        self.assertTrue(self.env['li.work.item'].browse(item['work_id']).quota_consumed)
        self.assertFalse(self._of_type(self._work(), 'invite'))

    @freeze_time(MONDAY_10_UTC)
    def test_three_errors_pause_the_agent(self):
        persona = self._persona()
        self._queue(persona, 4)
        for _i in range(3):
            item = self._of_type(self._work(), 'invite')[0]
            self.call('li_report_result', work_id=item['work_id'], status='failed', retry_safe=True,
                      linkedin_profile='taha', error='button not found')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual(persona.state, 'paused')
        self.assertTrue(persona.activity_ids)

    @freeze_time(MONDAY_10_UTC)
    def test_session_expired_pauses_profile_agents(self):
        persona = self._persona()
        other = self._persona('Rep persona', profile=self.profile2)
        self._queue(persona, 2)
        self._queue(other, 1)
        items = self._work()
        result = self.call('li_report_error', linkedin_profile='taha', error='Login required',
                           session_expired=True)
        self.assertEqual(result['profile_state'], 'reconnect_needed')
        self.assertEqual(self.profile.connection_state, 'reconnect_needed')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual(other.connection_agent_id.state, 'running')
        taha_items = self.env['li.work.item'].browse([i['work_id'] for i in items
                                                      if i['linkedin_profile'] == 'taha'])
        self.assertEqual(set(taha_items.mapped('state')), {'cancelled'})
        self.assertTrue(self.profile.activity_ids)
        # Claude in Chrome: only the account check comes back until Chrome is signed in again
        self.assertEqual([i['type'] for i in self._work() if i['linkedin_profile'] == 'taha'], ['verify_account'])

    @freeze_time(MONDAY_10_UTC)
    def test_total_target_stops_agent(self):
        persona = self._persona(con_total_target=2)
        self._queue(persona, 5)
        items = self._of_type(self._work(), 'invite')
        self.assertEqual(len(items), 2)
        for item in items:
            self._send(item)
        self.assertEqual(persona.connection_agent_id.state, 'stopped')

    def test_stop_clears_queue(self):
        persona = self._persona()
        self._queue(persona, 3)
        items = self._of_type(self._work(), 'invite')
        persona.action_connection_stop()
        self.assertFalse(self.env['li.prospect'].search([('persona_id', '=', persona.id)]))
        self.assertEqual(set(self.env['li.work.item'].browse([i['work_id'] for i in items]).mapped('state')),
                         {'cancelled'})

    @freeze_time(MONDAY_10_UTC)
    def test_take_over_tool(self):
        persona = self._persona()
        prospect = self._queue(persona, 1, 'ali')
        prospect.name = 'Ali Raza'
        result = self.call('li_take_over', name='Ali Raza')
        self.assertTrue(prospect.is_taken_over)
        self.assertEqual(result['taken_over'][0]['id'], prospect.id)

    @freeze_time(MONDAY_10_UTC)
    def test_summaries_are_plain_text(self):
        persona = self._persona(con_daily_limit=5)
        self._queue(persona, 2)
        tools = self.env['li.mcp.tools']

        def check(name, result):
            text = tools._summarize(name, result)
            self.assertTrue(text and len(text) <= 400, text)
            self.assertNotIn('{', text, '%s summary must not be JSON: %s' % (name, text))
            self.assertNotIn('"work_id"', text)
            return text

        text = check('li_overview', self.call('li_overview'))
        self.assertRegex(text, r'^2 profiles, 1 personas \(1 active\)\. Today: 0/5 invites, 0/40 messages')
        work = self.work_all()
        self.assertIn('work item(s)', check('li_get_work', work))
        invites = self._of_type(work['items'], 'invite')
        self.assertEqual(check('li_confirm_send', self.call('li_confirm_send', work_id=invites[0]['work_id'])), 'go')
        check('li_report_result', self.call('li_report_result', work_id=invites[0]['work_id'], status='connected',
                                            linkedin_profile='taha', retry_safe=True))
        check('li_take_over', self.call('li_take_over', prospect_id=invites[1]['prospect']['id']))
        check('li_report_error', self.call('li_report_error', linkedin_profile='taha', error='x'))
        self.assertIn('Run recorded', check('li_finish_run', self.call('li_finish_run')))
        empty = {'items': [], 'count': 0, 'reasons': ['Founders: Connection Agent daily limit (5) reached']}
        self.assertEqual(check('li_get_work', empty), 'No work allowed right now; call li_finish_run. '
                                                      'Founders: Connection Agent daily limit (5) reached.')
        self.assertIn('1/5 invites', check('li_overview', self.call('li_overview')))
