# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class Physiotherapy(models.Model):
    _inherit = 'pb.physiotherapy'

    subscription_id = fields.Many2one("pb.hms.subscription", "Subscription", ondelete="restrict")

    @api.onchange("subscription_id")
    def onchange_subscription_id(self):
        if self.subscription_id:
            # remaining_service is computed from already-saved sessions, so it
            # doesn't count this in-progress one yet: <=0 here means every
            # slot is already used by other sessions.
            if self.subscription_id.remaining_service <= 0:
                subscription = self.subscription_id
                self.subscription_id = False
                return {'warning': {
                    'title': _("No sessions remaining"),
                    'message': _("%s has no remaining sessions on this subscription.") % (subscription.patient_id.name or subscription.name),
                }}
            if self.subscription_id.pb_type=='full':
                self.invoice_exempt = True
            else:
                self.pricelist_id = self.subscription_id.pricelist_id and self.subscription_id.pricelist_id.id or False

    @api.constrains('subscription_id')
    def _check_subscription_remaining_service(self):
        for rec in self:
            if rec.subscription_id and rec.subscription_id.remaining_service < 0:
                raise ValidationError(_(
                    "This session would exceed the number of sessions allowed on subscription %s."
                ) % rec.subscription_id.display_name)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: