# -*- coding: utf-8 -*-

{
    'name': 'Add Products by Barcode in Invoice',
    'version': '19.0.1.0.0',
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
    'installable': True,
    'auto_install': False,
    'application': False,
    'price': 15,
    'currency': 'USD',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: