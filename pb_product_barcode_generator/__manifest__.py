# -*- coding: utf-8 -*-
{
    "name": 'PB Product Barcode Generator',
    'summary': """This module will add a functionality to allow barcode generation of EAN13 for products. You can do configuration at product or category or company level.""",
    "description": """
        This module will add a functionality to allow barcode generation of EAN13 for products You can do configuration at product or category or company level. The 13rd is the key of the EAN13, this will be automatically computed. Barcode product barcode generator generate product barcode.
    """,
    'images': ['static/description/banner.png'],
    "category" : "Warehouse",
    "version": '1.0.1',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    "depends": [ 'product'],
    "data": [
       "data/data.xml",
       "views/product_view.xml",
    ],
    'installable': True,
    'sequence': 2,
    'price': 12,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: 