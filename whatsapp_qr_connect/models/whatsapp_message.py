# -*- coding: utf-8 -*-
from odoo import fields, models


class WhatsappMessage(models.Model):
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message Log'
    _order = 'id desc'
    _rec_name = 'phone'

    account_id = fields.Many2one('whatsapp.account', string='Sent From',
                                 ondelete='set null', index=True)
    phone = fields.Char(string='To')
    body = fields.Text(string='Message')
    status = fields.Selection([
        ('SENT', 'Sent'),
        ('NOT_WHATSAPP', 'Not on WhatsApp'),
        ('INVALID_PHONE', 'Invalid Number'),
        ('NOT_LINKED', 'Number Not Linked'),
        ('ERROR', 'Error'),
    ], required=True, index=True)
    detail = fields.Text(string='Details')
    message_id = fields.Char(string='WhatsApp Message ID')
    attachment_name = fields.Char(string='Attached File')
    res_model = fields.Char(string='Related Model')
    res_id = fields.Integer(string='Related Record ID')
    user_id = fields.Many2one('res.users', string='Sent By', default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now)
