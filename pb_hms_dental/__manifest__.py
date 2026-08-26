# -*- coding: utf-8 -*-
{
    'name': 'Dental Hospital Management System ( Odontology )',
    'version': '19.0.1.0.0',
    'summary': 'Hospital Management System for Dental ( Odontology ) By PackBytes',
    'description': """
        Hospital Management System for Dental. Odontology management system for hospitals With this module you can manage Eye Patients pb hms packbytes dentist.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms', 'pb_hms_documents_preview'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/tooth_data.xml',
        'views/hms_dental_view.xml',
        'views/pb_hms_views.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 71,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: