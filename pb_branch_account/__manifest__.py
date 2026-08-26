# -*- coding: utf-8 -*-
{
    'name': 'Multiple Branch / Unit Operation for Accounting',
    'version': '19.0.1.0.0',
    'category': 'Account',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'summary': """ Multiple Branch / Unit Operation for Accounting """,
    'description': """
        Multiple Branch / Unit Operation for Accounting.
    """,
    'images': ['static/description/banner.png'],
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1', 
    "depends": ['pb_branch_base','account'],
    "data": [
        'views/account_move_view.xml',
        'views/account_payment_view.xml',
        'views/branch_base_view.xml',
        'report/invoice_report_view.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 20,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: