# -*- coding: utf-8 -*-
{
    'name': 'Hospital Nursing Operations',
    'version': '19.0.1.0.0',
    'summary': 'System for managing Hospital Nursing Operations like Hospitalization Ward Round & Evaluations.',
    'description': """
        System for managing Hospital Nursing Operations like Hospitalization Ward Round & Evaluations. This Module Helps You To Manage Your Hospital Ward Rounds medical pb hms packbytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms','pb_hms_hospitalization'],
    'data': [
        'security/ir.model.access.csv',
        'view/pb_hms_nursing.xml',
        'view/hms_base.xml',
        'view/menu_item.xml',
        'data/data.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: