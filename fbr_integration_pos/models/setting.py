from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fbr_mode = fields.Selection([
        ('sandbox', 'Sandbox'),
        ('production', 'Production')
    ], string="FBR Environment", default='sandbox')
    fbr_token = fields.Char(string="FBR API Token")
    fbr_bpos_id = fields.Char(string="FBR BPOS ID", default="05")
    pos_auto_invoice_on_payment = fields.Boolean(related="pos_config_id.auto_invoice_on_payment", readonly=False)
    pos_restrict_invoice_download = fields.Boolean(related='pos_config_id.restrict_invoice_download',
                                                   readonly=False)
    pos_default_partner_id = fields.Many2one('res.partner', related="pos_config_id.default_partner_id",
                                             readonly=False,
                                             string="Default Customer")

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration_pos.fbr_mode', self.fbr_mode)
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration_pos.fbr_token', self.fbr_token)
        self.env['ir.config_parameter'].sudo().set_param('fbr_integration_pos.fbr_bpos_id', self.fbr_bpos_id)

    def get_values(self):
        res = super().get_values()
        res.update(
            fbr_mode=self.env['ir.config_parameter'].sudo().get_param('fbr_integration_pos.fbr_mode'),
            fbr_token=self.env['ir.config_parameter'].sudo().get_param('fbr_integration_pos.fbr_token'),
            fbr_bpos_id=self.env['ir.config_parameter'].sudo().get_param('fbr_integration_pos.fbr_bpos_id')
        )
        return res


class PosConfigInherit(models.Model):
    _inherit = 'pos.config'

    auto_invoice_on_payment = fields.Boolean(string="Auto Check Invoice on Payment?")
    restrict_invoice_download = fields.Boolean(string="Restrict Invoice Download?")
    default_partner_id = fields.Many2one('res.partner', string="Select Customer")
