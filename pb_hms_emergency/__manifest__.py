# -*- coding: utf-8 -*-
{
    'name': 'Emergency Management for Hospital',
    'version': '19.0.1.0.0',
    'summary': 'Hospital Management System for Emergency Department',
    'description': """
        Hospital Management System for Emergency Department pb hms packbytes Emergency Management for Hospital medical.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_hospitalization'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/data.xml',
        'report/report_emergency.xml',
        'views/hms_emergency_view.xml',
        'views/pb_hms_view.xml',
        'views/res_config.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
