# -*- coding: utf-8 -*-
{ 
    'name': 'Radiology Management',
    'summary': 'Manage Radiology requests, Radiology tests, Invoicing and related history for hospital.',
    'description': """
        This module add functionality to manage Radiology flow. radiology management system Hospital Management lab tests radiology invoices radiology test results PB HMS.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_base', 'pb_hms_documents_preview'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'report/radiology_prescription.xml',
        'report/radiology_report.xml',
        'report/radiology_request_results.xml',

        'data/mail_template.xml',
        'data/data.xml',
        'data/digest_data.xml',

        'views/radiology_request_view.xml',
        'views/radiology_test_view.xml',
        'views/radiology_patient_test_view.xml',
        'views/hms_base_view.xml',
        'views/res_config.xml',
        'views/portal_template.xml',
        'views/templates_view.xml',
        'views/radiology_view.xml',
        'views/digest_view.xml',

        'views/menu_item.xml',
    ],
    'demo': [
        'data/radiology_demo.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 61,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: