from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Stored as typed system parameters (Odoo 20): the keys are unchanged, so existing
    # values are picked up as they are.
    fbr_mode = fields.Selection([
        ('sandbox', 'Sandbox'),
        ('production', 'Production')
    ], string="FBR Environment", default='sandbox', config_parameter='fbr_integration.fbr_mode')
    fbr_token = fields.Char(string="FBR API Token", config_parameter='fbr_integration.fbr_token')
    fbr_bpos_id = fields.Char(string="FBR BPOS ID", default="05", config_parameter='fbr_integration.fbr_bpos_id')
    fbr_enable_service = fields.Boolean(string='Enable Service Fee?',
                                        config_parameter='fbr_integration.fbr_enable_service')
    fbr_service_fee = fields.Float(string='Service Fee', config_parameter='fbr_integration.fbr_service_fee')
