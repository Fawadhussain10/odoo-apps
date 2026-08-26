# -*- coding: utf-8 -*-
{
    'name' : 'Invoice Summary Report for Patient By PackBytes',
    'summary': 'Invoice Summary Report for Patient By PackBytes',
    'category' : 'Extra-Addons',
    'depends' : ['pb_hms', 'pb_invoice_summary'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'description': """
        Invoice Summary Report for Patient By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'data': [
        'views/hms_base.xml',
        'reports/report_invoice_summary.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 15,
    'currency': 'USD',

}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: