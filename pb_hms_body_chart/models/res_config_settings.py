# -*- encoding: utf-8 -*-
from odoo import api, fields, models,_


class ResCompany(models.Model):
    _inherit = 'res.company'

    pb_default_chart_image = fields.Binary('Default Chart Image', help="Image to use in chart by default.")
    pb_default_chart_image_name = fields.Char('Default Chart Image name')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pb_default_chart_image = fields.Binary(related='company_id.pb_default_chart_image',
        string='Default Chart Image', readonly=False)
    pb_default_chart_image_name = fields.Char(related='company_id.pb_default_chart_image_name',
        string='Default Chart Image name', readonly=False)
