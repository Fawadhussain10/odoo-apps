from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .li_common import utc_now

DEFAULT_INSTRUCTIONS = (
    "You run LinkedIn sales agents for this Odoo database. Do all LinkedIn work for these profiles only through "
    "this Odoo connector: never use another LinkedIn tool or connector, even if one is available. li_overview lists the LinkedIn profiles with their "
    "execution mode. For each profile you work on: Always start with li_get_work (linkedin_profile = its key) and "
    "do only the items it returns, in order; call li_get_work again until it returns no items. "
    "Built-in engine profiles: Odoo does all LinkedIn work itself; you only write. Answer invite_note, message, "
    "followup and handoff items with li_submit_text (one paragraph, no line breaks), analyse items with "
    "li_record_analysis, post_draft items with li_submit_post_draft. Never open LinkedIn for these profiles. When "
    "the user asks to send connections or messages now, call li_send_now (what: invites, messages or all), and "
    "li_sending_status to report what went out; to answer replies now, call li_check_inbox_now first, then "
    "li_get_work, analyse and write, then li_send_now with what messages. To invite a "
    "specific person the user links, call li_invite_person. "
    "Claude in Chrome profiles: work in Chrome signed in to that profile's LinkedIn account; the first item checks "
    "the account. Before every Connect, Send or Post click call li_confirm_send and act only if go is true. Report "
    "every item with the tool named in it, including failures, and never retry a send whose result had retry_safe "
    "false. If LinkedIn shows a sign-in page call li_report_error with session_expired true; if it says the account "
    "is restricted, with restricted true; then skip that profile. "
    "Before writing any message, handoff or follow-up: first read who the person is (prospect.profile in the item: "
    "headline, role, company, about, experience; in Chrome open their profile), then read the whole conversation so "
    "far (what we already said and asked, what they answered, the topic being discussed now), then read their last "
    "reply and judge its nature, and only then write so the text fits their real role and what they said, continues "
    "the current topic and moves toward the objective of the step. Never repeat something we already said or ask "
    "something they already answered, and never send a message that does not fit the person's profile or the "
    "conversation. "
    "Always: notes at most 200 characters, no prices or promises that are not in the item, stop with anyone who "
    "says no. If li_confirm_send says wait, do other items first and confirm again later. At the end call "
    "li_finish_run once, with the errors you met, and reply with a short summary per profile."
)

REPLY_NOW_PROMPT_ENGINE = (
    "Answer my LinkedIn replies now (Odoo connector). Call li_overview, then li_check_inbox_now for my built-in engine "
    "profile. After about two minutes call li_get_work: record each analyse item with li_record_analysis and write "
    "each message item with li_submit_text, repeating until no items are left. For every person, first read who they are (prospect.profile in the item), then the whole conversation so far (what we already said and asked, what they answered, the current topic), then their last reply and its nature, and only then analyse or write so the text fits their role and what they said and never repeats what was already said. "
    "Then call li_send_now with what messages, and later li_sending_status to tell me what was sent."
)
SEND_NOW_PROMPT_ENGINE = (
    "Send my LinkedIn connections now (Odoo connector). Call li_overview, then li_send_now for my built-in engine "
    "profile. If it says notes are missing, call li_get_work, write each invite_note with li_submit_text and call "
    "li_send_now again. Wait a few minutes, call li_sending_status and tell me who was invited."
)
RUN_PROMPT_ENGINE = (
    "Run my LinkedIn agents now (Odoo connector). Call li_overview, then for every LinkedIn profile in Built-in "
    "engine mode call li_get_work and answer every writing item (li_submit_text, li_record_analysis, "
    "li_submit_post_draft) until li_get_work returns no items. Do not open LinkedIn: Odoo sends and reads by itself. "
    "For every person, first read who they are (prospect.profile in the item), then the whole conversation so far (what we already said and asked, what they answered, the current topic), then their last reply and its nature, and only then analyse or write so the text fits their role and what they said and never repeats what was already said. "
    "Then call li_finish_run and give me a short summary per profile."
)
RUN_PROMPT_CHROME = (
    "Run my LinkedIn agents now for the profile {profile} in Claude in Chrome (Odoo connector). This Chrome is "
    "signed in to that LinkedIn account. Call li_get_work with linkedin_profile {profile} and do each item exactly as "
    "its instructions say (account check first, li_confirm_send before every Connect, Send or Post click), reporting "
    "each one; repeat until li_get_work returns no items. Before writing to anyone, open their profile and read it, "
    "then read the whole conversation and their last reply, and only then write, never repeating what was already said. Then call li_finish_run and give me a "
    "short summary."
)
SCHEDULED_PROMPT_ENGINE = (
    "Scheduled LinkedIn run (Odoo connector), 1 to 3 times a day, e.g. 09:30, 13:30 and 16:30 in my time zone. "
    "Call li_overview; for every Built-in engine profile call li_get_work and answer all writing items (li_submit_text, "
    "li_record_analysis, li_submit_post_draft) until none are left; never open LinkedIn. For every person, first read who they are (prospect.profile in the item), then the whole conversation so far (what we already said and asked, what they answered, the current topic), then their last reply and its nature, and only then analyse or write so the text fits their role and what they said and never repeats what was already said. "
    "Call li_finish_run with any "
    "errors and end with a three-line summary. If there is nothing to do, just call li_finish_run."
)
SCHEDULED_PROMPT_CHROME = (
    "Scheduled LinkedIn run for the profile {profile} in Claude in Chrome (Odoo connector), 1 to 3 times a day, e.g. "
    "10:00, 14:00 and 16:30 in the persona's working hours; this computer and Chrome must be on, signed in to that "
    "LinkedIn account. Call li_get_work with linkedin_profile {profile}, do each item as its instructions say "
    "(account check first, li_confirm_send before every click that sends or posts) until none are left. Before "
    "writing to anyone, open their profile and read it, then read the whole conversation and their last reply, and "
    "never repeat what was already said. If LinkedIn "
    "shows a sign-in page or a restriction, report it with li_report_error and stop. Call li_finish_run with any "
    "errors and end with a three-line summary."
)

