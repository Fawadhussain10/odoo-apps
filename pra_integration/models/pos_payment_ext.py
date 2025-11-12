from odoo import models, fields


class PosPaymentMethodExt(models.Model):
    _inherit = 'pos.payment.method'
    _description = 'POS Payment Method Extension'

    pra_payment_id = fields.Boolean(string="PRA Payment Method", default=False,
                                    help="Indicates if this payment method is used for PRA integration.")
