from datetime import datetime

from odoo.tests import freeze_time, tagged

from .common import LiTransactionCase
from ..models.li_mcp_tools import ToolError

MONDAY_10_UTC = '2026-10-12 10:00:00'      # Monday


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestChromeMode(LiTransactionCase):

    def _persona(self, name='Chrome persona', profile=None, **vals):
        values = dict(con_send_window_from=0.0, con_send_window_to=24.0, con_delay_min=0, con_delay_max=0)
        values.update(vals)
        persona = self._make_persona(name, profile=profile, **values)
        persona.action_connection_run()
        return persona

    def _prospect(self, persona, username='ali-raza', name='Ali Raza', **vals):
        return self.env['li.prospect'].create(dict({
            'name': name, 'persona_id': persona.id, 'linkedin_url': 'https://www.linkedin.com/in/%s/' % username,
        }, **vals))

    def _invite(self, account='taha'):
        items = [i for i in self.call('li_get_work', linkedin_profile=account)['items'] if i['type'] == 'invite']
        self.assertTrue(items)
        go = self.call('li_confirm_send', work_id=items[0]['work_id'])
        self.assertTrue(go['go'], go)
        return items[0]

    # ------------------------------------------------------------------
    # Account check
    # ------------------------------------------------------------------
    def test_li_get_work_needs_a_profile(self):
        with self.assertRaisesRegex(ToolError, 'linkedin_profile is required'):
            self.call('li_get_work')
        with self.assertRaisesRegex(ToolError, 'Unknown LinkedIn profile'):
            self.call('li_get_work', linkedin_profile='nobody')

    def test_verify_account_first(self):
        self.profile.chrome_verified_at = False
        self._prospect(self._persona())
        work = self.call('li_get_work', linkedin_profile='taha')
        self.assertEqual([i['type'] for i in work['items']], ['verify_account'])
        verify = work['items'][0]
        self.assertIn('/in/me/', verify['instructions'])
        # Chrome signed in to another account: refused, nothing unlocked
        wrong = self.call('li_report_result', work_id=verify['work_id'], linkedin_profile='taha', status='verified',
                          linkedin_url='https://www.linkedin.com/in/someone-else/')
        self.assertFalse(wrong['ok'])
        self.assertIn('someone-else', wrong['message'])
        verify = self.call('li_get_work', linkedin_profile='taha')['items'][0]
        self.assertEqual(verify['type'], 'verify_account')
        ok = self.call('li_report_result', work_id=verify['work_id'], linkedin_profile='taha', status='verified',
                       linkedin_url='https://www.linkedin.com/in/taha-test/?trk=x')
        self.assertTrue(ok['ok'])
        self.assertTrue(self.profile.chrome_verified_at)
        types = [i['type'] for i in self.call('li_get_work', linkedin_profile='taha')['items']]
        self.assertIn('invite', types)
        self.assertNotIn('verify_account', types)

    def test_not_signed_in_sets_reconnect_needed_then_verify_reconnects(self):
        self.profile.chrome_verified_at = False
        persona = self._persona()
        verify = self.call('li_get_work', linkedin_profile='taha')['items'][0]
        result = self.call('li_report_result', work_id=verify['work_id'], linkedin_profile='taha',
                           status='not_logged_in')
        self.assertFalse(result['ok'])
        self.assertEqual(self.profile.connection_state, 'reconnect_needed')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual(self.profile2.connection_state, 'connected')
        verify = self.call('li_get_work', linkedin_profile='taha')['items']
        self.assertEqual([i['type'] for i in verify], ['verify_account'])
        self.call('li_report_result', work_id=verify[0]['work_id'], linkedin_profile='taha', status='verified',
                  linkedin_url='https://www.linkedin.com/in/taha-test/')
        self.assertEqual(self.profile.connection_state, 'connected')

    # ------------------------------------------------------------------
    # Engine profiles refuse the browser tools
    # ------------------------------------------------------------------
    def test_engine_profile_refuses_browser_tools(self):
        persona = self._persona()
        self._prospect(persona)
        invite = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'invite'][0]
        self.profile.execution_mode = 'engine'
        calls = [
            ('li_confirm_send', {'work_id': invite['work_id']}),
            ('li_report_result', {'work_id': invite['work_id'], 'status': 'sent', 'linkedin_profile': 'taha'}),
            ('li_record_conversation', {'linkedin_profile': 'taha', 'prospect_id': 1,
                                        'messages': [{'sender_name': 'A', 'text': 'b'}]}),
            ('li_report_error', {'linkedin_profile': 'taha', 'error': 'x'}),
            ('li_mark_accepted', {'work_id': invite['work_id'], 'accepted': [], 'linkedin_profile': 'taha'}),
            ('li_add_prospects', {'work_id': invite['work_id'], 'people': [], 'linkedin_profile': 'taha'}),
        ]
        for tool, arguments in calls:
            with self.assertRaisesRegex(ToolError, 'built-in engine|search_prospects|check_acceptance',
                                        msg=tool):
                self.call(tool, **arguments)
        work = self.call('li_get_work', linkedin_profile='taha')
        self.assertEqual(work['execution_mode'], 'engine')
        self.assertFalse([i for i in work['items'] if i['type'] != 'analyse'])
        self.assertIn('Do not open LinkedIn', work['note'])

    def test_items_carry_browser_instructions(self):
        persona = self._persona()
        self._prospect(persona)
        items = self.call('li_get_work', linkedin_profile='taha')['items']
        invite = [i for i in items if i['type'] == 'invite'][0]
        self.assertIn('Connect', invite['instructions'])
        self.assertNotIn('connect_with_person', invite['instructions'])
        self.assertEqual(invite['linkedin_profile'], 'taha')

    # ------------------------------------------------------------------
    # Statuses
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_weekly_invite_limit_pauses_until_next_week(self):
        persona = self._persona(tz='Asia/Karachi')
        other = self._persona('Second persona')
        self._prospect(persona)
        self._prospect(persona, 'sara-khan', 'Sara Khan')
        invite = self._invite()
        result = self.call('li_report_result', work_id=invite['work_id'], linkedin_profile='taha',
                           status='weekly_invite_limit', error="You've reached the weekly invitation limit")
        self.assertTrue(result['ok'])
        agent = persona.connection_agent_id
        self.assertEqual(agent.state, 'paused')
        self.assertEqual(other.connection_agent_id.state, 'paused')      # same LinkedIn account
        # next Monday 00:00 in Karachi (UTC+5) = Sunday 19:00 UTC
        self.assertEqual(agent.paused_until, datetime(2026, 10, 18, 19, 0))
        item = self.env['li.work.item'].browse(invite['work_id'])
        self.assertEqual((item.state, item.quota_consumed), ('failed', False))
        self.assertEqual(self.env['li.prospect'].search([('linkedin_username', '=', 'ali-raza')]).stage, 'queued')
        self.assertFalse([i for i in self.call('li_get_work', linkedin_profile='taha')['items']
                          if i['type'] == 'invite'])
        with freeze_time('2026-10-18 18:59:00'):
            self.env['li.connection.agent']._resume_due()
            self.assertEqual(agent.state, 'paused')
        with freeze_time('2026-10-18 19:00:00'):
            self.env['li.connection.agent']._resume_due()
            self.assertEqual(agent.state, 'running')
            self.assertFalse(agent.paused_until)

    @freeze_time(MONDAY_10_UTC)
    def test_not_found_flags_prospect_without_quota(self):
        persona = self._persona()
        prospect = self._prospect(persona)
        invite = self._invite()
        self.call('li_report_result', work_id=invite['work_id'], linkedin_profile='taha', status='not_found')
        item = self.env['li.work.item'].browse(invite['work_id'])
        self.assertEqual((item.state, item.quota_consumed), ('failed', False))
        self.assertTrue(prospect.needs_check)
        self.assertIn('not found', prospect.needs_check_reason)

    @freeze_time(MONDAY_10_UTC)
    def test_followed_when_no_connect(self):
        persona = self._persona()
        prospect = self._prospect(persona)
        items = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'invite']
        self.assertIn('click Follow', items[0]['instructions'])
        self.assertTrue(self.call('li_confirm_send', work_id=items[0]['work_id'])['go'])
        self.call('li_report_result', work_id=items[0]['work_id'], linkedin_profile='taha', status='followed')
        self.assertEqual(prospect.stage, 'followed')
        self.assertFalse(self.env['li.work.item'].browse(items[0]['work_id']).quota_consumed)

    @freeze_time(MONDAY_10_UTC)
    def test_pending_marks_invited_without_quota(self):
        persona = self._persona()
        prospect = self._prospect(persona)
        invite = self._invite()
        self.call('li_report_result', work_id=invite['work_id'], linkedin_profile='taha', status='pending')
        self.assertEqual(prospect.stage, 'invited')
        self.assertFalse(self.env['li.work.item'].browse(invite['work_id']).quota_consumed)

    @freeze_time(MONDAY_10_UTC)
    def test_restricted_pauses_profile_and_tells_owner(self):
        persona = self._persona()
        on_other = self._persona('Other account', profile=self.profile2)
        self._prospect(persona)
        invite = self._invite()
        self.call('li_report_result', work_id=invite['work_id'], linkedin_profile='taha', status='restricted')
        self.assertEqual(self.profile.connection_state, 'restricted')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual(on_other.connection_agent_id.state, 'running')
        self.assertTrue(self.profile.activity_ids.filtered(lambda a: 'restricted' in a.summary
                                                           and a.user_id == self.rep))

    def test_report_error_restricted(self):
        persona = self._persona()
        self.call('li_report_error', linkedin_profile='taha', error='Account restricted', restricted=True)
        self.assertEqual(self.profile.connection_state, 'restricted')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual([i['type'] for i in self.call('li_get_work', linkedin_profile='taha')['items']],
                         ['verify_account'])
