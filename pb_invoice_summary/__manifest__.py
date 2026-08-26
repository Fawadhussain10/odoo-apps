# -*- coding: utf-8 -*-
{
    'name' : 'Invoice Summary Report By PackBytes',
    'summary': 'Invoice Summary Report By PackBytes',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'depends' : ['account'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'description': """
        Invoice Summary Report By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/account_view.xml',
        'views/invoice_summary_view.xml',
        'reports/report_invoice_summary.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 51,
    'currency': 'USD',

}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: