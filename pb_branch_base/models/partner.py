# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResPartnerIn(models.Model):
    _inherit = 'res.partner'

    #Do not set branch by default as all Contact should be shared across all branch by default.
    branch_id = fields.Many2one('res.company', string="Branch")