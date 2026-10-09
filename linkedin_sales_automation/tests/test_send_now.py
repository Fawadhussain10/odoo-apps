from datetime import datetime

from odoo.tests import freeze_time, tagged

from .test_background import MONDAY_10_UTC, BackgroundCase
from ..models.li_mcp_tools import ToolError


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestSendNow(BackgroundCase):
    """"Send connections now" asked in Claude: Odoo checks the personas and the engine sends."""

    def _engine_on(self):
        """Planning needs no engine process, only an engine that should run."""
        self.profile.sudo().engine_wanted = True

    def _triggers(self):
        cron = self.env.ref('linkedin_sales_automation.cron_background_work')
        return self.env['ir.cron.trigger'].sudo().search([('cron_id', '=', cron.id)])

    @freeze_time(MONDAY_10_UTC)
    def test_send_now_starts_the_engine_and_respects_the_limit(self):
        self._start()
        persona = self._persona(con_daily_limit=2)
        for i in range(3):
            self._prospect(persona, 'p%s' % i, 'Person %s' % i)
        before = len(self._triggers())
        result = self.call('li_send_now', linkedin_profile='taha')
        self.assertTrue(result['started'])
        plan = result['personas'][0]
        self.assertEqual((plan['left_today'], plan['queued_prospects'], plan['ready_to_send']), (2, 3, 3))
        self.assertIn('sending up to 2 invite(s)', plan['status'])
        self.assertEqual(len(self._triggers()), before + 1)        # runs at once, not at the next interval
        for _i in range(4):
            self._run()
            self.profile.last_send_at = False                       # the delay gap is tested elsewhere
        self.assertEqual(len(self._calls(tool='connect_with_person')), 2)   # never above the daily limit
        status = self.call('li_sending_status', linkedin_profile='taha')
        sent = status['personas'][0]['invites_today']
        self.assertEqual(len(sent), 2)
        self.assertEqual({s['name'] for s in sent} <= {'Person 0', 'Person 1', 'Person 2'}, True)
        self.assertEqual(status['personas'][0]['left_today'], 0)
        again = self.call('li_send_now', linkedin_profile='taha')
        self.assertFalse(again['started'])
        self.assertIn('daily limit reached', again['message'])

    @freeze_time(MONDAY_10_UTC)
    def test_notes_are_written_first(self):
        self._engine_on()
        persona = self._persona(con_send_note=True, con_note_instructions='Short.')
        self._prospect(persona)
        result = self.call('li_send_now', linkedin_profile='taha')
        self.assertFalse(result['started'])
        self.assertIn('waiting for notes', result['message'])
        note = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'invite_note'][0]
        self.call('li_submit_text', work_id=note['work_id'], text='Hi Ali, great to connect.')
        result = self.call('li_send_now', linkedin_profile='taha')
        self.assertTrue(result['started'])
        self.assertEqual(result['personas'][0]['ready_to_send'], 1)

    @freeze_time('2026-10-12 20:00:00')          # Monday 20:00 UTC, window 10:00-17:00
    def test_outside_the_window(self):
        self._engine_on()
        persona = self._persona(con_send_window_from=10.0, con_send_window_to=17.0)
        self._prospect(persona)
        result = self.call('li_send_now', linkedin_profile='taha')
        self.assertFalse(result['started'])
        self.assertIn('next window Tue 13 Oct 10:00 UTC', result['message'])

    @freeze_time(MONDAY_10_UTC)
    def test_stopped_agent_starts_only_when_asked(self):
        self._engine_on()
        persona = self._persona(run=())
        self._prospect(persona)
        result = self.call('li_send_now', linkedin_profile='taha')
        self.assertFalse(result['started'])
        self.assertIn('not started', result['message'])
        self.assertEqual(persona.connection_agent_id.state, 'stopped')
        result = self.call('li_send_now', linkedin_profile='taha', start_agents=True)
        self.assertTrue(result['started'])
        self.assertEqual(persona.connection_agent_id.state, 'running')

    @freeze_time(MONDAY_10_UTC)
    def test_weekly_pause_is_not_overridden(self):
        self._engine_on()
        persona = self._persona()
        self._prospect(persona)
        persona.connection_agent_id._pause_until(datetime(2026, 10, 19), 'weekly invitation limit')
        result = self.call('li_send_now', linkedin_profile='taha', start_agents=True)
        self.assertFalse(result['started'])
        self.assertIn('paused until', result['message'])
        self.assertEqual(persona.connection_agent_id.state, 'paused')

    def test_profile_checks(self):
        self._engine_on()
        persona = self._persona()
        with self.assertRaisesRegex(ToolError, 'No persona "nobody"'):
            self.call('li_send_now', linkedin_profile='taha', persona='nobody')
        self.profile.connection_state = 'reconnect_needed'
        result = self.call('li_send_now', linkedin_profile='taha')
        self.assertFalse(result['started'])
        self.assertIn('Reconnect LinkedIn', result['message'])
        self.profile.write({'connection_state': 'connected', 'execution_mode': 'chrome'})
        with self.assertRaisesRegex(ToolError, 'Claude in Chrome'):
            self.call('li_send_now', linkedin_profile='taha')
        self.assertTrue(persona)

    @freeze_time(MONDAY_10_UTC)
    def test_send_now_keeps_going_at_the_delay_gap(self):
        """Live test: "planned 5, sent 1". The engine must come back when the gap ends, and the
        status must say it is still sending."""
        self._start()
        persona = self._persona(con_delay_min=60, con_delay_max=60, con_daily_limit=3)
        for i in range(4):
            self._prospect(persona, 'p%s' % i, 'Person %s' % i)
        result = self.call('li_send_now', linkedin_profile='taha')
        self.assertIn('one every 60–60 s', result['message'])
        self.assertIn('Fewer sent right away is normal', result['message'])
        self._run()                                                      # first invite, gap 60 s starts
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)
        self.assertEqual(self.profile.send_gap_seconds, 60)
        triggers = self._triggers().filtered(lambda t: t.call_at >= datetime(2026, 10, 12, 10, 1, 0))
        self.assertTrue(triggers)
        self.assertEqual(min(triggers.mapped('call_at')), datetime(2026, 10, 12, 10, 1, 5))
        status = self.call('li_sending_status', linkedin_profile='taha')
        self.assertTrue(status['sending_in_progress'])
        self.assertIn('still sending, next one around 10:01 UTC', status['message'])
        with freeze_time('2026-10-12 10:00:40'):                         # too early: nothing, comes back later
            self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)
        with freeze_time('2026-10-12 10:01:05'):
            self._run()
        with freeze_time('2026-10-12 10:02:10'):
            self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 3)   # the daily limit of 3
        with freeze_time('2026-10-12 10:03:30'):
            before = len(self._triggers())
            self._run()
            status = self.call('li_sending_status', linkedin_profile='taha')
        self.assertEqual(len(self._triggers()), before)                  # limit reached: no more quick runs
        self.assertFalse(status['sending_in_progress'])
        self.assertIn('nothing more goes out now', status['message'])

    @freeze_time(MONDAY_10_UTC)
    def test_status_lists_what_was_not_sent(self):
        """Live test: "7 sent but 6 listed, 1 error" — the status names the failed send."""
        self._start()
        persona = self._persona()
        self._prospect(persona, 'p0', 'Person Zero')
        self._script(connect_with_person=[{'data': {'status': 'outcome_unknown', 'retry_safe': False}}])
        self._run()
        status = self.call('li_sending_status', linkedin_profile='taha')
        failed = status['personas'][0]['not_sent_today']
        self.assertEqual((failed[0]['name'], failed[0]['status'], failed[0]['flagged_for_check']),
                         ('Person Zero', 'unknown', True))
        self.assertIn('1 not sent (Person Zero: unknown', status['message'])

    @freeze_time('2026-10-12 16:59:30')
    def test_status_never_promises_a_send_after_the_window(self):
        """Live test: "next invite around 17:12" with a 10:00-17:00 window."""
        self._start()
        persona = self._persona(con_send_window_from=10.0, con_send_window_to=17.0, con_delay_min=90,
                                con_delay_max=90)
        for i in range(3):
            self._prospect(persona, 'p%s' % i, 'Person %s' % i)
        self._run()                                                   # one invite at 16:59:30, gap 90 s
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)
        status = self.call('li_sending_status', linkedin_profile='taha')
        self.assertFalse(status['sending_in_progress'])
        self.assertIn('next send window Tue 13 Oct 10:00 UTC', status['message'])
        with freeze_time('2026-10-12 17:01:30'):
            self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)   # the engine stops at the window end

    @freeze_time(MONDAY_10_UTC)
    def test_engine_comes_back_after_a_send_while_more_is_queued(self):
        self._start()
        persona = self._persona()
        self._prospect(persona)
        self._prospect(persona, 'sara-khan', 'Sara Khan')
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)
        follow = self._triggers().filtered(lambda t: t.call_at >= datetime(2026, 10, 12, 10, 0, 30))
        self.assertTrue(follow)


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestSendMessagesNow(BackgroundCase):
    """"Send messages" and "answer replies" asked in Claude."""

    @freeze_time(MONDAY_10_UTC)
    def test_messages_written_then_sent_now(self):
        self._start()
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona)
        result = self.call('li_send_now', linkedin_profile='taha', what='messages')
        self.assertFalse(result['started'])
        self.assertIn('1 message(s) to write', result['message'])
        self.assertFalse(result['personas'])                         # invites not asked
        item = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'message'][0]
        self.call('li_submit_text', work_id=item['work_id'], text='Hi Ali, thanks for connecting!')
        result = self.call('li_send_now', linkedin_profile='taha', what='messages')
        self.assertTrue(result['started'])
        self.assertIn('sending: 1 message(s) now', result['message'])
        self._script(get_conversation=[{'data': {'sections': {'conversation': ''}}}])
        self._run()
        self.assertEqual(self._calls(tool='send_message')[0]['args']['message'], 'Hi Ali, thanks for connecting!')
        status = self.call('li_sending_status', linkedin_profile='taha')
        self.assertEqual(status['personas'][0]['messages_today'][0]['name'], prospect.name)
        self.assertIn('1 message(s) sent today', status['message'])

    @freeze_time(MONDAY_10_UTC)
    def test_chat_limit_and_stopped_agent(self):
        self.profile.sudo().engine_wanted = True
        persona = self._persona(run=(), chat_daily_limit=0)
        result = self.call('li_send_now', linkedin_profile='taha', what='messages')
        self.assertIn('Chat Agent is stopped: not started', result['message'])
        self.assertEqual(persona.chat_agent_id.state, 'stopped')
        with self.assertRaisesRegex(ToolError, 'what must be'):
            self.call('li_send_now', linkedin_profile='taha', what='everything')

    @freeze_time(MONDAY_10_UTC)
    def test_check_inbox_now(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        persona = self._persona(run=('chat',))
        self._accepted(persona)
        self._run()                                                   # first inbox read
        self.assertEqual(len(self._calls(tool='get_inbox')), 1)
        self._run()                                                   # within the interval: not again
        self.assertEqual(len(self._calls(tool='get_inbox')), 1)
        result = self.call('li_check_inbox_now', linkedin_profile='taha')
        self.assertTrue(result['started'])
        self.assertIn('li_get_work', result['message'])
        self._run()
        self.assertEqual(len(self._calls(tool='get_inbox')), 2)
        self.profile.connection_state = 'reconnect_needed'
        self.assertFalse(self.call('li_check_inbox_now', linkedin_profile='taha')['started'])


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestInvitePerson(BackgroundCase):
    """"Send an invite to this person" with a LinkedIn link, asked in Claude."""

    URL = 'https://www.linkedin.com/in/fawad-hussain-fhk/?isSelfProfile=true'

    @freeze_time(MONDAY_10_UTC)
    def test_invite_a_linked_person_now(self):
        self._start()
        persona = self._persona()
        result = self.call('li_invite_person', linkedin_url=self.URL)
        self.assertTrue(result['ok'] and result['started'])
        prospect = self.env['li.prospect'].browse(result['prospect_id'])
        self.assertEqual((prospect.linkedin_url, prospect.name, prospect.persona_id),
                         ('https://www.linkedin.com/in/fawad-hussain-fhk/', 'Fawad Hussain Fhk', persona))
        self._run()
        self.assertEqual(self._calls(tool='connect_with_person')[0]['args'], {'linkedin_username': 'fawad-hussain-fhk'})
        self.assertEqual(prospect.stage, 'invited')
        again = self.call('li_invite_person', linkedin_url=self.URL)
        self.assertFalse(again['ok'])
        self.assertIn('already a prospect', again['message'])

    @freeze_time(MONDAY_10_UTC)
    def test_note_and_refusals(self):
        self.profile.sudo().engine_wanted = True
        persona = self._persona(con_send_note=True, con_note_instructions='Short.')
        result = self.call('li_invite_person', linkedin_url=self.URL, name='Fawad Hussain')
        self.assertTrue(result['needs_note'])
        result = self.call('li_invite_person', linkedin_url=self.URL, note='Hi Fawad,\nlet us connect.')
        self.assertTrue(result['started'])
        item = self.env['li.work.item'].search([('prospect_id', '=', result['prospect_id'])])
        self.assertEqual((item.state, item.text_confirmed, item.with_note), ('queued', 'Hi Fawad, let us connect.', True))
        own = self.call('li_invite_person', linkedin_url='https://www.linkedin.com/in/taha-test/?isSelfProfile=true')
        self.assertFalse(own['ok'])
        self.assertIn('does not allow inviting yourself', own['message'])
        self.env['li.prospect'].create({'name': 'Blocked', 'persona_id': persona.id, 'stage': 'do_not_contact',
                                        'linkedin_url': 'https://www.linkedin.com/in/blocked-one/'})
        self.assertIn('do-not-contact', self.call('li_invite_person',
                                                  linkedin_url='https://www.linkedin.com/in/blocked-one/')['message'])
        with self.assertRaisesRegex(ToolError, 'profile link'):
            self.call('li_invite_person', linkedin_url='fawad hussain')
        with self.assertRaisesRegex(ToolError, 'at most 200'):
            self.call('li_invite_person', linkedin_url='https://www.linkedin.com/in/someone-new/', note='x' * 201)
