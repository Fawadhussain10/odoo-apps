# -*- coding: utf-8 -*-
{
    'name': 'Sale Tender',
    'version': '17.0.1.0.0',
    'summary': 'Manage tender submissions and convert accepted tenders into quotations',
    'description': """
Sale Tender
===========
Track tenders (Bid Money/Earnest Money, Performance Security, Advance Payment
Security) with their tender number, mode of instrument and supporting
attachments. Tenders go through a simple Accept/Reject approval flow, and
accepted tenders can be converted into a sale Quotation with one click.
""",
    'category': 'Sales',
    'author': 'Fawad Hussain, Packbytes',
    'website': 'https://packbytes.com/',
    'support': 'sales@packbytes.com',
    'price': 50.00,
    'currency': 'EUR',
    'depends': ['sale_management', 'mail'],
    'data': [
        'security/sale_tender_security.xml',
        'security/ir.model.access.csv',
        'data/sale_tender_sequence.xml',
        'views/sale_tender_views.xml',
        'views/sale_tender_menus.xml',
        'views/sale_order_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
