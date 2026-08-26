# -*- coding: utf-8 -*-

from odoo import api, fields, models,_

class PbInvoiceSummary(models.Model):
    _inherit = 'pb.invoice.summary'

    STATES = {'done': [('readonly', True)]}

    patient_id = fields.Many2one('hms.patient',  string='Patient', index=True, required=True)
    partner_id = fields.Many2one('res.partner',  related="patient_id.partner_id", string='Partner', index=True, store=True)