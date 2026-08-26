# -*- coding: utf-8 -*-
{ 
    'name': 'Hospital Radiology Management - Hospitalization',
    'summary': 'Manage Radiology requests, Radiology tests flow on - Hospitalization.',
    'description': """
        This module add functionality to manage Radiology flow. radiology management system Hospital Management lab tests radiology invoices radiology test results PB HMS - Hospitalization with Radiology Tests.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_hospitalization','pb_hms_radiology'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'report/report_pb_radiology_prescription.xml',
        'report/discharge_summary_report.xml',
        'report/radiology_report.xml',

        'views/hms_base_view.xml',
        'views/radiology_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 16,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: