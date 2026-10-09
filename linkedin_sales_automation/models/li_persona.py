from odoo import _, api, fields, models
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import UserError

LANGUAGES = [
    ('en', 'English'),
    ('ar', 'Arabic'),
    ('ur', 'Urdu'),
    ('fr', 'French'),
    ('de', 'German'),
    ('es', 'Spanish'),
]


AGENT_FIELDS = {
    'con_daily_limit', 'con_weekly_limit', 'con_send_window_from', 'con_send_window_to', 'con_delay_min',
    'con_delay_max', 'con_send_note', 'con_note_instructions', 'con_stop_tracking_after_days',
    'con_skip_if_contacted', 'con_total_target', 'con_follow_if_no_connect',
    'chat_daily_limit', 'chat_first_message_delay', 'chat_step_ids', 'chat_pivot_criteria',
    'chat_pivot_min_step', 'chat_stop_on_negative', 'chat_handoff_message', 'chat_meeting_link',
    'chat_send_window_from', 'chat_send_window_to',
}


def _default_working_days(self):
    return self.env['li.weekday'].search([('code', '<=', 4)])


class LiPersona(models.Model):
    _name = 'li.persona'
    _description = 'LinkedIn Persona'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'linkedin_profile_id, name'

    name = fields.Char(required=True, tracking=True)
    linkedin_profile_id = fields.Many2one(
        'li.profile', 'LinkedIn Profile', required=True, tracking=True, index=True, ondelete='restrict',
        domain=[('connection_state', '=', 'connected')])
    company_id = fields.Many2one(related='linkedin_profile_id.company_id', store=True, index=True)
    service_id = fields.Many2one('li.service', 'Service', required=True, tracking=True, ondelete='restrict',
                                 domain=[('active', '=', True)])
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('stopped', 'Stopped'),
    ], compute='_compute_state', store=True, index=True, tracking=True)
    job_titles = fields.Text(required=True, help='Comma separated: Founder, CEO, Head of Operations…')
    seniority_ids = fields.Many2many('li.target.tag', 'li_persona_seniority_rel', string='Seniority',
                                     domain=[('kind', '=', 'seniority')])
    industry_ids = fields.Many2many('li.target.tag', 'li_persona_industry_rel', string='Industries',
                                    domain=[('kind', '=', 'industry')])
    location_ids = fields.Many2many('li.target.tag', 'li_persona_location_rel', string='Locations',
                                    domain=[('kind', '=', 'location')])
    company_size_ids = fields.Many2many('li.company.size', string='Company size')
    include_keywords = fields.Char()
    exclude_keywords = fields.Char()
    search_url = fields.Char('Search URL', help='Optional LinkedIn search URL used as the lead source instead of '
                                                'the filters. Sales Navigator URLs are not supported by the '
                                                'LinkedIn server.')
    icp_description = fields.Text('Ideal customer', required=True, help='Passed to Claude.')
    pain_points = fields.Text(help='Passed to Claude.')
    tone = fields.Selection([('professional', 'Professional'), ('friendly', 'Friendly'), ('direct', 'Direct')],
                            required=True, default='professional')
    language = fields.Selection(LANGUAGES, required=True, default='en')
    salesperson_id = fields.Many2one('res.users', 'Salesperson', help='Assigned on the CRM lead at pivot.')
    crm_team_id = fields.Many2one('crm.team', 'Sales team', help='Overrides the service default.')
    target_timezone = fields.Selection(_tz_get, 'Target time zone', required=True, default='Asia/Karachi',
                                       help='Time zone of the audience. Every send window of this persona is '
                                            'read in this zone.')
    target_working_days = fields.Many2many('li.weekday', string='Target working days', required=True,
                                           default=_default_working_days)
    connection_agent_id = fields.Many2one('li.connection.agent', readonly=True, copy=False, ondelete='set null')
    chat_agent_id = fields.Many2one('li.chat.agent', readonly=True, copy=False, ondelete='set null')
    connection_state = fields.Selection(related='connection_agent_id.state', string='Connection Agent state')
    chat_state = fields.Selection(related='chat_agent_id.state', string='Chat Agent state')
    date_activated = fields.Datetime(readonly=True, copy=False, help='First time any agent ran.')
    active = fields.Boolean(default=True)
    color = fields.Integer()

    prospect_ids = fields.One2many('li.prospect', 'persona_id')
    prospect_count = fields.Integer(compute='_compute_counts')
    accepted_count = fields.Integer('Accepted', compute='_compute_counts')
    lead_count = fields.Integer('Warm leads', compute='_compute_counts')
    meeting_count = fields.Integer('Meetings', compute='_compute_counts')
    invites_today = fields.Integer('Invites today', compute='_compute_today')
    messages_today = fields.Integer('Messages today', compute='_compute_today')
    event_count = fields.Integer(compute='_compute_counts')

    # Agent settings edited on the persona form (stored on the agents)
    con_daily_limit = fields.Integer(string='Connection daily limit', related='connection_agent_id.daily_limit', readonly=False, default=15)
    con_weekly_limit = fields.Integer(string='Connection weekly limit', related='connection_agent_id.weekly_limit', readonly=False)
    con_send_window_from = fields.Float(string='Connection send window from', related='connection_agent_id.send_window_from', readonly=False, default=10.0)
    con_send_window_to = fields.Float(string='Connection send window to', related='connection_agent_id.send_window_to', readonly=False, default=17.0)
    con_delay_min = fields.Integer(string='Connection delay min', related='connection_agent_id.delay_min', readonly=False, default=45)
    con_delay_max = fields.Integer(string='Connection delay max', related='connection_agent_id.delay_max', readonly=False, default=120)
    con_send_note = fields.Boolean(string='Connection send note', related='connection_agent_id.send_note', readonly=False)
    con_note_instructions = fields.Text(string='Connection note instructions', related='connection_agent_id.note_instructions', readonly=False)
    con_stop_tracking_after_days = fields.Integer(string='Connection stop tracking after days', related='connection_agent_id.stop_tracking_after_days', readonly=False, default=21)
    con_follow_if_no_connect = fields.Boolean(string='Connection follow when no Connect',
                                              related='connection_agent_id.follow_if_no_connect', readonly=False)
    con_skip_if_contacted = fields.Boolean(string='Connection skip if contacted', related='connection_agent_id.skip_if_contacted', readonly=False, default=True)
    con_total_target = fields.Integer(string='Connection total target', related='connection_agent_id.total_target', readonly=False)
    con_last_run = fields.Datetime(string='Connection last run', related='connection_agent_id.last_run', readonly=True)
    con_paused_until = fields.Datetime(related='connection_agent_id.paused_until', string='Paused until')
    con_pause_reason = fields.Char(related='connection_agent_id.pause_reason')
    con_next_run = fields.Datetime(string='Connection next run', related='connection_agent_id.next_run', readonly=True)
    chat_daily_limit = fields.Integer(string='Chat daily limit', related='chat_agent_id.daily_limit', readonly=False, default=40)
    chat_first_message_delay = fields.Integer(string='Chat first message delay', related='chat_agent_id.first_message_delay', readonly=False, default=4)
    chat_step_ids = fields.One2many(string='Questionnaire steps', related='chat_agent_id.step_ids', readonly=False)
    chat_pivot_criteria = fields.Text(string='Chat pivot criteria', related='chat_agent_id.pivot_criteria', readonly=False)
    chat_pivot_min_step = fields.Integer(string='Chat pivot min step', related='chat_agent_id.pivot_min_step', readonly=False)
    chat_stop_on_negative = fields.Boolean(string='Chat stop on negative', related='chat_agent_id.stop_on_negative', readonly=False, default=True)
    chat_handoff_message = fields.Text(string='Chat handoff message', related='chat_agent_id.handoff_message', readonly=False)
    chat_meeting_link = fields.Char(string='Chat meeting link', related='chat_agent_id.meeting_link', readonly=False)
    chat_send_window_from = fields.Float(string='Chat send window from', related='chat_agent_id.send_window_from', readonly=False, default=10.0)
    chat_send_window_to = fields.Float(string='Chat send window to', related='chat_agent_id.send_window_to', readonly=False, default=18.0)
    chat_last_run = fields.Datetime(string='Chat last run', related='chat_agent_id.last_run', readonly=True)

    # Targeting notes tab (free text for the team)
    targeting_notes = fields.Html()

    @api.depends('connection_agent_id.state', 'chat_agent_id.state',
                 'connection_agent_id.has_run', 'chat_agent_id.has_run')
    def _compute_state(self):
        for persona in self:
            agents = [a for a in (persona.connection_agent_id, persona.chat_agent_id) if a]
            states = {a.state for a in agents}
            if not any(a.has_run for a in agents):
                persona.state = 'draft'
            elif 'running' in states:
                persona.state = 'active'
            elif 'paused' in states:
                persona.state = 'paused'
            else:
                persona.state = 'stopped'

    def _compute_counts(self):
        Prospect = self.env['li.prospect']
        Event = self.env['li.event']
        Lead = self.env['crm.lead'].with_context(active_test=False)
        for persona in self:
            if not persona.id:
                persona.update({'prospect_count': 0, 'accepted_count': 0, 'lead_count': 0,
                                'meeting_count': 0, 'event_count': 0})
                continue
            persona.prospect_count = Prospect.search_count([('persona_id', '=', persona.id)])
            persona.accepted_count = Prospect.search_count([('persona_id', '=', persona.id),
                                                            ('date_accepted', '!=', False)])
            persona.lead_count = Lead.search_count([('li_persona_id', '=', persona.id)])
            persona.meeting_count = Event.search_count([('persona_id', '=', persona.id),
                                                        ('event_type', '=', 'meeting_booked')])
            persona.event_count = Event.search_count([('persona_id', '=', persona.id)])

    def _compute_today(self):
        WorkItem = self.env['li.work.item'].sudo()
        for persona in self:
            if not persona.id or not persona.connection_agent_id:
                persona.invites_today = persona.messages_today = 0
                continue
            persona.invites_today = WorkItem._quota_used_today(persona, 'connection')
            persona.messages_today = WorkItem._quota_used_today(persona, 'chat')

    @api.model_create_multi
    def create(self, vals_list):
        # related agent settings cannot be written before the agents exist
        agent_vals = []
        for vals in vals_list:
            con = {k[4:]: vals.pop(k) for k in list(vals) if k.startswith('con_') and k in AGENT_FIELDS}
            chat = {k[5:]: vals.pop(k) for k in list(vals) if k.startswith('chat_') and k in AGENT_FIELDS}
            agent_vals.append((con, chat))
        personas = super().create(vals_list)
        for persona, (con, chat) in zip(personas, agent_vals):
            persona.connection_agent_id = self.env['li.connection.agent'].sudo().create(
                dict(con, persona_id=persona.id))
            persona.chat_agent_id = self.env['li.chat.agent'].sudo().create(dict(chat, persona_id=persona.id))
        return personas

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=_('%s (copy)', persona.name)) for persona, vals in zip(self, vals_list)]

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def _check_can_run_common(self):
        for persona in self:
            if persona.linkedin_profile_id.connection_state != 'connected':
                raise UserError(_('LinkedIn profile "%s" is not Connected. Connect LinkedIn on the profile first.',
                                  persona.linkedin_profile_id.name))
            if not (persona.icp_description or '').strip():
                raise UserError(_('Describe the ideal customer before running an agent.'))
            if not persona.target_working_days:
                raise UserError(_('Choose at least one target working day.'))

    def _pause_all_agents(self, reason=None):
        for persona in self:
            persona.connection_agent_id._auto_pause(reason or _('Paused'))
            persona.chat_agent_id._auto_pause(reason or _('Paused'))

    def _is_working_day(self, local_dt):
        self.ensure_one()
        return local_dt.weekday() in self.target_working_days.mapped('code')

    def _prompt_payload(self):
        """Persona block given to Claude in every work item."""
        self.ensure_one()
        service = self.service_id
        return {
            'name': self.name,
            'service': service.name,
            'service_pitch': service.description or '',
            'value_points': service.value_points or '',
            'icp': self.icp_description or '',
            'pain_points': self.pain_points or '',
            'tone': self.tone,
            'language': dict(LANGUAGES).get(self.language, self.language),
            'target_timezone': self.target_timezone,
            'signature': self.linkedin_profile_id.signature or '',
        }

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_connection_run(self):
        return self.connection_agent_id.action_run()

    def action_connection_pause(self):
        return self.connection_agent_id.action_pause()

    def action_connection_stop(self):
        return self.connection_agent_id.action_stop()

    def action_chat_run(self):
        return self.chat_agent_id.action_run()

    def action_chat_pause(self):
        return self.chat_agent_id.action_pause()

    def action_chat_stop(self):
        return self.chat_agent_id.action_stop()

    def action_pause_all(self):
        self.connection_agent_id.action_pause()
        self.chat_agent_id.action_pause()
        return True

    def action_stop_all(self):
        self.connection_agent_id.action_stop()
        self.chat_agent_id.action_stop()
        return True

    def _open(self, name, model, domain, views='list,form', context=None):
        return {'type': 'ir.actions.act_window', 'name': name, 'res_model': model,
                'view_mode': views, 'domain': domain, 'context': context or {}}

    def action_open_prospects(self):
        self.ensure_one()
        return self._open(_('Prospects'), 'li.prospect', [('persona_id', '=', self.id)],
                          'list,kanban,form', {'default_persona_id': self.id})

    def action_open_accepted(self):
        self.ensure_one()
        return self._open(_('Accepted'), 'li.prospect', [('persona_id', '=', self.id),
                                                         ('date_accepted', '!=', False)], 'list,kanban,form')

    def action_open_leads(self):
        self.ensure_one()
        return self._open(_('Warm leads'), 'crm.lead', [('li_persona_id', '=', self.id)], 'list,kanban,form',
                          {'active_test': False})

    def action_open_meetings(self):
        self.ensure_one()
        lead_ids = self.env['crm.lead'].with_context(active_test=False).search(
            [('li_persona_id', '=', self.id)]).ids
        return self._open(_('Meetings'), 'calendar.event', [('opportunity_id', 'in', lead_ids)],
                          'list,calendar,form')

    def action_open_events(self):
        self.ensure_one()
        return self._open(_('Activity'), 'li.event', [('persona_id', '=', self.id)], 'list,pivot,graph')
