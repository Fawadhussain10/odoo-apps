from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .li_common import AGENT_STATES, utc_now

MAX_CONSECUTIVE_ERRORS = 3


class LiAgentMixin(models.AbstractModel):
    """State machine shared by the four agents (Run / Pause / Stop)."""
    _name = 'li.agent.mixin'
    _description = 'LinkedIn agent (shared behaviour)'
    _agent_type = None
    _agent_label = None

    state = fields.Selection(AGENT_STATES, default='stopped', required=True, readonly=True, copy=False)
    has_run = fields.Boolean(readonly=True, copy=False)
    consecutive_errors = fields.Integer(readonly=True, copy=False)
    last_run = fields.Datetime(readonly=True, copy=False)
    next_run = fields.Datetime(readonly=True, copy=False)
    limit_notice_date = fields.Date(readonly=True, copy=False,
                                    help='Day on which the "daily limit reached" note was posted.')
    paused_until = fields.Datetime(readonly=True, copy=False,
                                   help='Paused automatically until this time (e.g. LinkedIn weekly invitation '
                                        'limit); runs again by itself then.')
    pause_reason = fields.Char(readonly=True, copy=False)

    def _agent_persona(self):
        """Persona the agent belongs to (False for shared agents)."""
        return self.env['li.persona']

    def _check_can_run(self):
        """Raise UserError with a clear message when Run is not allowed."""
        return True

    def _on_stop(self):
        """Hook: clear the queue of the agent."""
        return True

    def _log_state(self, event_type, detail=None, by_user=True):
        Event = self.env['li.event']
        for agent in self:
            persona = agent._agent_persona()
            label = agent._agent_label
            verb = {'agent_started': _('started'), 'agent_paused': _('paused'),
                    'agent_stopped': _('stopped')}[event_type]
            if by_user and not self.env.su:
                line = _('%(agent)s %(verb)s by %(user)s', agent=label, verb=verb, user=self.env.user.name)
            else:
                line = _('%(agent)s %(verb)s', agent=label, verb=verb)
            if detail:
                line = '%s — %s' % (line, detail)
            Event._log(event_type, agent._agent_type, persona=persona, detail=line,
                       persona_body=line, author_user=by_user and not self.env.su)
            if not persona:
                agent.message_post(body=line)

    def action_run(self):
        for agent in self:
            if agent.state == 'running':
                continue
            agent._check_can_run()
            vals = {'state': 'running', 'has_run': True, 'consecutive_errors': 0, 'last_run': utc_now(),
                    'paused_until': False, 'pause_reason': False}
            agent.write(vals)
            persona = agent._agent_persona()
            if persona and not persona.date_activated:
                persona.date_activated = utc_now()
            agent._log_state('agent_started')
        return True

    def action_pause(self):
        for agent in self.filtered(lambda a: a.state == 'running'):
            agent.state = 'paused'
            agent._log_state('agent_paused')
        return True

    def action_stop(self):
        for agent in self.filtered(lambda a: a.state != 'stopped'):
            agent.state = 'stopped'
            agent._on_stop()
            agent._log_state('agent_stopped')
        return True

    def _auto_pause(self, reason):
        for agent in self.filtered(lambda a: a.state == 'running'):
            agent.sudo().state = 'paused'
            agent.sudo()._log_state('agent_paused', detail=reason, by_user=False)

    def _pause_until(self, until, reason):
        """Pause running agents until `until` (naive UTC); _cron_resume_agents runs them again."""
        agents = self.filtered(lambda a: a.state == 'running')
        agents._auto_pause(reason)
        agents.sudo().write({'paused_until': until, 'pause_reason': reason})
        return agents

    @api.model
    def _resume_due(self):
        """Run again the agents whose timed pause is over."""
        agents = self.sudo().search([('state', '=', 'paused'), ('paused_until', '!=', False),
                                     ('paused_until', '<=', utc_now())])
        for agent in agents:
            persona = agent._agent_persona()
            if persona and persona.linkedin_profile_id.connection_state != 'connected':
                continue
            agent.write({'state': 'running', 'paused_until': False, 'pause_reason': False,
                         'consecutive_errors': 0})
            agent._log_state('agent_started', detail=_('timed pause over'), by_user=False)
        return agents

    def _register_success(self):
        self.filtered('consecutive_errors').sudo().write({'consecutive_errors': 0})

    def _register_error(self, error):
        """Count consecutive failures; after 3, pause the agent and schedule an
        activity for the persona owner."""
        for agent in self.sudo():
            agent.consecutive_errors += 1
            if agent.consecutive_errors >= MAX_CONSECUTIVE_ERRORS and agent.state == 'running':
                agent._auto_pause(_('%s consecutive errors, last: %s', agent.consecutive_errors, error))
                target = agent._agent_persona() or agent
                owner = agent._error_owner()
                target.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=owner.id,
                    summary=_('%s paused after errors', agent._agent_label),
                    note=_('The agent was paused after %(n)s consecutive errors. Last error: %(e)s',
                           n=agent.consecutive_errors, e=error))

    def _error_owner(self):
        persona = self._agent_persona()
        if persona:
            return persona.salesperson_id or persona.linkedin_profile_id.owner_id or self.env.user
        return self.env.ref('base.user_admin', raise_if_not_found=False) or self.env.user


