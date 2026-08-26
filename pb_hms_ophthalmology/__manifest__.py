# -*- coding: utf-8 -*-
{
    'name': 'Hospital Management System for Ophthalmology',
    'version': '19.0.1.0.0',
    'summary': 'Hospital Management System for Ophthalmology  By PackBytes',
    'description': """
        Hospital Management System for Ophthalmology. Ophthalmology system for hospitals With this module you can manage Eye Patients pb hms packbytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'report/ophthalmology_report.xml',
        'views/pb_hms_views.xml',
        'views/hms_ophthalmology_view.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: