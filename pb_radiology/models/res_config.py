# -*- coding: utf-8 -*-
# Part of PackBytes See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, SUPERUSER_ID, _


class ResCompany(models.Model):
    _inherit = "res.company"

    pb_radiology_usage_location_id = fields.Many2one('stock.location', 
        string='Usage Location for Consumed Radiology Test Material.')
    pb_radiology_stock_location_id = fields.Many2one('stock.location', 
        string='Stock Location for Consumed Radiology Test Material')
    pb_radiology_result_qrcode = fields.Boolean(string="Print Authetication QrCode on Radiology Result", default=True)
    pb_radiology_invoice_policy = fields.Selection([('any_time', 'Anytime'), ('in_advance', 'Advance'),
        ('in_end', 'At End')], default="any_time", string="Radiology Invoice Policy", required=True)
    pb_check_radiology_payment = fields.Boolean(string="Check Payment Status before Accepting Radiology Request")
    pb_radiology_disclaimer = fields.Text(string="Radiology Disclaimer")


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pb_radiology_usage_location_id = fields.Many2one('stock.location', 
        related='company_id.pb_radiology_usage_location_id',
        domain=[('usage','=','customer')],
        string='Usage Location for Consumed Radiology Test Material', readonly=False)
    pb_radiology_stock_location_id = fields.Many2one('stock.location', 
        related='company_id.pb_radiology_stock_location_id',
        domain=[('usage','=','internal')],
        string='Stock Location for Consumed Radiology Test Material', readonly=False)
    pb_radiology_result_qrcode = fields.Boolean(related='company_id.pb_radiology_result_qrcode', string="Print Authetication QrCode on Radiology Result", readonly=False)
    pb_radiology_invoice_policy = fields.Selection(related='company_id.pb_radiology_invoice_policy', string="Radiology Invoice Policy", readonly=False)
    pb_check_radiology_payment = fields.Boolean(related='company_id.pb_check_radiology_payment', string="Check Payment Status before Accepting Radiology Request", readonly=False)
    pb_radiology_disclaimer = fields.Text(related='company_id.pb_radiology_disclaimer', string="Radiology Disclaimer", readonly=False)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: