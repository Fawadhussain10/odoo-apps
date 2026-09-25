# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    hospital_invoice_type = fields.Selection(selection_add=[('commission', 'Commission')])

    @api.onchange('ref_physician_id')
    def onchange_ref_physician(self):
        if self.ref_physician_id and self.ref_physician_id.provide_commission:
            self.commission_partner_ids = [(4, self.ref_physician_id.id)]

    @api.onchange('physician_id')
    def onchange_physician(self):
        if self.physician_id:
            #PB NOTE: no need but sudo do not work for portal access.
            physician = self.env['hms.physician'].sudo().search([('id','=',self.sudo().physician_id.id)])
            if physician.provide_commission:
                self.commission_partner_ids = [(4, physician.partner_id.id)]
