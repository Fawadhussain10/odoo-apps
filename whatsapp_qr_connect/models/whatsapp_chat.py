# -*- coding: utf-8 -*-
import base64
import logging
import mimetypes
from odoo import _, api, fields, models, modules
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

PREVIEW_LEN = 80
MAX_UPLOAD_BYTES = 16 * 1024 * 1024
LISTEN_SECONDS = 50          # each minute-cron run keeps WhatsApp connected this long


class WhatsappChat(models.Model):
    """A conversation with one phone number that Odoo has written to.

    Only numbers Odoo sent a message to get a chat - the rest of the linked
    phone's WhatsApp chats are never read into Odoo.
    """
    _name = 'whatsapp.chat'
    _description = 'WhatsApp Chat'
    _order = 'last_message_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True, readonly=False)
    account_id = fields.Many2one('whatsapp.account', required=True, ondelete='cascade', index=True)
    phone = fields.Char(required=True, index=True)
    contact_name = fields.Char(string='WhatsApp Name')
    message_ids = fields.One2many('whatsapp.message', 'chat_id')
    last_message_date = fields.Datetime(index=True)
    last_message_preview = fields.Char()
    unread_count = fields.Integer(compute='_compute_unread', store=True)

    _account_phone_uniq = models.Constraint(
        'unique(account_id, phone)', 'There is already a chat with this number.')

    @api.depends('contact_name', 'phone')
    def _compute_name(self):
        for chat in self:
            chat.name = chat.contact_name or ('+' + (chat.phone or ''))

    @api.depends('message_ids.is_read', 'message_ids.direction')
    def _compute_unread(self):
        for chat in self:
            chat.unread_count = len(chat.message_ids.filtered(
                lambda m: m.direction == 'in' and not m.is_read))

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    @api.model
    def _get_or_create(self, account_id, phone):
        chat = self.search([('account_id', '=', account_id), ('phone', '=', phone)], limit=1)
        if not chat and len(phone) >= 10:      # 0301... and 92301... are the same person
            chat = self.search([('account_id', '=', account_id), ('phone', 'like', phone[-10:])], limit=1)
        if not chat:
            partner = self.env['res.partner']
            if len(phone) >= 9:
                partner = partner.sudo().search([('phone', 'like', phone[-9:])], limit=1)
            chat = self.create({'account_id': account_id, 'phone': phone,
                                'name': partner.name or '+' + phone})
        return chat

    def _refresh_last_message(self):
        for chat in self:
            last = self.env['whatsapp.message'].sudo().search(
                [('chat_id', '=', chat.id)], order='date desc, id desc', limit=1)
            if last:
                text = last.body or ('[%s]' % (last.media_type or last.attachment_name or _("file")))
                chat.write({'last_message_date': last.date,
                            'last_message_preview': text.replace('\n', ' ')[:PREVIEW_LEN]})

    def _serialize(self):
        return [{
            'id': c.id, 'name': c.name, 'phone': c.phone, 'account': c.account_id.name,
            'account_id': c.account_id.id, 'unread': c.unread_count,
            'preview': c.last_message_preview or '', 'date': fields.Datetime.to_string(
                c.last_message_date) if c.last_message_date else False,
        } for c in self]

    @api.model
    def _visible_chats(self):
        accounts = self.env['whatsapp.account'].search([])   # multi-company rules apply
        return self.sudo().search([('account_id', 'in', accounts.ids)])

    @api.model
    def _check_user(self):
        if not (self.env.user._is_internal()
                and self.env.user.has_group('whatsapp_qr_connect.group_whatsapp_chat')):
            raise AccessError(_("You are not allowed to use WhatsApp chats "
                                "(group: WhatsApp / Chat User)."))

    # ------------------------------------------------------------------
    # RPC used by the chat screen
    # ------------------------------------------------------------------
    @api.model
    def get_chats(self):
        self._check_user()
        chats = self._visible_chats()
        has_linked = bool(self.env['whatsapp.account'].search_count([('state', '=', 'connected')]))
        return {'chats': chats[:200]._serialize(), 'has_linked': has_linked,
                'unread': sum(chats.mapped('unread_count'))}

    def get_messages(self, mark_read=True):
        self.ensure_one()
        self._check_user()
        chat = self.sudo()
        if chat not in self._visible_chats():
            raise AccessError(_("You cannot open this chat."))
        if mark_read:
            chat.message_ids.filtered(lambda m: m.direction == 'in' and not m.is_read).write(
                {'is_read': True})
        return {
            'chat': chat._serialize()[0],
            'messages': [{
                'id': m.id, 'direction': m.direction, 'body': m.body or '',
                'media': m.media_type or m.attachment_name or '',
                'file': {'id': m.attachment_id.id, 'mimetype': m.attachment_id.mimetype,
                         'name': m.attachment_id.name} if m.attachment_id else False,
                'status': m.status, 'detail': m.detail or '',
                'date': fields.Datetime.to_string(m.date), 'user': m.user_id.name or '',
            } for m in chat.message_ids.sorted(lambda m: (m.date, m.id))[-300:]],
        }

    def send_reply(self, text, attachments=None):
        """Answer in this chat. ``attachments``: ``[{'name', 'mimetype', 'data'(base64)}]``
        (pictures, videos, audio, PDFs, any file); the text becomes the caption of the first."""
        self.ensure_one()
        self._check_user()
        chat = self.sudo()
        if chat not in self._visible_chats():
            raise AccessError(_("You cannot open this chat."))
        text = (text or '').strip()
        attachments = attachments or []
        if not text and not attachments:
            raise UserError(_("The message is empty."))
        items, total = [], 0
        for index, att in enumerate(attachments):
            content = base64.b64decode(att.get('data') or '')
            total += len(content)
            if not content:
                raise UserError(_("The file '%s' is empty.", att.get('name') or ''))
            if len(content) > MAX_UPLOAD_BYTES:
                raise UserError(_("The file '%s' is larger than 16 MB.", att.get('name') or ''))
            items.append({
                'phone': chat.phone, 'message': text if index == 0 else '',
                'attachment': {
                    'filename': att.get('name') or 'file', 'content': content, 'keep': True,
                    'as_media': True,
                    'mimetype': att.get('mimetype') or mimetypes.guess_type(att.get('name') or '')[0]
                    or 'application/octet-stream'}})
        if not items:
            items.append({'phone': chat.phone, 'message': text})
        results = self.env['whatsapp.account'].send_messages(items, account=chat.account_id)
        failed = [r for r in results if r['status'] != 'SENT']
        if failed:
            raise UserError(failed[0].get('detail') or failed[0]['status'])
        return chat.get_messages(mark_read=False)

    @api.model
    def poll(self, last_id=0):
        """Cheap call every few seconds from the browser: new incoming messages."""
        self._check_user()
        chats = self._visible_chats()
        new = self.env['whatsapp.message'].sudo().search([
            ('direction', '=', 'in'), ('id', '>', last_id), ('chat_id', 'in', chats.ids)],
            order='id')
        top = self.env['whatsapp.message'].sudo().search(
            [('direction', '=', 'in'), ('chat_id', 'in', chats.ids)], order='id desc', limit=1)
        return {
            'last_id': top.id or 0,
            'unread': sum(chats.mapped('unread_count')),
            'new': [{'id': m.id, 'chat_id': m.chat_id.id, 'name': m.chat_id.name,
                     'text': (m.body or '[%s]' % (m.media_type or '')).replace('\n', ' ')[:PREVIEW_LEN]}
                    for m in new[-5:]],
        }

    @api.model
    def refresh_inbox(self):
        """"Check now" button: fetch what WhatsApp delivered since the last check."""
        self._check_user()
        accounts = self.env['whatsapp.account'].search([('state', '=', 'connected')])
        count = accounts.sudo()._receive_messages()
        return {'received': count}

    @api.model
    def _cron_receive(self):
        accounts = self.env['whatsapp.account'].sudo().search([('state', '=', 'connected')])
        # one long-lived connection per run keeps replies arriving within seconds
        accounts._receive_messages(commit=True, window=max(15, LISTEN_SECONDS // max(len(accounts), 1)))
