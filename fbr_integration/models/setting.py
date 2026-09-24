from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fbr_mode = fields.Selection([
        ('sandbox', 'Sandbox'),
        ('production', 'Production')
    ], string="FBR Environment", default='sandbox')
    fbr_token = fields.Char(string="FBR API Token")
    fbr_bpos_id = fields.Char(string="FBR BPOS ID", default="05")
    fbr_enable_service = fields.Boolean(string='Enable Service Fee?')
    fbr_service_fee = fields.Float(string='Service Fee')

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration.fbr_mode', self.fbr_mode)
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration.fbr_token', self.fbr_token)
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration.fbr_bpos_id', self.fbr_bpos_id)
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration.fbr_enable_service', self.fbr_enable_service)
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration.fbr_service_fee', self.fbr_service_fee)

    def get_values(self):
        res = super().get_values()
        res.update(
            fbr_mode=self.env['ir.config_parameter'].sudo().get_param('fbr_integration.fbr_mode'),
            fbr_token=self.env['ir.config_parameter'].sudo().get_param('fbr_integration.fbr_token'),
            fbr_bpos_id=self.env['ir.config_parameter'].sudo().get_param('fbr_integration.fbr_bpos_id'),
            fbr_enable_service=self.env['ir.config_parameter'].sudo().get_param('fbr_integration.fbr_enable_service'),
            fbr_service_fee=self.env['ir.config_parameter'].sudo().get_param('fbr_integration.fbr_service_fee'),
        )
        return res
