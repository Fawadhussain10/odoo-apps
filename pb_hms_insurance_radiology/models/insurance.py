# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class InsuranceClaim(models.Model):
    _inherit = 'hms.insurance.claim'

    radiology_request_id = fields.Many2one('pb.radiology.request', string='Radiology Request')
    claim_for = fields.Selection(selection_add=[('radiology', 'Radiology')])


class Insurance(models.Model):
    _inherit = 'hms.patient.insurance'

    allow_radiology_insurance = fields.Boolean(string="Insured Radiology", default=False)
    radiology_insurance_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fix', 'Fix-amount')], 'Radiology Insurance Type', default='percentage', required=True)
    radiology_insurance_amount = fields.Float(string="Radiology Co-payment", help="The patient should pay specific amount 50QR")
    radiology_insurance_percentage = fields.Float(string="Radiology Insured Percentage")
    radiology_insurance_limit = fields.Float(string="Radiology Insurance Limit")
    radiology_create_claim = fields.Boolean(string="Radiology Create Claim", default=False)