from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import LiTransactionCase
from ..models.li_mcp_tools import TOOLS, ToolError


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestFoundation(LiTransactionCase):

    def test_persona_creates_agents_and_draft_state(self):
        persona = self._make_persona('Fashion founders – PK', con_daily_limit=12, chat_daily_limit=30)
        self.assertTrue(persona.connection_agent_id and persona.chat_agent_id)
        self.assertEqual(persona.connection_agent_id.daily_limit, 12)
        self.assertEqual(persona.chat_agent_id.daily_limit, 30)
        self.assertEqual(persona.connection_agent_id.delay_min, 45)
        self.assertEqual(persona.state, 'draft')

    def test_persona_status_rules(self):
        persona = self._make_persona('Status persona')
        persona.chat_agent_id.step_ids = [(0, 0, {'name': 'Intro', 'trigger': 'after_accept'})]
        persona.chat_agent_id.pivot_criteria = 'Asks for a call'
        persona.action_connection_run()
        self.assertEqual(persona.state, 'active')
        persona.action_connection_pause()
        self.assertEqual(persona.state, 'paused')
        persona.action_chat_run()
        self.assertEqual(persona.state, 'active')
        persona.action_stop_all()
        self.assertEqual(persona.state, 'stopped')
        self.assertTrue(persona.date_activated)
        self.assertTrue(self.env['li.event'].search_count([('persona_id', '=', persona.id),
                                                           ('event_type', '=', 'agent_started')]))

    def test_run_blocked_with_clear_message(self):
        persona = self._make_persona('Blocked')
        self.profile.connection_state = 'not_connected'
        with self.assertRaisesRegex(UserError, 'not Connected'):
            persona.action_connection_run()
        self.profile.connection_state = 'connected'
        with self.assertRaisesRegex(UserError, 'questionnaire step'):
            persona.action_chat_run()

    def test_engine_details_admin_only(self):
        self.assertEqual(self.profile.with_user(self.manager).read(['name'])[0]['name'], self.profile.name)
        with self.assertRaises(AccessError):
            self.profile.with_user(self.manager).read(['engine_port'])

    def test_record_rules_own_profiles(self):
        mine = self._make_persona('Mine', profile=self.profile)
        other = self._make_persona('Other', profile=self.profile2)
        visible = self.env['li.persona'].with_user(self.rep).search([('id', 'in', (mine | other).ids)])
        self.assertEqual(visible, mine)
        visible = self.env['li.persona'].with_user(self.manager).search([('id', 'in', (mine | other).ids)])
        self.assertEqual(visible, mine | other)

    def test_connector_lookup(self):
        Profile = self.env['li.profile']
        self.assertEqual(Profile._find_by_account('taha'), self.profile)
        self.assertEqual(Profile._find_by_account(' TAHA '), self.profile)
        self.assertEqual(Profile._find_by_account('Taha Sohail - Main'), self.profile)
        self.assertFalse(Profile._find_by_account('rep2'))
        self.assertEqual(Profile._find_by_account(str(self.profile.id)), self.profile)
        self.assertFalse(Profile._find_by_account('999999999'))

    def test_tool_list_has_no_generic_tool(self):
        names = {t['name'] for t in TOOLS}
        self.assertEqual(names, {'li_overview', 'li_get_work', 'li_confirm_send', 'li_report_result',
                                 'li_add_prospects', 'li_record_conversation', 'li_mark_accepted',
                                 'li_record_analysis', 'li_report_error', 'li_take_over', 'li_finish_run',
                                 'li_submit_text', 'li_submit_post_draft', 'li_send_now',
                                 'li_sending_status', 'li_check_inbox_now', 'li_invite_person'})
        for tool in TOOLS:
            self.assertIn('readOnlyHint', tool['annotations'])
            if not tool['annotations']['readOnlyHint']:
                self.assertFalse(tool['annotations'].get('destructiveHint'))

    def test_argument_validation(self):
        with self.assertRaisesRegex(ToolError, 'work_id is required'):
            self.call('li_confirm_send')
        with self.assertRaisesRegex(ToolError, 'Unknown argument'):
            self.call('li_overview', model='res.partner')
        with self.assertRaisesRegex(ToolError, 'Unknown tool'):
            self.tools.call_tool('search_read', {})

    def test_overview(self):
        self._make_persona('Overview persona')
        result = self.call('li_overview')
        self.assertIn('taha', [p['linkedin_profile'] for p in result['profiles']])
        self.assertIn('Overview persona', [p['name'] for p in result['personas']])

    def test_settings_open_and_save(self):
        settings = self.env['res.config.settings'].create({})
        self.assertIn('li_get_work', settings.li_mcp_instructions)
        self.assertTrue(settings.li_mcp_url.endswith('/li_sales/mcp'))
        self.env['li.mcp.token']._generate('Settings test')
        self.assertEqual(self.env['res.config.settings'].create({}).li_mcp_token_count,
                         self.env['li.mcp.token'].search_count([]))
        settings.li_mcp_instructions = 'Custom instructions'
        settings.li_max_items_per_run = 12
        settings.execute()
        icp = self.env['ir.config_parameter'].sudo()
        self.assertEqual(icp.get_param('li_sales.mcp_instructions'), 'Custom instructions')
        self.assertEqual(icp.get_param('li_sales.max_items_per_run'), '12')
        self.assertEqual(self.env['res.config.settings'].create({}).li_mcp_instructions, 'Custom instructions')