class LiConnectionAgent(models.Model):
    _name = 'li.connection.agent'
    _description = 'Connection Agent'
    _inherit = ['li.agent.mixin']
    _agent_type = 'connection'
    _agent_label = 'Connection Agent'

    persona_id = fields.Many2one('li.persona', required=True, ondelete='cascade', index=True)
    name = fields.Char(related='persona_id.name')
    daily_limit = fields.Integer(required=True, default=15, help='Invites per day for this persona. Hard limit.')
    weekly_limit = fields.Integer(help='Optional extra cap over the last 7 local days. 0 = none.')
    send_window_from = fields.Float(default=10.0)
    send_window_to = fields.Float(default=17.0)
    delay_min = fields.Integer('Delay min (s)', required=True, default=45)
    delay_max = fields.Integer('Delay max (s)', required=True, default=120)
    send_note = fields.Boolean('Send note with invite')
    note_instructions = fields.Text()
    stop_tracking_after_days = fields.Integer('Withdraw pending after (days)', default=21)
    skip_if_contacted = fields.Boolean('Skip contacted people', required=True, default=True)
    follow_if_no_connect = fields.Boolean('Follow when no Connect', default=True,
                                          help='LinkedIn offers no Connect button for some people (follow-only '
                                               'profiles): follow them instead. Follows do not count as invites.')
    total_target = fields.Integer('Stop after total', help='Stop automatically after N invites. 0 = no limit.')
    search_page = fields.Integer(default=0, readonly=True, copy=False,
                                 help='Next result page to ask for in search_prospects items.')
    last_search_date = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        ('persona_uniq', 'unique(persona_id)', 'A persona has one Connection Agent.'),
        ('limits_positive', 'CHECK(daily_limit >= 0 AND delay_min >= 0 AND delay_max >= delay_min)',
         'Limits must be positive and delay max ≥ delay min.'),
    ]

    @api.depends('persona_id')
    def _compute_display_name(self):
        for agent in self:
            agent.display_name = _('Connection Agent — %s', agent.persona_id.name or '')

    def _agent_persona(self):
        return self.persona_id

    def _check_can_run(self):
        self.persona_id._check_can_run_common()
        if self.send_note and not (self.note_instructions or '').strip():
            raise UserError(_('Write the note instructions or untick "Send note with invite".'))

    def _on_stop(self):
        """Stop clears queued prospects not yet invited (they return to the pool)
        and cancels released invite / search items."""
        self.env['li.work.item'].sudo()._cancel_open(
            [('persona_id', '=', self.persona_id.id), ('agent_type', '=', 'connection')],
            reason=_('Connection Agent stopped'))
        queued = self.env['li.prospect'].sudo().search([('persona_id', '=', self.persona_id.id),
                                                        ('stage', '=', 'queued')])
        queued.unlink()



