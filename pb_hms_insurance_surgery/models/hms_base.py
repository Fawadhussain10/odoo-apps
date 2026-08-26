# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PBSurgery(models.Model):
    _inherit = 'hms.surgery'

    insurance_id = fields.Many2one('hms.patient.insurance', string='Insurance Policy')
    claim_id = fields.Many2one('hms.insurance.claim', string='Claim')
    insurance_company_id = fields.Many2one('hms.insurance.company', related='insurance_id.insurance_company_id', string='Insurance Company', readonly=True, store=True)
    surgery_insurance_percentage = fields.Float(related='insurance_id.surgery_insurance_percentage', string="Surgery Percentage", readonly=True)

    @api.onchange('patient_id')
    def onchange_patient_id(self):
        allow_surgery_insurance = self.patient_id.insurance_ids.filtered(lambda x: x.allow_surgery_insurance)
        if self.patient_id and allow_surgery_insurance:
            insurance = allow_surgery_insurance[0]
            self.insurance_id = insurance.id
            # self.pricelist_id = insurance.pricelist_id and insurance.pricelist_id.id or False

    def action_create_invoice(self):
        res = super(PBSurgery, self).action_create_invoice()
        if self.invoice_id and self.insurance_id and (self.insurance_id.surgery_insurance_limit >= self.invoice_id.amount_total or self.insurance_id.surgery_insurance_limit==0):
            insurace_invoice = self.invoice_id.pb_create_insurace_invoice(self.insurance_id, self.insurance_id.surgery_insurance_type, 
                self.insurance_id.surgery_insurance_amount, self.insurance_id.surgery_insurance_percentage, 
                self, 'surgery', 'surgery_id', self.insurance_id.surgery_create_claim)
            if insurace_invoice and insurace_invoice.claim_id:
                self.claim_id = insurace_invoice.claim_id.id
        return res 