from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pra_enabled = fields.Boolean(
        string="Enable PRA e-Invoicing",
        help="Report every validated order of this Point of Sale to the Punjab "
             "Revenue Authority (PRA) e-IMS in real time.",
    )
    pra_mode = fields.Selection([
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ], string="PRA Environment", default='sandbox')
    pra_pos_id = fields.Char(
        string="PRA POS ID",
        help="POS ID generated on the ePRA portal "
             "(Registration > POS Client Registration > POS Details, or Generate Test POS).",
    )
    pra_token = fields.Char(
        string="PRA Token",
        help="Token issued against the PRA POS ID. In Sandbox mode this can be left "
             "empty to use PRA's shared testing token. In Production it is the token "
             "shown on the POS Details tab of the ePRA portal for this POS ID.",
    )
    pra_proxy_url = fields.Char(
        string="PRA Proxy URL",
        help="Optional HTTP(S) proxy used for PRA calls, e.g. http://user:pass@203.0.113.10:3128. "
             "Use it when this server's IP is not whitelisted by PRA (e.g. hosted outside "
             "Pakistan): requests are tunnelled through the proxy so PRA sees the proxy's IP. "
             "Leave empty to connect to PRA directly.",
    )
