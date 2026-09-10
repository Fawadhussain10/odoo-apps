from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    pra_payment_mode = fields.Selection([
        ('1', 'Cash'),
        ('2', 'Card'),
        ('3', 'Gift Voucher'),
        ('4', 'Loyalty Card'),
        ('6', 'Cheque'),
    ], string="PRA Payment Mode",
        help="How this payment method is reported to PRA on the fiscal invoice. "
             "Leave empty to let it be inferred automatically (Cash journals report as "
             "Cash, everything else as Card). When an order is paid with more than one "
             "PRA payment mode, PRA is informed it was paid with 'Mixed' payment.")

    def _get_pra_payment_mode(self):
        self.ensure_one()
        if self.pra_payment_mode:
            return self.pra_payment_mode
        return '1' if self.type == 'cash' else '2'