# Earlier defaults: replaced on upgrade when the stored text was never customised.
PREVIOUS_DEFAULT_INSTRUCTIONS = [
    "You run LinkedIn sales agents for this Odoo database. Do all LinkedIn work for these profiles only through this Odoo connector: never use another LinkedIn tool or connector, even if one is available. li_overview lists the LinkedIn profiles with their execution mode. For each profile you work on: Always start with li_get_work (linkedin_profile = its key) and do only the items it returns, in order; call li_get_work again until it returns no items. Built-in engine profiles: Odoo does all LinkedIn work itself; you only write. Answer invite_note, message, followup and handoff items with li_submit_text (one paragraph, no line breaks), analyse items with li_record_analysis, post_draft items with li_submit_post_draft. Never open LinkedIn for these profiles. When the user asks to send connections or messages now, call li_send_now (what: invites, messages or all), and li_sending_status to report what went out; to answer replies now, call li_check_inbox_now first, then li_get_work, analyse and write, then li_send_now with what messages. To invite a specific person the user links, call li_invite_person. Claude in Chrome profiles: work in Chrome signed in to that profile's LinkedIn account; the first item checks the account. Before every Connect, Send or Post click call li_confirm_send and act only if go is true. Report every item with the tool named in it, including failures, and never retry a send whose result had retry_safe false. If LinkedIn shows a sign-in page call li_report_error with session_expired true; if it says the account is restricted, with restricted true; then skip that profile. Before writing any message, handoff or follow-up: first read who the person is (prospect.profile in the item: headline, role, company, about, experience; in Chrome open their profile), then read their last reply and judge its nature, and only then write so the text fits their real role and what they said and moves toward the objective of the step. Never send a message that does not fit the person's profile. Always: notes at most 200 characters, no prices or promises that are not in the item, stop with anyone who says no. If li_confirm_send says wait, do other items first and confirm again later. At the end call li_finish_run once, with the errors you met, and reply with a short summary per profile.",
    "You run LinkedIn sales agents for this Odoo database. Do all LinkedIn work for these profiles only through this Odoo connector: never use another LinkedIn tool or connector, even if one is available. li_overview lists the LinkedIn profiles with their execution mode. For each profile you work on: Always start with li_get_work (linkedin_profile = its key) and do only the items it returns, in order; call li_get_work again until it returns no items. Built-in engine profiles: Odoo does all LinkedIn work itself; you only write. Answer invite_note, message, followup and handoff items with li_submit_text (one paragraph, no line breaks), analyse items with li_record_analysis, post_draft items with li_submit_post_draft. Never open LinkedIn for these profiles. When the user asks to send connections or messages now, call li_send_now (what: invites, messages or all), and li_sending_status to report what went out; to answer replies now, call li_check_inbox_now first, then li_get_work, analyse and write, then li_send_now with what messages. To invite a specific person the user links, call li_invite_person. Claude in Chrome profiles: work in Chrome signed in to that profile's LinkedIn account; the first item checks the account. Before every Connect, Send or Post click call li_confirm_send and act only if go is true. Report every item with the tool named in it, including failures, and never retry a send whose result had retry_safe false. If LinkedIn shows a sign-in page call li_report_error with session_expired true; if it says the account is restricted, with restricted true; then skip that profile. Always: notes at most 200 characters, no prices or promises that are not in the item, stop with anyone who says no. If li_confirm_send says wait, do other items first and confirm again later. At the end call li_finish_run once, with the errors you met, and reply with a short summary per profile.",
    "You run LinkedIn sales agents for this Odoo database. li_overview lists the LinkedIn profiles with their execution mode. For each profile you work on: Always start with li_get_work (linkedin_profile = its key) and do only the items it returns, in order; call li_get_work again until it returns no items. Built-in engine profiles: Odoo does all LinkedIn work itself; you only write. Answer invite_note, message, followup and handoff items with li_submit_text (one paragraph, no line breaks), analyse items with li_record_analysis, post_draft items with li_submit_post_draft. Never open LinkedIn for these profiles. When the user asks to send connections or messages now, call li_send_now (what: invites, messages or all), and li_sending_status to report what went out; to answer replies now, call li_check_inbox_now first, then li_get_work, analyse and write, then li_send_now with what messages. To invite a specific person the user links, call li_invite_person. Claude in Chrome profiles: work in Chrome signed in to that profile's LinkedIn account; the first item checks the account. Before every Connect, Send or Post click call li_confirm_send and act only if go is true. Report every item with the tool named in it, including failures, and never retry a send whose result had retry_safe false. If LinkedIn shows a sign-in page call li_report_error with session_expired true; if it says the account is restricted, with restricted true; then skip that profile. Always: notes at most 200 characters, no prices or promises that are not in the item, stop with anyone who says no. If li_confirm_send says wait, do other items first and confirm again later. At the end call li_finish_run once, with the errors you met, and reply with a short summary per profile.",
    "You run LinkedIn sales agents for this Odoo database. li_overview lists the LinkedIn profiles with their execution mode. For each profile you work on: Always start with li_get_work (linkedin_profile = its key) and do only the items it returns, in order; call li_get_work again until it returns no items. Built-in engine profiles: Odoo does all LinkedIn work itself; you only write. Answer invite_note, message, followup and handoff items with li_submit_text (one paragraph, no line breaks), analyse items with li_record_analysis, post_draft items with li_submit_post_draft. Never open LinkedIn for these profiles. When the user asks to send connections or messages now, call li_send_now (what: invites, messages or all), and li_sending_status to report what went out; to answer replies now, call li_check_inbox_now first, then li_get_work, analyse and write, then li_send_now with what messages. Claude in Chrome profiles: work in Chrome signed in to that profile's LinkedIn account; the first item checks the account. Before every Connect, Send or Post click call li_confirm_send and act only if go is true. Report every item with the tool named in it, including failures, and never retry a send whose result had retry_safe false. If LinkedIn shows a sign-in page call li_report_error with session_expired true; if it says the account is restricted, with restricted true; then skip that profile. Always: notes at most 200 characters, no prices or promises that are not in the item, stop with anyone who says no. If li_confirm_send says wait, do other items first and confirm again later. At the end call li_finish_run once, with the errors you met, and reply with a short summary per profile.",
    "You run LinkedIn sales agents for this Odoo database. li_overview lists the LinkedIn profiles with their execution mode. For each profile you work on: Always start with li_get_work (linkedin_profile = its key) and do only the items it returns, in order; call li_get_work again until it returns no items. Built-in engine profiles: Odoo does all LinkedIn work itself; you only write. Answer invite_note, message, followup and handoff items with li_submit_text (one paragraph, no line breaks), analyse items with li_record_analysis, post_draft items with li_submit_post_draft. Never open LinkedIn for these profiles. When the user asks to send connections now, call li_send_now, and li_sending_status to report what went out. Claude in Chrome profiles: work in Chrome signed in to that profile's LinkedIn account; the first item checks the account. Before every Connect, Send or Post click call li_confirm_send and act only if go is true. Report every item with the tool named in it, including failures, and never retry a send whose result had retry_safe false. If LinkedIn shows a sign-in page call li_report_error with session_expired true; if it says the account is restricted, with restricted true; then skip that profile. Always: notes at most 200 characters, no prices or promises that are not in the item, stop with anyone who says no. If li_confirm_send says wait, do other items first and confirm again later. At the end call li_finish_run once, with the errors you met, and reply with a short summary per profile.",
    "You run LinkedIn sales agents for this Odoo database. li_overview lists the LinkedIn profiles with their "
    "execution mode. For each profile you work on: Always start with li_get_work (linkedin_profile = its key) and "
    "do only the items it returns, in order; call li_get_work again until it returns no items. "
    "Built-in engine profiles: Odoo does all LinkedIn work itself; you only write. Answer invite_note, message, "
    "followup and handoff items with li_submit_text (one paragraph, no line breaks), analyse items with "
    "li_record_analysis, post_draft items with li_submit_post_draft. Never open LinkedIn for these profiles. "
    "Claude in Chrome profiles: work in Chrome signed in to that profile's LinkedIn account; the first item checks "
    "the account. Before every Connect, Send or Post click call li_confirm_send and act only if go is true. Report "
    "every item with the tool named in it, including failures, and never retry a send whose result had retry_safe "
    "false. If LinkedIn shows a sign-in page call li_report_error with session_expired true; if it says the account "
    "is restricted, with restricted true; then skip that profile. "
    "Always: notes at most 200 characters, no prices or promises that are not in the item, stop with anyone who "
    "says no. If li_confirm_send says wait, do other items first and confirm again later. At the end call "
    "li_finish_run once, with the errors you met, and reply with a short summary per profile.",
    "You run LinkedIn sales agents for this Odoo database. li_overview lists the LinkedIn profiles and their "
    "execution mode. For each profile: Always start with li_get_work (linkedin_profile = its key) and do only "
    "the items it returns, in order. Built-in engine profiles: Odoo does their LinkedIn work itself, so do only "
    "the writing items and never open LinkedIn for them. Claude in Chrome profiles: work in Chrome signed in to "
    "that profile's LinkedIn account; the first item checks the account. Before every Connect or Send click call "
    "li_confirm_send and send only if go is true. Report every item with the tool named in it, including "
    "failures. Never retry a send whose result had retry_safe false. If LinkedIn shows a sign-in page call "
    "li_report_error with session_expired true; if it says the account is restricted, with restricted true; "
    "then skip that profile. Keep notes at most 200 characters, never mention prices or promises that are not "
    "in the item, and stop with anyone who says no. If li_confirm_send says wait, do other items first and call "
    "li_confirm_send again later. Repeat li_get_work until it returns no items, then call li_finish_run and "
    "reply with a short summary per profile.",
    "You run LinkedIn sales agents for this Odoo database. Always start with li_get_work and do only "
    "the items it returns, in order. Use exactly the LinkedIn connector named in each item. Before any "
    "connect_with_person or send_message call li_confirm_send and send only if go is true. Report "
    "every item with the tool named for its type, including failures. Never retry a send whose result "
    "had retry_safe false. If a LinkedIn tool says the session expired or login is needed, call "
    "li_report_error with session_expired true and skip that account. Keep notes at most 200 "
    "characters, never mention prices or promises that are not in the item, and stop with anyone who "
    "says no. If li_confirm_send says wait, do other items first (other accounts, inbox checks, analysis) "
    "and call li_confirm_send again later. If only waiting items are left, call li_finish_run. "
    "Repeat li_get_work until it returns no items, then call li_finish_run and reply with a short "
    "summary.",
    "You run LinkedIn sales agents for this Odoo database. Always start with li_get_work and do only "
    "the items it returns, in order. Use exactly the LinkedIn connector named in each item. Before any "
    "connect_with_person or send_message call li_confirm_send and send only if go is true. Report "
    "every item with the tool named for its type, including failures. Never retry a send whose result "
    "had retry_safe false. If a LinkedIn tool says the session expired or login is needed, call "
    "li_report_error with session_expired true and skip that account. Keep notes at most 200 "
    "characters, never mention prices or promises that are not in the item, and stop with anyone who "
    "says no. Repeat li_get_work until it returns no items, then call li_finish_run and reply with a short "
    "summary.",
]


