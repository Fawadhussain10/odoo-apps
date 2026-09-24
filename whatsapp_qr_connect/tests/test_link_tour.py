# -*- coding: utf-8 -*-
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
