# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

class PBCommissionBill(models.TransientModel):
    _inherit = "commission.bill"

    def create_bill(self, line):
        res = super(PBCommissionBill, self).create_bill(line)
        res.hospital_invoice_type = 'commission'
        return res
