# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class InsuranceClaim(models.Model):
    _inherit = 'hms.insurance.claim'

    request_id = fields.Many2one('pb.laboratory.request', string='Laboratory Request')
    claim_for = fields.Selection(selection_add=[('laboratory', 'Laboratory')])


class Insurance(models.Model):
    _inherit = 'hms.patient.insurance'

    allow_laboratory_insurance = fields.Boolean(string="Insured Laboratory", default=False)
    lab_insurance_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fix', 'Fix-amount')], 'Laboratory Insurance Type', default='percentage', required=True)
    lab_insurance_amount = fields.Float(string="Laboratory Co-payment", help="The patient should pay specific amount 50QR")
    lab_insurance_percentage = fields.Float(string="Laboratory Insured Percentage")
    lab_insurance_limit = fields.Float(string="Laboratory Insurance Limit")
    lab_create_claim = fields.Boolean(string="Laboratory Create Claim", default=False)