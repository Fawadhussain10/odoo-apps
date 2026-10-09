from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .li_common import utc_now


class LiFollowupAgent(models.Model):
    _name = 'li.followup.agent'
    _description = 'Follow-up Agent'
    _inherit = ['li.agent.mixin', 'mail.thread', 'mail.activity.mixin']
    _agent_type = 'followup'
    _agent_label = 'Follow-up Agent'

    name = fields.Char(default='Follow-up Agent', required=True)
    daily_limit = fields.Integer(required=True, default=60,
                                 help='Follow-up messages across all personas, counted over a rolling 24 hours.')
    persona_ids = fields.Many2many('li.persona', string='Applies to',
                                   help='Empty = all active personas.')
    send_window_from = fields.Float(required=True, default=10.0)
    send_window_to = fields.Float(required=True, default=17.0)
    max_followups = fields.Integer(required=True, default=3, help='Maximum follow-ups per prospect.')
    on_reply = fields.Selection([('return_to_chat', 'Back to Chat Agent'), ('stop', 'Stop the sequence')],
                                required=True, default='return_to_chat')
    step_ids = fields.One2many('li.followup.step', 'agent_id', 'Follow-up sequence')
    sent_today = fields.Integer('Sent (last 24 h)', compute='_compute_sent_today')

    def _compute_sent_today(self):
        used = self.env['li.work.item'].sudo()._followup_used()
        for agent in self:
            agent.sent_today = used

    @api.model
    def _get(self):
        agent = self.env.ref('linkedin_sales_automation.followup_agent_main', raise_if_not_found=False)
        return agent.sudo() if agent else self.sudo().search([], limit=1)

    def _check_can_run(self):
        if not self.step_ids:
            raise UserError(_('Add at least one follow-up step before running the Follow-up Agent.'))

    def _on_stop(self):
        self.env['li.work.item'].sudo()._cancel_open([('agent_type', '=', 'followup')],
                                                     reason=_('Follow-up Agent stopped'))

    def _covers(self, persona):
        if self.persona_ids:
            return persona in self.persona_ids and persona.state != 'stopped'
        return persona.state == 'active'

    def _ordered_steps(self):
        return self.step_ids.sorted(lambda s: (s.sequence, s.id))


class LiFollowupStep(models.Model):
    _name = 'li.followup.step'
    _description = 'Follow-up step'
    _order = 'agent_id, sequence, id'

    agent_id = fields.Many2one('li.followup.agent', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    wait_days = fields.Integer('Send after no reply for (days)', required=True, default=3)
    template = fields.Text(help='Placeholders: {first_name}, {company}, {service}')
    ai_personalise = fields.Boolean('AI personalise', default=True)


class LiActivityAgent(models.Model):
    _name = 'li.activity.agent'
    _description = 'Activity Agent'
    _inherit = ['li.agent.mixin', 'mail.thread', 'mail.activity.mixin']
    _agent_type = 'activity'
    _agent_label = 'Activity Agent'

    name = fields.Char(default='Activity Agent', required=True)
    # not "activity_type_id": mail.activity.mixin already defines that name
    reply_activity_type_id = fields.Many2one(
        'mail.activity.type', 'Activity type', required=True,
        default=lambda self: self.env.ref('linkedin_sales_automation.mail_activity_type_li_reply',
                                          raise_if_not_found=False))
    deadline_hours = fields.Integer(required=True, default=48)
    assign_to = fields.Selection([
        ('lead_salesperson', 'Salesperson on the lead'),
        ('persona_salesperson', 'Salesperson of the persona'),
        ('profile_owner', 'Owner of the LinkedIn profile'),
    ], required=True, default='lead_salesperson')
    auto_done = fields.Boolean('Mark done automatically on reply', required=True, default=True)
    note_template = fields.Text(default='{prospect} replied: {reply}',
                                help='Placeholders: {prospect}, {reply} (first 200 characters), {persona}')
    reply_prospect_ids = fields.Many2many('li.prospect', compute='_compute_reply_prospects',
                                          string='Reply activities')

    @api.model
    def _get(self):
        agent = self.env.ref('linkedin_sales_automation.activity_agent_main', raise_if_not_found=False)
        return agent.sudo() if agent else self.sudo().search([], limit=1)

    def _compute_reply_prospects(self):
        prospects = self.env['li.prospect'].search(
            ['|', ('reply_activity_id', '!=', False), ('reply_activity_date', '!=', False),
             ('is_taken_over', '=', True)], order='reply_due_at desc', limit=50)
        for agent in self:
            agent.reply_prospect_ids = prospects

    def _assignee(self, prospect):
        self.ensure_one()
        lead_user = prospect.crm_lead_id.user_id
        persona = prospect.persona_id
        owner = persona.linkedin_profile_id.owner_id
        if self.assign_to == 'lead_salesperson':
            return lead_user or prospect.taken_over_by or persona.salesperson_id or owner
        if self.assign_to == 'persona_salesperson':
            return persona.salesperson_id or lead_user or owner
        return owner

    def _check_can_run(self):
        if not self.reply_activity_type_id:
            raise UserError(_('Choose the activity type.'))
