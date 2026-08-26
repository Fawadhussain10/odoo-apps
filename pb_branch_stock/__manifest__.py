# -*- coding: utf-8 -*-
{
    'name': 'Multiple Branch/Unit Operation for Inventory',
    'version': '19.0.1.0.0',
    'category': 'stock',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'summary': """Multiple Branch/Unit Operation for Inventory""",
    'description': """
        Multiple Branch/Unit Operation for Inventory.
    """,
    'images': ['static/description/banner.png'],
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1', 
    "depends": ['stock','pb_branch_base','web','base'],
    "data": [
        'views/stock_location_view.xml',
        'views/stock_move_view.xml',
        'views/stock_picking_view.xml',
        'views/stock_warehouse_view.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 12,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: