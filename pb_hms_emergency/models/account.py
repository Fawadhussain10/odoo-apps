# -*- coding: utf-8 -*-

from odoo import api,fields,models,_


class AccountMove(models.Model):
    _inherit = 'account.move'

    emergency_id = fields.Many2one('pb.hms.emergency',  string='Emergency')
    hospital_invoice_type = fields.Selection(selection_add=[('emergency', 'Emergency')])
