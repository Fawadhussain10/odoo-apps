# -*- coding: utf-8 -*-
{
    'name': 'Invoice Splitting',
    'summary': """This Module will Add functionality of Invoice Splitting.""",
    'description': """
        This Module will Add functionality of Invoice Spliting of selected invoices of a customer. split invoice invoice spliting invoice split.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ["account"],
    'data' : [
        'security/ir.model.access.csv',
        'wizard/split_wizard_view.xml',
        'views/account_view.xml',
    ],
    'installable': True,
    'sequence': 1,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: