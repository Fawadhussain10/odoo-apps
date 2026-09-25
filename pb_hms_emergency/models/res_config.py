# -*- coding: utf-8 -*-
# Part of PackBytes See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    emergency_invoicing = fields.Boolean("Allow Emergency Invoicing", default=True)
    emergency_usage_location_id = fields.Many2one('stock.location', 
        string='Usage Location for Consumed in Emergency.')
    emergency_stock_location_id = fields.Many2one('stock.location', 
        string='Stock Location for Consumed in Emergency')
    pb_emergency_service_product_id = fields.Many2one('product.product', 
        string='Emergency Service')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    emergency_invoicing = fields.Boolean("Allow Emergency Invoicing", related='company_id.emergency_invoicing', readonly=False)
    emergency_usage_location_id = fields.Many2one('stock.location', 
        related='company_id.emergency_usage_location_id',
        domain=[('usage','=','customer')],
        string='Usage Location for Consumed in Emergency', readonly=False)
    emergency_stock_location_id = fields.Many2one('stock.location', 
        related='company_id.emergency_stock_location_id',
        domain=[('usage','=','internal')],
        string='Stock Location for Consumed in Emergency', readonly=False)
    pb_emergency_service_product_id = fields.Many2one('product.product', 
        related='company_id.pb_emergency_service_product_id',
        domain=[('hospital_product_type','=','emergency')],
        string='Emergency Service', readonly=False)