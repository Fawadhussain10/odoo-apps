# -*- coding: utf-8 -*-

{
    'name': 'Add Products by Barcode in Invoice',
    'version': '20.0.1.0.0',
    'category': 'Accounting',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'summary': """Add Products by scanning barcode to avoid mistakes and make work faster in Invoice.""",
    'description': """
        Add Products by scanning barcode to avoid mistakes and make work faster in Invoice. Barcode Product barcode barcode in invoice Invoice Barcode Scan barcode and add product Scan product and add Scan to add product Scan barcode to add product product by barcode scan add product in invoice.
    """,
    'images': ['static/description/banner.png'],
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1', 
    "depends": ["account",'barcodes','stock'],
    "data": [
        "views/account_invoice_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pb_invoice_barcode/static/src/js/barcode_handler_field.js",
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'price': 20,
    'currency': 'USD',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: