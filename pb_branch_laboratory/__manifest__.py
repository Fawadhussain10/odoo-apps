# -*- coding: utf-8 -*-
{
    'name': 'Laboratory Multiple Branch/Unit Operation',
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'summary': """Laboratory Multiple Branch/Unit Operation for Hospital Management System""",
    'description': """
        Laboratory Multiple Branch/Unit Operation for Hospital Management System.
    """,
    'images': ['static/description/banner.png'],
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1', 
    "depends": ['pb_hms_branch','pb_laboratory'],
    "data": [
        'views/laboratory_view.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 26,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: