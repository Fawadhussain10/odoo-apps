import json
from datetime import timedelta

from odoo import _, api, fields, models

from .li_common import AGENT_TYPES, SEND_TYPES, WORK_TYPES, local_now, utc_now

QUEUE_MAX_AGE = timedelta(days=7)
SENDING_MAX_AGE = timedelta(minutes=15)


class LiWorkItem(models.Model):
    """Work released to Claude by li_get_work (11.2), and the sending queue of
    built-in engine accounts.

    A released send item reserves one unit of its agent's daily quota until
    it is reported or its claim expires. A queued item (engine accounts) holds
    an approved text, or an invite without note; the background sender sends
    it when the rules allow and consumes the quota then. Before the engine is
    asked to send, the item is committed as Sending: if Odoo stops during the
    send, the outcome is unknown and the item is never sent again.
    """
    _name = 'li.work.item'
    _description = 'LinkedIn work item'
    _order = 'id desc'
    _rec_name = 'work_type'

    work_type = fields.Selection(WORK_TYPES, required=True, index=True)
    state = fields.Selection([
        ('released', 'Released'),
        ('queued', 'Queued'),
        ('sending', 'Sending'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='released', required=True, index=True)
    agent_type = fields.Selection(AGENT_TYPES, required=True, index=True)
    linkedin_profile_id = fields.Many2one('li.profile', required=True, index=True, ondelete='cascade',
                                          string='LinkedIn Profile')
    persona_id = fields.Many2one('li.persona', index=True, ondelete='cascade')
    company_id = fields.Many2one(related='linkedin_profile_id.company_id', store=True, index=True)
    prospect_id = fields.Many2one('li.prospect', index=True, ondelete='set null')
    step_id = fields.Many2one('li.chat.step', ondelete='set null')
    followup_step_id = fields.Many2one('li.followup.step', ondelete='set null')
    prospect_ids = fields.Many2many('li.prospect', 'li_work_item_prospect_rel', string='Listed prospects',
                                    help='Prospects listed in check_inbox / check_acceptance items.')
    payload = fields.Text(help='JSON sent to Claude.')
    date_released = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    expires_at = fields.Datetime(required=True, index=True)
    date_done = fields.Datetime()
    quota_date = fields.Date(index=True, help='Local day (persona target time zone) the quota is counted on.')
    quota_consumed = fields.Boolean(index=True)
    with_note = fields.Boolean()
    confirmed = fields.Boolean(help='li_confirm_send answered go.')
    date_confirmed = fields.Datetime()
    result_status = fields.Char()
    text_confirmed = fields.Text(help='Text validated by li_confirm_send.')
    text_sent = fields.Text()
    retry_safe = fields.Boolean()
    error = fields.Text()
    cancel_reason = fields.Char()
    conversation_version = fields.Integer(
        help='Last conversation message the text was written for. A newer message makes the text stale: '
             'it is discarded instead of sent.')
    discarded_stale = fields.Boolean(readonly=True, index=True,
                                     help='Discarded right before sending because the conversation changed.')
    send_attempts = fields.Integer(readonly=True, help='Background send attempts of this item.')
    writing = fields.Boolean(readonly=True, index=True,
                             help='Writing item of a built-in engine profile: Claude writes the text '
                                  '(li_submit_text), Odoo sends it.')
    date_submitted = fields.Datetime(readonly=True, help='When Claude submitted the text.')
    post_id = fields.Many2one('li.post', ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.uid)

    def _payload_dict(self):
        self.ensure_one()
        try:
            return json.loads(self.payload or '{}')
        except ValueError:
            return {}

    # ------------------------------------------------------------------
    # Quota
    # ------------------------------------------------------------------
    @api.model
    def _quota_domain(self, persona, agent_type):
        return [('persona_id', '=', persona.id), ('agent_type', '=', agent_type),
                ('quota_consumed', '=', True)]

    @api.model
    def _quota_used_today(self, persona, agent_type, exclude=None):
        today = local_now(persona.target_timezone).date()
        domain = self._quota_domain(persona, agent_type) + [('quota_date', '=', today)]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        return self.search_count(domain)

    @api.model
    def _quota_used_week(self, persona, agent_type, exclude=None):
        today = local_now(persona.target_timezone).date()
        domain = self._quota_domain(persona, agent_type) + [('quota_date', '>', today - timedelta(days=7))]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        return self.search_count(domain)

    @api.model
    def _followup_used(self, exclude=None):
        """The shared Follow-up Agent covers several time zones: its daily limit
        is counted over a rolling 24 hours."""
        domain = [('agent_type', '=', 'followup'), ('quota_consumed', '=', True),
                  ('date_released', '>', utc_now() - timedelta(hours=24))]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        return self.search_count(domain)

    @api.model
    def _total_invites(self, persona):
        return self.search_count([('persona_id', '=', persona.id), ('work_type', '=', 'invite'),
                                  ('state', '=', 'done'), ('quota_consumed', '=', True)])

    # ------------------------------------------------------------------
    # Life cycle
    # ------------------------------------------------------------------
    def _claim_timeout(self):
        minutes = int(self.env['ir.config_parameter'].sudo().get_param('li_sales.claim_timeout', 15) or 15)
        return timedelta(minutes=max(minutes, 1))

    def _close(self, state, **vals):
        vals.update(state=state, date_done=utc_now())
        if state in ('expired', 'cancelled'):
            # an item never confirmed sent nothing: give the quota back
            vals.setdefault('quota_consumed', False)
        self.write(vals)

    @api.model
    def _cancel_open(self, domain, reason, stale=False):
        """Cancel released and queued items (never one being sent). stale: the
        conversation changed, so queued texts count as discarded stale."""
        items = self.search(domain + [('state', 'in', ('released', 'queued'))])
        if stale:
            items.filtered(lambda i: i.state == 'queued' and i.text_confirmed).write({'discarded_stale': True})
        unconfirmed = items.filtered(lambda i: not i.confirmed)
        unconfirmed._close('cancelled', cancel_reason=reason)
        # a confirmed send may already be on LinkedIn: keep the quota, still block a report
        (items - unconfirmed)._close('cancelled', cancel_reason=reason, quota_consumed=True)
        return items

    @api.model
    def _cron_expire_claims(self):
        """Expire unreported claims and return their quota. A send that was
        confirmed but never reported has an unknown outcome: keep the quota and
        flag the prospect for a person to check."""
        self._recover_interrupted_sends()
        old = self.search([('state', '=', 'queued'), ('date_released', '<', utc_now() - QUEUE_MAX_AGE)])
        old._close('cancelled', cancel_reason=_('waited in the sending queue for more than %s days', QUEUE_MAX_AGE.days))
        expired = self.search([('state', '=', 'released'), ('expires_at', '<', utc_now())])
        for item in expired:
            if item.confirmed and item.work_type in SEND_TYPES:
                item._close('expired', quota_consumed=True,
                            error=_('Confirmed but never reported — outcome unknown'))
                if item.prospect_id:
                    item.prospect_id._flag_check(
                        _('A %s was confirmed for sending but never reported. Check LinkedIn to see '
                          'whether it went out.', dict(WORK_TYPES)[item.work_type].lower()))
            else:
                item._close('expired')
        return len(expired)

    @api.model
    def _recover_interrupted_sends(self):
        """A background send still marked Sending long after it started was cut off
        (Odoo restarted or the worker was killed): its outcome is unknown."""
        stuck = self.search([('state', '=', 'sending'), ('date_confirmed', '<', utc_now() - SENDING_MAX_AGE)])
        for item in stuck:
            item._close('failed', result_status='unknown', quota_consumed=True, retry_safe=False,
                        error=_('Odoo stopped while the engine was sending — outcome unknown'))
            if item.prospect_id:
                item.prospect_id._flag_check(
                    _('Odoo stopped while a %s was being sent. Check LinkedIn to see whether it went out.',
                      dict(WORK_TYPES)[item.work_type].lower()))
        return len(stuck)
