# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp QR Connect',
    'version': '20.0.2.0.0',
    'category': 'Technical',
    'summary': 'Link WhatsApp by QR code inside Odoo and send sales, purchase, delivery, '
               'invoice, bill, salary slip and ledger PDFs on WhatsApp - no extra service.',
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
    'depends': ['base', 'web', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/whatsapp_account_views.xml',
        'views/whatsapp_message_views.xml',
        'wizard/whatsapp_send_wizard_views.xml',
        'views/menus.xml',
        'reports/partner_ledger.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'whatsapp_qr_connect/static/src/link_action/*',
        ],
        'web.assets_tests': [
            'whatsapp_qr_connect/static/tests/tours/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
