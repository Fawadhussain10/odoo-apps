# -*- coding: utf-8 -*-
{
    'name': 'Hospital Management System for Aesthetic',
    'version': '19.0.1.0.0',
    'summary': 'Hospital Management System for Aesthetic By PackBytes',
    'description': """
        Hospital Management System for Aesthetic. Aesthetic management system for hospitals With this module you can manage Aesthetic Patients pb hms packbytes dentist.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_portal', 'pb_documents_preview'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'report/aesthetic_wish_report.xml',
        'report/aesthetic_history_report.xml',
        'report/aesthetic_phototype_report.xml',
        'views/hms_aesthetic_base_view.xml',
        'views/pb_patient_view.xml',
        'views/pb_hms_views.xml',
        'views/hms_aesthetic_wish_view.xml',
        'views/portal_aestheticwish.xml',
        'views/portal_patient_history.xml',
        'views/portal_aesthetic_phototype.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 2,
    'price': 101,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