class LiMcpLog(models.Model):
    _name = 'li.mcp.log'
    _description = 'MCP call log'
    _order = 'id desc'
    _rec_name = 'method'

    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    user_id = fields.Many2one('res.users', ondelete='set null')
    method = fields.Char(required=True)
    tool = fields.Char(index=True)
    args_size = fields.Integer('Arguments size (bytes)')
    duration_ms = fields.Integer('Duration (ms)')
    ok = fields.Boolean()
    error = fields.Text()
    remote_addr = fields.Char()
    token_id = fields.Many2one('li.mcp.token', 'Token', ondelete='set null')

    @api.model
    def _cron_purge(self, days=30):
        old = self.search([('date', '<', utc_now() - timedelta(days=days))])
        old.unlink()
        return len(old)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    li_prospect_id = fields.Many2one('li.prospect', 'LinkedIn prospect', index=True, ondelete='set null',
                                     copy=False)
    li_persona_id = fields.Many2one('li.persona', 'LinkedIn persona', index=True, ondelete='set null',
                                    copy=False)

    def action_open_li_prospect(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'li.prospect',
                'res_id': self.li_prospect_id.id, 'view_mode': 'form'}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    li_mcp_enabled = fields.Boolean('Odoo MCP endpoint', config_parameter='li_sales.mcp_enabled', default=True)
    # filled by get_values: computed fields are not evaluated on the unsaved settings record
    li_mcp_url = fields.Char('MCP URL', readonly=True)
    li_mcp_token_count = fields.Integer('Active MCP tokens', readonly=True)
    li_max_sends_per_account = fields.Integer('Max sends per account per li_get_work',
                                              config_parameter='li_sales.max_sends_per_account', default=5)
    li_max_items_per_run = fields.Integer('Max items per li_get_work', config_parameter='li_sales.max_items_per_run',
                                          default=20)
    li_claim_timeout = fields.Integer('Claim timeout (minutes)', config_parameter='li_sales.claim_timeout',
                                      default=15)
    li_inbox_interval = fields.Integer('Check inbox every (minutes)', config_parameter='li_sales.inbox_interval',
                                       default=60)
    li_acceptance_interval = fields.Integer('Check acceptance every (hours)',
                                            config_parameter='li_sales.acceptance_interval', default=6)
    # Built-in engine: background work
    li_read_budget = fields.Integer('Daily read budget per profile', config_parameter='li_sales.read_budget',
                                    default=150)
    li_connections_every = fields.Integer('Recent connections read every (minutes)',
                                          config_parameter='li_sales.connections_every', default=15)
    li_acceptance_every = fields.Integer('Acceptance checks every (minutes)',
                                         config_parameter='li_sales.acceptance_every', default=60)
    li_acceptance_per_run = fields.Integer('Acceptance checks per run', config_parameter='li_sales.acceptance_per_run',
                                           default=3)
    li_engine_tool_timeout = fields.Integer('Engine action timeout (seconds)',
                                            config_parameter='li_sales.engine_tool_timeout', default=60)
    # LinkedIn engine (filled by get_values; read-only)
    li_is_odoo_sh = fields.Boolean(readonly=True)
    li_engine_state = fields.Char('Engine', readonly=True)
    li_engine_message = fields.Char(readonly=True)
    li_engine_detail = fields.Text(readonly=True)
    li_engine_admin_commands = fields.Text(readonly=True)
    li_engine_preparing = fields.Boolean(readonly=True)

    # Text is not allowed as config_parameter: stored by get_values / set_values
    li_mcp_instructions = fields.Text('Server instructions')
    # Prompts to paste in Claude (read-only, filled by get_values)
    li_prompt_run_engine = fields.Text('Run now – built-in engine', readonly=True)
    li_prompt_send_now_engine = fields.Text('Send connections now – built-in engine', readonly=True)
    li_prompt_reply_now_engine = fields.Text('Answer replies now – built-in engine', readonly=True)
    li_prompt_run_chrome = fields.Text('Run now – Claude in Chrome', readonly=True)
    li_prompt_scheduled_engine = fields.Text('Scheduled – built-in engine', readonly=True)
    li_prompt_scheduled_chrome = fields.Text('Scheduled – Claude in Chrome', readonly=True)

    def action_li_new_token(self):
        return {'type': 'ir.actions.act_window', 'res_model': 'li.mcp.token.wizard', 'view_mode': 'form',
                'target': 'new', 'name': _('New MCP token')}

    def action_li_manage_tokens(self):
        return self.env['ir.actions.act_window']._for_xml_id('linkedin_sales_automation.action_li_mcp_token')

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        res['li_mcp_instructions'] = icp.get_param('li_sales.mcp_instructions') or DEFAULT_INSTRUCTIONS
        res['li_mcp_url'] = '%s/li_sales/mcp' % (icp.get_param('web.base.url') or '').rstrip('/')
        res['li_mcp_token_count'] = self.env['li.mcp.token'].sudo().search_count([])
        res.update(self._li_engine_values())
        chrome = self.env['li.profile'].search([('execution_mode', '=', 'chrome')], limit=1).account_key or '<profile key>'
        res.update({
            'li_prompt_run_engine': RUN_PROMPT_ENGINE,
            'li_prompt_send_now_engine': SEND_NOW_PROMPT_ENGINE,
            'li_prompt_reply_now_engine': REPLY_NOW_PROMPT_ENGINE,
            'li_prompt_run_chrome': RUN_PROMPT_CHROME.format(profile=chrome),
            'li_prompt_scheduled_engine': SCHEDULED_PROMPT_ENGINE,
            'li_prompt_scheduled_chrome': SCHEDULED_PROMPT_CHROME.format(profile=chrome),
        })
        return res

    @api.model
    def _li_engine_values(self):
        from .li_engine_manager import is_odoo_sh
        if is_odoo_sh():
            return {'li_is_odoo_sh': True, 'li_engine_state': _('Not available on Odoo.sh'),
                    'li_engine_message': _('Use the Claude in Chrome mode on every LinkedIn Profile.')}
        manager = self.env['li.engine.manager']
        status = manager._prepare_status()
        health = manager._health()
        state = {'none': _('Not prepared'), 'running': _('Preparing…'), 'failed': _('Preparation failed'),
                 'done': _('Ready') if health['ready'] else _('Prepared, system libraries missing')}.get(
            status.get('state'), status.get('state'))
        lines = []
        if status.get('state') == 'running':
            done = len(status.get('done_steps') or [])
            lines.append(_('Step %(n)s of %(total)s: %(message)s', n=done + 1, total=len(status.get('steps') or []),
                           message=status.get('message') or ''))
        if health.get('engine_version'):
            lines.append(_('Engine: mcp-server-linkedin %s', health['engine_version']))
        if health.get('python'):
            lines.append(_('Python: %s', health['python']))
        if health.get('chrome'):
            lines.append(_('Browser: installed'))
        lines.append(_('Window for the browser (Xvfb): %s', _('available') if health['xvfb']
                       else _('not installed, the browser runs headless')))
        if health['missing_libs']:
            lines.append(_('Missing system libraries: %s', ', '.join(health['missing_libs'])))
        if status.get('error'):
            lines.append(_('Error: %s', status['error']))
        lines.append(_('Folder: %s', manager._root()))
        return {
            'li_is_odoo_sh': False,
            'li_engine_state': state,
            'li_engine_message': status.get('message') or '',
            'li_engine_detail': '\n'.join(lines),
            'li_engine_admin_commands': '\n'.join(health['admin_commands']) or False,
            'li_engine_preparing': status.get('state') == 'running',
        }

    def action_li_prepare_engine(self):
        if not self.env.user.has_group('linkedin_sales_automation.group_li_admin'):
            raise UserError(_('Only a LinkedIn Sales Administrator can prepare the engine.'))
        self.env['li.engine.manager']._start_prepare()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_li_refresh_engine(self):
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def set_values(self):
        super().set_values()
        value = (self.li_mcp_instructions or '').strip() or DEFAULT_INSTRUCTIONS
        self.env['ir.config_parameter'].sudo().set_param('li_sales.mcp_instructions', value)

    @api.model
    def _li_upgrade_default_instructions(self):
        icp = self.env['ir.config_parameter'].sudo()
        current = icp.get_param('li_sales.mcp_instructions')
        if current and current.strip() in PREVIOUS_DEFAULT_INSTRUCTIONS:
            icp.set_param('li_sales.mcp_instructions', DEFAULT_INSTRUCTIONS)

    @api.model
    def _li_remove_duplicate_medium(self):
        """Early builds created a second "LinkedIn" UTM medium; utm already has one."""
        data = self.env['ir.model.data'].sudo().search([('module', '=', 'linkedin_sales_automation'),
                                                        ('name', '=', 'utm_medium_linkedin')])
        if data:
            medium = self.env['utm.medium'].sudo().browse(data.res_id).exists()
            target = self.env.ref('utm.utm_medium_linkedin')
            if medium and medium != target:
                self.env['crm.lead'].sudo().with_context(active_test=False).search(
                    [('medium_id', '=', medium.id)]).write({'medium_id': target.id})
                medium.unlink()
            data.unlink()

    def action_li_reset_instructions(self):
        self.env['ir.config_parameter'].sudo().set_param('li_sales.mcp_instructions', DEFAULT_INSTRUCTIONS)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
