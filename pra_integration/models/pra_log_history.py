from odoo import models, fields, api


class PosOrder(models.Model):
    _name = 'pos.order.log.history'
    _rec_name = "pos_order_reference"
    _description = 'POS Order Log History for PRA Integration'

    pos_order_reference = fields.Char(string="Order Reference ")
    pos_order_id = fields.Many2one('pos.order', string="POS Order Number")
    order_send_data = fields.Text(string="Order Send Data")
    pra_response = fields.Text(string="PRA Response")
    pra_invoice_number = fields.Char(string="PRA Invoice Number")
    pra_qr_code = fields.Binary(string="PRA QR Code")
    pra_response_success = fields.Boolean(string="PRA Response Success", default=False)
