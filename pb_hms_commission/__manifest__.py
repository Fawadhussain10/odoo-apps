# -*- coding: utf-8 -*-
{
    'name': 'Hospital Doctor Commission Management',
    'category': 'Medical',
    'summary': 'Option to give commission or payment to referring doctor, visiting dr and third party person in HMS',
    'description': """
        Hospital Management System with patient commission for referring doctor, for visiting doctor and commission for third party. Medical Flows PB HMS.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms','pb_commission'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/hms_base_view.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 14,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: