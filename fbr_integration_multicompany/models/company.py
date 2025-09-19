from odoo import models, fields, api, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    fbr_mode = fields.Selection([
        ('sandbox', 'Sandbox'),
        ('production', 'Production')
    ], string="FBR Environment", default='sandbox')
    fbr_token = fields.Char(string="FBR API Token")
    fbr_bpos_id = fields.Char(string="FBR BPOS ID", default="05")
    fbr_enable_service = fields.Boolean(string='Enable Service Fee?')
    fbr_service_fee = fields.Float(string='Service Fee')
