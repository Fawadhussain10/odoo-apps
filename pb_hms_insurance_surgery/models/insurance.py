# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class InsuranceClaim(models.Model):
    _inherit = 'hms.insurance.claim'

    surgery_id = fields.Many2one('hms.surgery', string='Surgery')
    claim_for = fields.Selection(selection_add=[('surgery', 'Surgery')])


class Insurance(models.Model):
    _inherit = 'hms.patient.insurance'

    allow_surgery_insurance = fields.Boolean(string="Insured Surgery", default=False)
    surgery_insurance_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fix', 'Fix-amount')], 'Surgery Insurance Type', default='percentage', required=True)
    surgery_insurance_amount = fields.Float(string="Surgery Co-payment", help="The patient should pay specific amount 50QR")
    surgery_insurance_percentage = fields.Float(string="Surgery Insured Percentage")
    surgery_insurance_limit = fields.Float(string="Surgery Insurance Limit")
    surgery_create_claim = fields.Boolean(string="Surgery Create Claim", default=False)