# -*- coding: utf-8 -*-
# Part of PackBytes See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    vaccination_invoicing = fields.Boolean("Allow Vaccination Invoicing", default=True)
    pb_vaccination_usage_location_id = fields.Many2one('stock.location', 
        string='Usage Location for Consumed Vaccine.')
    pb_vaccination_stock_location_id = fields.Many2one('stock.location', 
        string='Stock Location for Consumed Vaccine')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    vaccination_invoicing = fields.Boolean("Allow Vaccination Invoicing", related='company_id.vaccination_invoicing', readonly=False)
    pb_vaccination_usage_location_id = fields.Many2one('stock.location', 
        related='company_id.pb_vaccination_usage_location_id',
        domain=[('usage','=','customer')],
        string='Usage Location for Consumed Vaccine', readonly=False)
    pb_vaccination_stock_location_id = fields.Many2one('stock.location', 
        related='company_id.pb_vaccination_stock_location_id',
        domain=[('usage','=','internal')],
        string='Stock Location for Consumed pb_vaccination_usage_location_id', readonly=False)