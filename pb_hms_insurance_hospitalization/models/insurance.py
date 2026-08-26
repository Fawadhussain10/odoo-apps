# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError, UserError, RedirectWarning


class InsuranceClaim(models.Model):
    _inherit = 'hms.insurance.claim'

    STATES={'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    hospitalization_id = fields.Many2one('pb.hospitalization', 'Hospitalization')
    claim_for = fields.Selection(selection_add=[('hospitalization', 'Hospitalization')])
    package_id = fields.Many2one('pb.hms.package', string='Package')
    
    
    @api.onchange('package_id')
    def onchange_package_id(self):
        if self.package_id:
            self.amount_requested = self.package_id.amount_total

    @api.onchange('hospitalization_id')
    def onchange_hospitalization(self):
        if self.hospitalization_id and self.hospitalization_id.package_id:
            self.package_id = self.hospitalization_id.package_id.id

    def get_relate_invoices(self):
        invoices = super(InsuranceClaim, self).get_relate_invoices()
        if self.claim_for=='hospitalization':
            invoices = self.env['account.move'].search([('hospitalization_id', '=', self.hospitalization_id.id)])
        return invoices
