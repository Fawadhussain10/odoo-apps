# -*- coding: utf-8 -*-
# Part of PackBytes See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    physiotherapy_invoice_policy = fields.Selection([('at_end','Invoice in the End'),
        ('anytime','Invoice Anytime'),
        ('advance','Invoice in Advance')], default='at_end', string="Physiotherapy Invoicing Policy", required=True)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    physiotherapy_invoice_policy = fields.Selection(related='company_id.physiotherapy_invoice_policy', string="Physiotherapy Invoicing Policy", readonly=False)