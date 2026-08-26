# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError, UserError, RedirectWarning

class AccountMove(models.Model): 
    _inherit = "account.move"

    patient_id = fields.Many2one('hms.patient',string="Patient")
    hospital_invoice_type = fields.Selection(selection_add=[('pharmacy', 'Pharmacy')])

    def get_scan_line_data(self, product, lot=False):
        res = super(AccountMove, self).get_scan_line_data(product, lot)
        res['pb_lot_id'] = lot and lot.id or False
        return res


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('quantity', 'pb_lot_id')
    def onchange_batch(self):
        res = super(AccountMoveLine, self).onchange_batch()
        if self.pb_lot_id and self.pb_lot_id.mrp:
            self.price_unit = self.pb_lot_id.mrp
        return res

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: