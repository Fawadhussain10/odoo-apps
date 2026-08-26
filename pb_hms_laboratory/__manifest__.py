# -*- coding: utf-8 -*-
{ 
    'name': 'Hospital Laboratory Management',
    'summary': 'Manage Lab requests, Lab tests, Invoicing and related history for hospital.',
    'description': """
        This module add functionality to manage Laboratory flow. laboratory management system Hospital Management lab tests laboratory invoices laboratory test results PB HMS.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms','pb_laboratory'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'report/report_pb_lab_prescription.xml',
        'report/lab_report.xml',
        'report/report_medical_advice.xml',

        'views/hms_base_view.xml',
        'views/laboratory_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 16,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: