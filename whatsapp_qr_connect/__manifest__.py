# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp QR Connect',
    'version': '19.0.3.0.0',
    'category': 'Technical',
    'summary': 'Link WhatsApp by QR code inside Odoo, chat with your customers from a '
               'premium home-screen app (live replies, photos, emoji, attachments, access group) and send sales, purchase, '
               'delivery, invoice, bill, salary slip and ledger PDFs on WhatsApp.',
    'description': """
WhatsApp QR Connect
===================
A standalone building block for WhatsApp messaging in Odoo.

* Settings > Technical > WhatsApp: scan a QR code in Odoo to link a WhatsApp
  number (like WhatsApp Web / Linked devices). No Node.js / gateway service.
* Link as many numbers as you like; each keeps its own session, stored
  in your Odoo database (works on Odoo.sh).
* One Python API for every other module::

      self.env['whatsapp.account'].send_message('923001234567', 'Hello!')
      # or, asking the user which number to use when several are linked:
      return self.env['whatsapp.account'].action_send_message(phone, text)

* WhatsApp button on Sales Orders, Purchase Orders, Delivery / Receipt
  transfers, Invoices and Bills, Salary Slips and Contacts (customer / vendor
  ledger). The document is sent as a PDF attachment; the message can be edited
  and the sending number chosen first. Buttons appear only for apps that are
  installed (Sales, Purchase, Inventory, Payroll).
* WhatsApp app on the home screen (only for the group WhatsApp / Chat User; administrators
  have it automatically): a modern WhatsApp-style chat screen (avatars, day separators, image and
  document bubbles, read ticks) with the chats Odoo started. Replies arrive within seconds (live
  listener + bus websocket), a "new message" pop-up (2 seconds) appears anywhere in Odoo,
  received photos, videos, voice notes and files are downloaded and shown in the chat, and you can
  answer with emoji, pictures, videos, audio, PDFs and any file.
* Message log of everything sent through the module.

Requires the Python library: neonize==0.5.2  (install with: pip install neonize==0.5.2;
it needs protobuf>=7.34.1). If your Odoo Python pins an older protobuf, install neonize in a
separate virtualenv and set the system parameter whatsapp_qr_connect.python_path to its python.
    """,
    'author': 'PackBytes',
    'website': 'https://packbytes.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'price': 250.00,
    'currency': 'USD',
    'depends': ['base', 'web', 'bus', 'account'],
    'data': [
        'security/whatsapp_security.xml',
        'security/ir.model.access.csv',
        'views/whatsapp_account_views.xml',
        'views/whatsapp_message_views.xml',
        'wizard/whatsapp_send_wizard_views.xml',
        'views/menus.xml',
        'reports/partner_ledger.xml',
        'data/ir_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'whatsapp_qr_connect/static/src/link_action/*',
            'whatsapp_qr_connect/static/src/inbox/*',
        ],
        'web.assets_tests': [
            'whatsapp_qr_connect/static/tests/tours/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
