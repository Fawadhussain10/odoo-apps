# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
        ('RECEIVED', 'Received'),
    ], required=True, index=True)
    direction = fields.Selection([('out', 'Sent'), ('in', 'Received')], default='out',
                                 required=True, index=True)
    chat_id = fields.Many2one('whatsapp.chat', string='Chat', ondelete='set null', index=True)
    is_read = fields.Boolean(default=True, index=True)
    media_type = fields.Char(string='Media')
    attachment_id = fields.Many2one('ir.attachment', string='Media File', ondelete='set null')
    detail = fields.Text(string='Details')
    message_id = fields.Char(string='WhatsApp Message ID')
    attachment_name = fields.Char(string='Attached File')
    res_model = fields.Char(string='Related Model')
    res_id = fields.Integer(string='Related Record ID')
    user_id = fields.Many2one('res.users', string='Sent By', default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now)

    @api.model_create_multi
    def create(self, vals_list):
        chats = self.env['whatsapp.chat'].sudo()
        for vals in vals_list:
            # what Odoo sends shows up in the chat screen (failed sends do not open chats)
            if (not vals.get('chat_id') and vals.get('account_id')
                    and vals.get('status') == 'SENT' and vals.get('phone')):
                phone = self.env['whatsapp.account']._normalize_phone(vals['phone'])
                if phone:
                    vals['chat_id'] = chats._get_or_create(vals['account_id'], phone).id
        records = super().create(vals_list)
        records.mapped('chat_id')._refresh_last_message()
        return records