class LiChatAgent(models.Model):
    _name = 'li.chat.agent'
    _description = 'Chat Agent'
    _inherit = ['li.agent.mixin']
    _agent_type = 'chat'
    _agent_label = 'Chat Agent'

    persona_id = fields.Many2one('li.persona', required=True, ondelete='cascade', index=True)
    name = fields.Char(related='persona_id.name')
    daily_limit = fields.Integer(required=True, default=40, help='Outbound messages per day. Hard limit.')
    first_message_delay = fields.Integer('First message delay (h)', required=True, default=4)
    step_ids = fields.One2many('li.chat.step', 'chat_agent_id', 'Questionnaire sequence', copy=True)
    pivot_criteria = fields.Text()
    pivot_min_step = fields.Integer(help='Earliest step number (1 = first step) at which the pivot may fire.')
    stop_on_negative = fields.Boolean(required=True, default=True)
    handoff_message = fields.Text()
    meeting_link = fields.Char()
    send_window_from = fields.Float(required=True, default=10.0)
    send_window_to = fields.Float(required=True, default=18.0)

    _sql_constraints = [
        ('persona_uniq', 'unique(persona_id)', 'A persona has one Chat Agent.'),
        ('limit_positive', 'CHECK(daily_limit >= 0)', 'The daily limit must be positive.'),
    ]

    @api.depends('persona_id')
    def _compute_display_name(self):
        for agent in self:
            agent.display_name = _('Chat Agent — %s', agent.persona_id.name or '')

    def _agent_persona(self):
        return self.persona_id

    def _check_can_run(self):
        self.persona_id._check_can_run_common()
        if not self.step_ids:
            raise UserError(_('Add at least one questionnaire step before running the Chat Agent.'))
        if not (self.pivot_criteria or '').strip():
            raise UserError(_('Set the pivot criteria before running the Chat Agent.'))

    def _on_stop(self):
        self.env['li.work.item'].sudo()._cancel_open(
            [('persona_id', '=', self.persona_id.id), ('agent_type', '=', 'chat')],
            reason=_('Chat Agent stopped'))



class LiChatStep(models.Model):
    _name = 'li.chat.step'
    _description = 'Chat Agent questionnaire step'
    _order = 'chat_agent_id, sequence, id'

    chat_agent_id = fields.Many2one('li.chat.agent', required=True, ondelete='cascade', index=True)
    persona_id = fields.Many2one(related='chat_agent_id.persona_id', store=True)
    sequence = fields.Integer(default=10)
    step_number = fields.Integer(compute='_compute_step_number')
    name = fields.Char(required=True)
    objective = fields.Text(help='What this message must learn — Claude uses it.')
    template = fields.Text(help='Base message. Placeholders: {first_name}, {company}, {service}')
    ai_personalise = fields.Boolean('AI personalise', default=True)
    trigger = fields.Selection([('after_accept', 'After accept'), ('after_reply', 'After reply')],
                               required=True, default='after_reply')
    wait_days = fields.Integer(help='Optional delay before sending.')
    is_question = fields.Boolean('Question', default=True)
    template_id = fields.Many2one('li.message.template', 'Load from template')

    def _compute_step_number(self):
        for step in self:
            ordered = step.chat_agent_id.step_ids.sorted(lambda s: (s.sequence, s.id))
            step.step_number = (ordered.ids.index(step.id) + 1) if step.id in ordered.ids else 0

    @api.onchange('template_id')
    def _onchange_template_id(self):
        tmpl = self.template_id
        if tmpl:
            self.update({'name': tmpl.name, 'objective': tmpl.objective, 'template': tmpl.template,
                         'trigger': tmpl.trigger, 'is_question': tmpl.is_question})
