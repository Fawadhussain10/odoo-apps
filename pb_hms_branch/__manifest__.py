# -*- coding: utf-8 -*-
{
    'name': 'Multiple Branch/Unit Operation for Hospital Management System',
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'summary': """Multiple Branch/Unit Operation for Hospital Management System""",
    'description': """
        Multiple Branch/Unit Operation for Hospital Management System.
    """,
    'images': ['static/description/banner.png'],
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1', 
    "depends": ['pb_branch_base','pb_hms', 'pb_branch_account', 'pb_branch_stock'],
    "data": [
        'views/hms_base_view.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: