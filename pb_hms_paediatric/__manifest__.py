# -*- coding: utf-8 -*-
{
    'name': 'Hospital Management System for Paediatrics ( Pediatric )',
    'version': '19.0.1.0.0',
    'summary': 'Hospital Management System for Paediatrics',
    'description': """
        Hospital Management System for Paediatrics pediatric. HealthCare Gynec system for hospitals With this module you can manage : - Child Patients - Maintain Child Growth Register - Child Vaccination pb hms packbytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_vaccination'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/weight_data.xml',
        'data/height_data.xml',
        'data/head_data.xml',
        'data/data.xml',
        'views/pb_hms_views.xml',
        'views/hms_paediatric_view.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 101,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
