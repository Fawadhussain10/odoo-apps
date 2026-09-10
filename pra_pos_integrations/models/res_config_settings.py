from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_pra_enabled = fields.Boolean(related='pos_config_id.pra_enabled', readonly=False)
    pos_pra_mode = fields.Selection(related='pos_config_id.pra_mode', readonly=False)
    pos_pra_pos_id = fields.Char(related='pos_config_id.pra_pos_id', readonly=False)
    pos_pra_token = fields.Char(related='pos_config_id.pra_token', readonly=False)
