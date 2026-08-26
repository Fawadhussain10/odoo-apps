# -*- coding: utf-8 -*-
# Part of PackBytes See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    pb_mr_usage_location_id = fields.Many2one('stock.location', string='Vendor Location for Sample Products')
    pb_mr_stock_location_id = fields.Many2one('stock.location', string='Stock Location for Sample Products')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pb_mr_usage_location_id = fields.Many2one('stock.location', 
        related='company_id.pb_mr_usage_location_id', domain=[('usage','=','supplier')],
        string='Vendor Location for Sample Products', readonly=False)
    pb_mr_stock_location_id = fields.Many2one('stock.location', 
        related='company_id.pb_mr_stock_location_id', domain=[('usage','=','internal')],
        string='Stock Location for Sample Products', readonly=False)