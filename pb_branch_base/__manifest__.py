# -*- coding: utf-8 -*-
{
    'name': 'Multiple Branch / Unit Operation Base for Odoo Applications',
    'version': '19.0.1.0.0',
    'category': 'sale',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'summary': """Multiple Branch / Unit Operation Base for Odoo Applications""",
    'description': """
        Multiple Branch / Unit Operation Base for Odoo Applications.
    """,
    'images': ['static/description/banner.png'],
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1', 
    "depends": ['base','web'],
    "data": [
        'security/security.xml',
        'views/partner_view.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: