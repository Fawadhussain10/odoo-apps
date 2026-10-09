import json

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .li_common import CLOSED_STAGES, PROSPECT_STAGES, linkedin_username, normalize_profile_url, utc_now


class LiProspect(models.Model):
    _name = 'li.prospect'
    _description = 'LinkedIn Prospect'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'write_date desc, id desc'

    name = fields.Char(required=True, tracking=True)
    headline = fields.Char()
    title = fields.Char()
    company = fields.Char()
    location = fields.Char()
    linkedin_url = fields.Char('LinkedIn URL', required=True, index=True)
    linkedin_username = fields.Char(index=True, readonly=True)
    linkedin_member_id = fields.Char('LinkedIn member ID')
    persona_id = fields.Many2one('li.persona', required=True, index=True, ondelete='cascade', tracking=True)
    linkedin_profile_id = fields.Many2one(related='persona_id.linkedin_profile_id', store=True, index=True,
                                          string='LinkedIn Profile')
    service_id = fields.Many2one(related='persona_id.service_id', store=True, index=True)
    company_id = fields.Many2one(related='persona_id.company_id', store=True, index=True, string='Odoo company')
    stage = fields.Selection(PROSPECT_STAGES, required=True, default='queued', index=True, tracking=True,
                             group_expand='_group_expand_stage')
    current_step_id = fields.Many2one('li.chat.step', 'Current step', ondelete='set null',
                                      help='Last questionnaire step sent.')
    date_invited = fields.Datetime(readonly=True)
    date_accepted = fields.Datetime(readonly=True)
    date_first_message = fields.Datetime(readonly=True)
    date_first_reply = fields.Datetime(readonly=True)
    date_warm = fields.Datetime(readonly=True)
    answers = fields.Text(help='JSON: {step name: answer} extracted by Claude.')
    answers_display = fields.Text('Extracted answers', compute='_compute_answers_display')
    ai_summary = fields.Text('AI summary')
    crm_lead_id = fields.Many2one('crm.lead', 'CRM lead', ondelete='set null', index=True)
    message_ids_li = fields.One2many('li.message', 'prospect_id', 'Conversation')
    is_taken_over = fields.Boolean('Taken over', readonly=True, index=True, tracking=True)
    taken_over_by = fields.Many2one('res.users', readonly=True)
    date_taken_over = fields.Datetime(readonly=True)
    takeover_reason = fields.Selection([
        ('manual', 'Take over button'),
        ('pivot', 'Pivot'),
        ('human_message', 'Message written by hand'),
    ], readonly=True)
    followup_count = fields.Integer(readonly=True)
    last_outbound_date = fields.Datetime(readonly=True)
    last_inbound_date = fields.Datetime(readonly=True)
    awaiting_reply = fields.Boolean(readonly=True,
                                    help='The last message of the thread is ours: no reply since (set by message '
                                         'order, not by LinkedIn timestamps).')
    next_followup_date = fields.Datetime(readonly=True)
    next_message_date = fields.Datetime('Next step due', readonly=True,
                                        help='When the next questionnaire step may be sent.')
    last_activity_date = fields.Datetime('Last activity', readonly=True, index=True)
    reply_activity_id = fields.Many2one('mail.activity', 'Open reply activity', ondelete='set null', readonly=True)
    reply_activity_date = fields.Datetime(readonly=True, help='When the open reply activity was created.')
    reply_due_at = fields.Datetime('Reply due', readonly=True, help='Exact due time of the open reply activity.')
    reply_overdue_logged = fields.Boolean(readonly=True)
    reply_overdue = fields.Boolean(compute='_compute_reply_overdue', search='_search_reply_overdue')

    # engine flags
    needs_analysis = fields.Boolean(readonly=True, help='New reply waiting for li_record_analysis.')
    handoff_pending = fields.Boolean(readonly=True)
    do_not_contact = fields.Boolean('Do not contact', readonly=True, index=True, tracking=True,
                                    help='Never contacted again by any persona.')
    needs_check = fields.Boolean('Needs a person to check', readonly=True, tracking=True,
                                 help='A send with unknown outcome (retry_safe false or expired after '
                                      'confirmation). No automatic send until cleared.')
    needs_check_reason = fields.Char(readonly=True)
    invite_without_note = fields.Boolean(readonly=True)
    send_attempts = fields.Integer(readonly=True, help='Failed send attempts in a row.')
    sequence_stopped = fields.Boolean(readonly=True, help='The Chat Agent will not send further steps.')
    last_sentiment = fields.Selection([('positive', 'Positive'), ('neutral', 'Neutral'),
                                       ('negative', 'Negative'), ('opt_out', 'Opt-out')], readonly=True)
    message_count_li = fields.Integer(compute='_compute_message_count_li')
    conversation_html = fields.Html('Conversation view', compute='_compute_conversation_html', sanitize=False)

    _sql_constraints = [
        ('persona_url_uniq', 'unique(persona_id, linkedin_url)', 'This person is already a prospect of the persona.'),
    ]

    @api.model
    def _group_expand_stage(self, stages, domain):
        return [key for key, _label in PROSPECT_STAGES]

    @api.depends('answers')
    def _compute_answers_display(self):
        for prospect in self:
            prospect.answers_display = prospect._answers_text()

    def _answers_dict(self):
        self.ensure_one()
        try:
            data = json.loads(self.answers or '{}')
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _answers_text(self):
        data = self._answers_dict()
        return '\n'.join('%s: %s' % (k, v) for k, v in data.items())

    @api.depends('message_ids_li.body', 'message_ids_li.direction')
    def _compute_conversation_html(self):
        for prospect in self:
            parts = []
            for msg in prospect.message_ids_li.sorted(lambda m: (m.date or m.create_date, m.id)):
                out = msg.direction == 'out'
                who = (_('AI') if msg.ai_generated else _('Rep')) if out else ''
                css = 'o_li_bubble_out' if out else 'o_li_bubble_in'
                style = ('margin-left:auto;background:#e7f1ff;border:1px solid #9ec5fe;' if out
                         else 'margin-right:auto;background:#f1f3f5;border:1px solid #dee2e6;')
                if out and not msg.ai_generated:
                    style = 'margin-left:auto;background:#fdecea;border:1px solid #f5c2c7;'
                parts.append(Markup(
                    '<div class="%s" style="%sborder-radius:12px;padding:6px 10px;margin:4px 0;max-width:80%%;'
                    'width:fit-content;white-space:pre-wrap">%s%s<div class="text-muted small">%s</div></div>') % (
                    css, style, Markup('<b>%s: </b>') % who if who else '', msg.body,
                    fields.Datetime.to_string(msg.date) if msg.date else ''))
            prospect.conversation_html = Markup('').join(parts) if parts else Markup(
                '<p class="text-muted">%s</p>') % _('No messages yet.')

    def _compute_message_count_li(self):
        for prospect in self:
            prospect.message_count_li = len(prospect.message_ids_li)

    @api.depends('reply_due_at', 'reply_activity_id')
    def _compute_reply_overdue(self):
        now = utc_now()
        for prospect in self:
            prospect.reply_overdue = bool(prospect.reply_activity_id and prospect.reply_due_at
                                          and prospect.reply_due_at < now)

    def _search_reply_overdue(self, operator, value):
        positive = (operator == '=') == bool(value)
        domain = [('reply_activity_id', '!=', False), ('reply_due_at', '<', utc_now())]
        if positive:
            return domain
        return ['|', ('reply_activity_id', '=', False), ('reply_due_at', '>=', utc_now())]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('linkedin_url'):
                vals['linkedin_url'] = normalize_profile_url(vals['linkedin_url'], vals.get('linkedin_username'))
                vals['linkedin_username'] = linkedin_username(vals['linkedin_url'])
            vals.setdefault('last_activity_date', utc_now())
        return super().create(vals_list)

    def write(self, vals):
        if 'linkedin_url' in vals:
            vals['linkedin_url'] = normalize_profile_url(vals['linkedin_url'])
            vals['linkedin_username'] = linkedin_username(vals['linkedin_url'])
        if vals.get('stage') == 'do_not_contact':
            vals['do_not_contact'] = True
        if 'stage' in vals and 'last_activity_date' not in vals:
            vals['last_activity_date'] = utc_now()
        return super().write(vals)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _first_name(self):
        self.ensure_one()
        return (self.name or '').split(' ')[0]

    def _is_closed(self):
        self.ensure_one()
        return self.stage in CLOSED_STAGES

    def _payload(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'first_name': self._first_name(),
            'headline': self.headline or '',
            'title': self.title or '',
            'company': self.company or '',
            'location': self.location or '',
            'linkedin_url': self.linkedin_url,
            'username': self.linkedin_username or '',
            'profile': self.profile_text or '',
        }

    def _situation_payload(self):
        """Where the conversation stands: who spoke last, what we already sent,
        the last analysis. Claude reads it with the conversation before writing."""
        self.ensure_one()
        msgs = self.message_ids_li.sorted(lambda m: (m.date or m.create_date, m.id))
        ours = msgs.filtered(lambda m: m.direction == 'out' and m.kind != 'note')
        theirs = msgs.filtered(lambda m: m.direction == 'in')
        return {
            'messages_from_us': len(ours),
            'replies_from_prospect': len(theirs),
            'last_message_from': ('us' if msgs[-1].direction == 'out' else 'prospect') if msgs else 'nobody',
            'our_last_message': ours[-1].body if ours else '',
            'their_last_reply': theirs[-1].body if theirs else '',
            'last_reply_nature': self.last_sentiment or '',
            'summary_so_far': self.ai_summary or '',
            'current_step': self.current_step_id.name or '',
        }

    def _conversation_payload(self, limit=30):
        self.ensure_one()
        msgs = self.message_ids_li.sorted(lambda m: (m.date or m.create_date, m.id))
        return [m._payload() for m in msgs[-limit:]]

    def _owner_user(self):
        self.ensure_one()
        persona = self.persona_id
        return self.crm_lead_id.user_id or persona.salesperson_id or persona.linkedin_profile_id.owner_id

    # ------------------------------------------------------------------
    # Takeover (6.6)
    # ------------------------------------------------------------------
    def _take_over(self, user=None, reason='manual'):
        Event = self.env['li.event']
        WorkItem = self.env['li.work.item'].sudo()
        for prospect in self.sudo():
            if prospect.is_taken_over:
                continue
            user = user or prospect._owner_user() or self.env.user
            prospect.write({'is_taken_over': True, 'taken_over_by': user.id, 'date_taken_over': utc_now(),
                            'takeover_reason': reason, 'next_followup_date': False})
            # cancel queued Chat Agent and Follow-up Agent messages for this prospect only
            WorkItem._cancel_open([('prospect_id', '=', prospect.id),
                                   ('work_type', 'in', ('invite', 'message', 'followup', 'analyse'))],
                                  reason=_('prospect taken over'), stale=True)
            why = {'manual': '', 'pivot': _(' at pivot'),
                   'human_message': _(' (a message written by hand was detected)')}[reason]
            line = _('%(user)s took over %(name)s%(why)s — agents stopped for this prospect',
                     user=user.name, name=prospect.name, why=why)
            Event._log('taken_over', 'system', persona=prospect.persona_id, prospect=prospect,
                       lead=prospect.crm_lead_id, detail=line, persona_body=line, prospect_body=line)

    def action_take_over(self):
        self._take_over(user=self.env.user, reason='manual')
        return True

    def action_return_to_agents(self):
        if not self.env.user.has_group('linkedin_sales_automation.group_li_manager'):
            raise UserError(_('Only a LinkedIn Sales Manager can return a prospect to the agents.'))
        for prospect in self.sudo().filtered('is_taken_over'):
            prospect.write({'is_taken_over': False, 'taken_over_by': False, 'date_taken_over': False,
                            'takeover_reason': False})
            line = _('%(user)s returned %(name)s to the agents — the Chat Agent resumes from the current step',
                     user=self.env.user.name, name=prospect.name)
            prospect.message_post(body=line)
            prospect.persona_id.message_post(body=line)
        return True

    def action_do_not_contact(self):
        WorkItem = self.env['li.work.item'].sudo()
        for prospect in self.sudo():
            prospect.write({'stage': 'do_not_contact', 'do_not_contact': True, 'needs_analysis': False,
                            'handoff_pending': False})
            WorkItem._cancel_open([('prospect_id', '=', prospect.id)], reason=_('marked do-not-contact'))
            prospect.message_post(body=_('Marked do-not-contact by %s. No persona will contact this person again.',
                                         self.env.user.name))
        return True

    def action_clear_check(self):
        self.sudo().write({'needs_check': False, 'needs_check_reason': False, 'send_attempts': 0})
        for prospect in self:
            prospect.message_post(body=_('Checked by %s — automatic sending allowed again.', self.env.user.name))
        return True

    def action_push_to_crm(self):
        """Manual pivot."""
        for prospect in self:
            prospect.sudo()._pivot(reason=_('Pushed to CRM by %s', self.env.user.name), manual=True)
        return True

    def action_open_lead(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'crm.lead', 'res_id': self.crm_lead_id.id,
                'view_mode': 'form'}

    # ------------------------------------------------------------------
    # Pivot -> CRM lead (6.3)
    # ------------------------------------------------------------------
    def _find_existing_lead(self):
        """One CRM lead per LinkedIn URL across all personas."""
        self.ensure_one()
        Lead = self.env['crm.lead'].sudo().with_context(active_test=False)
        if self.crm_lead_id:
            return self.crm_lead_id.sudo()
        if self.linkedin_username:
            lead = Lead.search([('li_prospect_id.linkedin_username', '=', self.linkedin_username)],
                               order='id', limit=1)
            if lead:
                return lead
        return Lead.search([('website', '=', self.linkedin_url)], order='id', limit=1)

    def _lead_description(self):
        self.ensure_one()
        parts = [Markup('<p><b>%s</b> <a href="%s">%s</a></p>') % (_('LinkedIn:'), self.linkedin_url,
                                                                   self.linkedin_url)]
        if self.ai_summary:
            parts.append(Markup('<p><b>%s</b><br/>%s</p>') % (_('AI summary'), self.ai_summary))
        answers = self._answers_dict()
        if answers:
            rows = Markup('').join(Markup('<li><b>%s:</b> %s</li>') % (k, v) for k, v in answers.items())
            parts.append(Markup('<p><b>%s</b></p><ul>%s</ul>') % (_('Answers per question'), rows))
        last = self.message_ids_li.sorted(lambda m: (m.date or m.create_date, m.id))[-5:]
        if last:
            rows = Markup('').join(Markup('<li><i>%s</i>: %s</li>') % (
                self.persona_id.linkedin_profile_id.my_display_name if m.direction == 'out' else self.name,
                m.body) for m in last)
            parts.append(Markup('<p><b>%s</b></p><ul>%s</ul>') % (_('Last messages'), rows))
        return Markup('').join(parts)

    def _pivot(self, reason, manual=False):
        """Warm lead: create (or reuse) the CRM lead, take the prospect over and
        queue the handoff message. Returns the lead."""
        self.ensure_one()
        prospect = self.sudo()
        persona = prospect.persona_id
        service = persona.service_id
        chat = persona.chat_agent_id
        Event = self.env['li.event']
        lead = prospect._find_existing_lead()
        company = persona.company_id
        in_company = lambda user: user and (not company or company in user.company_ids)
        salesperson = persona.salesperson_id if in_company(persona.salesperson_id) else self.env['res.users']
        profile_owner = persona.linkedin_profile_id.owner_id
        profile_owner = profile_owner if in_company(profile_owner) else self.env['res.users']
        if lead:
            created = False
            line = _('Pivot reached again (%(persona)s): %(reason)s', persona=persona.name, reason=reason)
            lead.message_post(body=line, author_id=Event._ai_partner().id, subtype_xmlid='mail.mt_note')
        else:
            created = True
            team = persona.crm_team_id or service.crm_team_id
            if team.company_id and company and team.company_id != company:
                team = self.env['crm.team']
            tags = service.crm_tag_ids | self.env.ref('linkedin_sales_automation.crm_tag_linkedin_ai')
            lead = self.env['crm.lead'].sudo().create({
                'name': '%s – %s (LinkedIn)' % (prospect.company or prospect.name, service.name),
                'contact_name': prospect.name,
                'partner_name': prospect.company or False,
                'function': prospect.title or prospect.headline or False,
                'website': prospect.linkedin_url,
                'description': prospect._lead_description(),
                'team_id': team.id or False,
                'user_id': salesperson.id or False,
                'tag_ids': [(6, 0, tags.ids)],
                'source_id': self.env.ref('linkedin_sales_automation.utm_source_li_automation').id,
                'medium_id': self.env.ref('utm.utm_medium_linkedin').id,
                'li_prospect_id': prospect.id,
                'li_persona_id': persona.id,
                'company_id': persona.company_id.id,
            })
        already_warm = prospect.stage in ('warm', 'meeting')
        prospect.write({
            'crm_lead_id': lead.id,
            'stage': prospect.stage if already_warm else 'warm',
            'date_warm': prospect.date_warm or utc_now(),
            'needs_analysis': False,
            'handoff_pending': bool(chat.handoff_message) and not already_warm and not prospect.is_taken_over,
        })
        owner = lead.user_id or salesperson or profile_owner or self.env.user
        if created:
            line = _('Pivot reached: %(reason)s. CRM lead #%(id)s created, assigned to %(user)s',
                     reason=reason, id=lead.id, user=owner.name or _('nobody'))
            Event._log('warm_lead', 'chat', persona=persona, prospect=prospect, lead=lead, detail=line,
                       persona_body=line, prospect_body=line, lead_body=line)
            lead.activity_schedule('mail.mail_activity_data_todo', user_id=owner.id,
                                   summary=_('Warm LinkedIn lead: %s', prospect.name),
                                   note=_('Pivot reached: %s. Take over the conversation on LinkedIn.', reason))
        else:
            line = _('Pivot reached: %(reason)s. Logged on existing CRM lead #%(id)s', reason=reason, id=lead.id)
            for record in (persona, prospect):
                record.message_post(body=line, author_id=Event._ai_partner().id, subtype_xmlid='mail.mt_note')
        prospect._take_over(user=owner, reason='pivot')
        return lead

    def _flag_check(self, reason):
        for prospect in self.sudo():
            prospect.write({'needs_check': True, 'needs_check_reason': reason})
            prospect.message_post(body=Markup('<b>%s</b> %s') % (_('Needs a check:'), escape(reason)))
            prospect.activity_schedule('mail.mail_activity_data_todo', user_id=prospect._owner_user().id,
                                       summary=_('Check LinkedIn send to %s', prospect.name), note=reason)
