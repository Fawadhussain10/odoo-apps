# -*- coding: utf-8 -*-
{
    'name': 'Hospital Pharmacy Management - Point of Sale',
    'version': '20.0.1.0.0',
    'summary': 'Link module between Point of Sale and Hospital Pharmacy Management system',
    'description': """
        Link module between Point of Sale and Hospital Pharmacy Management system. Point of prescription integration with Hospital management system.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_pharmacy', 'pos_stock'],
    'data': [
        'data/pb_hms_pharmacy_pos_data.xml',
        'security/security.xml',
        'views/prescription_order_views.xml',
        'views/pos_order_views.xml',
        'views/stock_template.xml',
        'receipt/pos_order_receipt.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pb_hms_pharmacy_pos/static/src/css/pb_hms_pharmacy_pos.css',
            'pb_hms_pharmacy_pos/static/src/js/**/*',
            'pb_hms_pharmacy_pos/static/src/xml/**/*',
        ],
    },
    'sequence': 2,
    'price': 265,
    'currency': 'USD',
    'installable': True,
    'auto_install': False,

}
