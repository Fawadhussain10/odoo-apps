# -*- coding: utf-8 -*-
import base64
import os
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.whatsapp_qr_connect.models.whatsapp_account import WhatsappAccount


@tagged('post_install', '-at_install')
class TestLinkTour(HttpCase):

    def test_menu_opens_qr_screen_when_nothing_linked(self):
        self.env['whatsapp.account'].search([]).unlink()

        def fake_spawn(account):
            # what the real helper does: publish a QR code for the record
            account.sudo().write({
                'qr_string': 'https://wa.me/settings/linked_devices#2@fake,fake,fake',
                'link_pid': os.getpid(),
            })

        with patch.object(WhatsappAccount, '_spawn_link_worker', fake_spawn), \
                patch.object(WhatsappAccount, '_check_worker_python', lambda self: None):
            self.start_tour(
                '/odoo/action-whatsapp_qr_connect.action_whatsapp_open',
                'whatsapp_qr_connect_link_tour', login='admin')


@tagged('post_install', '-at_install')
class TestInboxTour(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['whatsapp.account'].search([]).unlink()
        self.account = self.env['whatsapp.account'].create(
            {'name': 'Sales', 'state': 'connected', 'phone': '923001111111'})
        chat = self.env['whatsapp.chat'].create(
            {'account_id': self.account.id, 'phone': '923001234567'})
        self.env['whatsapp.message'].create({
            'account_id': self.account.id, 'chat_id': chat.id, 'phone': '923001234567',
            'status': 'SENT', 'body': 'Hello from Odoo'})
        import os, tempfile
        png = os.path.join(tempfile.mkdtemp(), 'T2')
        with open(png, 'wb') as fh:
            fh.write(base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC'))
        self.account._process_incoming([{
            'phone': '923001234567', 'name': 'Ali', 'message_id': 'T2', 'body': 'a photo',
            'media_type': 'image', 'timestamp': 1_800_000_001,
            'media': {'path': png, 'mimetype': 'image/png', 'filename': 'p.png'}}])
        self.account._process_incoming([{
            'phone': '923001234567', 'name': 'Ali', 'message_id': 'T1',
            'body': 'Reply from customer', 'media_type': '', 'timestamp': 1_800_000_000}])
        self.env.cr.flush()

    def test_inbox_screen(self):
        def fake(account, mode, payload=None, timeout=90, **extra):
            return {'ok': True, 'results': [{'status': 'SENT', 'message_id': 'T2'}]}
        with patch.object(WhatsappAccount, '_run_worker', fake):
            self.start_tour('/odoo', 'whatsapp_qr_connect_inbox_tour', login='admin')

    def test_new_message_popup(self):
        """A reply that arrives while the user works in Odoo shows a 2-second pop-up."""
        self.start_tour('/odoo', 'whatsapp_qr_connect_popup_tour', login='admin')
