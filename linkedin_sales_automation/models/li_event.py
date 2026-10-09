from markupsafe import Markup, escape

from odoo import api, fields, models

from .li_common import AGENT_TYPES, EVENT_TYPES, utc_now

HIGHLIGHT_EVENTS = ('warm_lead', 'meeting_booked')


class LiMessage(models.Model):
    _name = 'li.message'
    _description = 'LinkedIn Message'
    _order = 'date, id'

    prospect_id = fields.Many2one('li.prospect', required=True, ondelete='cascade', index=True)
    persona_id = fields.Many2one(related='prospect_id.persona_id', store=True, index=True)
    direction = fields.Selection([('in', 'Received'), ('out', 'Sent')], required=True)
    kind = fields.Selection([
        ('note', 'Invite note'),
        ('message', 'Message'),
        ('followup', 'Follow-up'),
        ('handoff', 'Handoff'),
        ('manual', 'Written by hand'),
        ('reply', 'Reply'),
    ], default='message')
    body = fields.Text(required=True)
    step_id = fields.Many2one('li.chat.step', ondelete='set null')
    followup_step_id = fields.Many2one('li.followup.step', ondelete='set null')
    ai_generated = fields.Boolean()
    date = fields.Datetime(default=fields.Datetime.now, index=True)
    linkedin_message_id = fields.Char()
    state = fields.Selection([('queued', 'Queued'), ('sent', 'Sent'), ('failed', 'Failed')], default='sent')
    sender_name = fields.Char()
    seen_in_thread = fields.Boolean(help='Matched in a thread read from LinkedIn.')
    work_item_id = fields.Many2one('li.work.item', ondelete='set null')

    def _payload(self):
        self.ensure_one()
        return {
            'from': 'us' if self.direction == 'out' else 'prospect',
            'text': self.body,
            'sent_at': self.date and self.date.replace(microsecond=0).isoformat() + 'Z',
        }


class LiEvent(models.Model):
    _name = 'li.event'
    _description = 'LinkedIn agent event'
    _order = 'date desc, id desc'
    _rec_name = 'event_type'

    date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    event_type = fields.Selection(EVENT_TYPES, required=True, index=True)
    agent_type = fields.Selection(AGENT_TYPES, required=True, index=True)
    persona_id = fields.Many2one('li.persona', index=True, ondelete='cascade')
    linkedin_profile_id = fields.Many2one('li.profile', index=True, ondelete='cascade', string='LinkedIn Profile')
    service_id = fields.Many2one('li.service', index=True, ondelete='set null')
    prospect_id = fields.Many2one('li.prospect', index=True, ondelete='set null')
    crm_lead_id = fields.Many2one('crm.lead', index=True, ondelete='set null', string='CRM lead')
    detail = fields.Text()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.uid)
    company_id = fields.Many2one('res.company', index=True)
    without_invite = fields.Boolean(
        string='Already connected',
        help='Accepted without an invitation from Odoo: the person was already a 1st-degree connection. '
             'Not counted as an accepted invite on the dashboard.')

    def init(self):
        # dashboard filters: event_type + date range (section 8, ~100k rows)
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS li_event_type_date_idx ON li_event (event_type, date);
            CREATE INDEX IF NOT EXISTS li_event_prospect_type_idx ON li_event (prospect_id, event_type);
        """)
        # one-time backfill of rows logged before without_invite existed (NULL): an acceptance
        # with no earlier invite to the same prospect was an existing connection
        self.env.cr.execute("""
            UPDATE li_event e SET without_invite = NOT EXISTS (
                SELECT 1 FROM li_event s WHERE s.prospect_id = e.prospect_id
                   AND s.event_type = 'invite_sent' AND s.date <= e.date)
             WHERE e.without_invite IS NULL AND e.event_type = 'invite_accepted' AND e.prospect_id IS NOT NULL;
            UPDATE li_event SET without_invite = FALSE WHERE without_invite IS NULL;
        """)

    @api.model
    def _ai_partner(self):
        return self.env.ref('linkedin_sales_automation.partner_ai_agent', raise_if_not_found=False)

    @api.model
    def _log(self, event_type, agent_type, persona=None, prospect=None, lead=None, detail='',
             persona_body=None, prospect_body=None, lead_body=None, author_user=False, date=None):
        """Write one li.event row and the matching chatter notes.

        Notes are authored by the "AI Agent" partner so they stand apart from
        human notes; author_user=True posts as the current user instead.
        """
        persona = persona or (prospect and prospect.persona_id) or self.env['li.persona']
        event = self.sudo().create({
            'date': date or utc_now(),
            'event_type': event_type,
            'agent_type': agent_type,
            'persona_id': persona.id or False,
            'linkedin_profile_id': persona.linkedin_profile_id.id or False,
            'service_id': persona.service_id.id or False,
            'prospect_id': prospect.id if prospect else False,
            'crm_lead_id': lead.id if lead else False,
            'detail': detail,
            'company_id': persona.company_id.id or False,
        })
        author = {} if author_user else {'author_id': self._ai_partner().id}
        label = dict(AGENT_TYPES).get(agent_type, '')
        for record, body in ((persona, persona_body), (prospect, prospect_body), (lead, lead_body)):
            if record and body:
                html = escape(body)
                if event_type in HIGHLIGHT_EVENTS:
                    html = Markup('<div class="alert alert-success mb-0 p-2">%s</div>') % html
                    if lead and record != lead:
                        html += Markup('<p>%s</p>') % lead._get_html_link()
                record.sudo().message_post(
                    body=Markup('<b>%s</b> · %s') % (label, html),
                    message_type='comment', subtype_xmlid='mail.mt_note', **author)
        return event
