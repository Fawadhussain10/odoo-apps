# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PbRadiologyRequest(models.Model):
    _inherit = 'pb.radiology.request'

    insurance_id = fields.Many2one('hms.patient.insurance', string='Insurance Policy')
    claim_id = fields.Many2one('hms.insurance.claim', string='Claim')
    insurance_company_id = fields.Many2one('hms.insurance.company', related='insurance_id.insurance_company_id', string='Insurance Company', readonly=True, store=True)
    radiology_insurance_percentage = fields.Float(related='insurance_id.radiology_insurance_percentage', string="Insured Percentage", readonly=True)

    @api.onchange('patient_id')
    def onchange_patient_id(self):
        allow_radiology_insurances = self.patient_id.insurance_ids.filtered(lambda x: x.allow_radiology_insurance)
        if self.patient_id and allow_radiology_insurances:
            insurance = allow_radiology_insurances[0]
            self.insurance_id = insurance.id
            self.pricelist_id = insurance.pricelist_id and insurance.pricelist_id.id or False

    def create_invoice(self):
        res = super(PbRadiologyRequest, self).create_invoice()
        if self.invoice_id and self.insurance_id and (self.insurance_id.radiology_insurance_limit >= self.invoice_id.amount_total or self.insurance_id.radiology_insurance_limit==0):
            insurace_invoice = self.invoice_id.pb_create_insurace_invoice(self.insurance_id, self.insurance_id.radiology_insurance_type, 
                self.insurance_id.radiology_insurance_amount, self.insurance_id.radiology_insurance_percentage, 
                self, 'radiology', 'radiology_request_id', self.insurance_id.radiology_create_claim)
            if insurace_invoice and insurace_invoice.claim_id:
                self.claim_id = insurace_invoice.claim_id.id
        return res 