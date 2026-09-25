# -*- coding: utf-8 -*-
# Part of PackBytes See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    pb_ambulance_invoicing = fields.Boolean("Allow Ambulance Invoicing", default=True)
    pb_ambulance_invoicing_product_id = fields.Many2one('product.product', 
        domain=[('type','=','service')],
        string='Ambulance Invoicing Product', 
        ondelete='restrict', help='Ambulance Invoicing Product')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pb_ambulance_invoicing = fields.Boolean("Allow Ambulance Invoicing", related='company_id.pb_ambulance_invoicing', readonly=False)
    pb_ambulance_invoicing_product_id = fields.Many2one('product.product', 
        related='company_id.pb_ambulance_invoicing_product_id', readonly=False,
        domain=[('type','=','service')],
        string='Ambulance Invoicing Product', 
        ondelete='restrict', help='Ambulance Invoicing Product')