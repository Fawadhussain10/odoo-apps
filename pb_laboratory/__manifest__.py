# -*- coding: utf-8 -*-
{ 
    'name': 'Laboratory Management',
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
    'depends': ['pb_hms_base'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'report/report_pb_lab_prescription.xml',
        'report/lab_report.xml',
        'report/lab_request_results.xml',
        'report/lab_samples_report.xml',
        'report/paper_format.xml',

        'data/mail_template.xml',
        'data/laboratory_data.xml',
        'data/lab_uom_data.xml',
        'data/lab_sample_type_data.xml',
        'data/digest_data.xml',
        
        'views/lab_uom_view.xml',
        'views/laboratory_request_view.xml',
        'views/laboratory_view.xml',
        'views/laboratory_test_view.xml',
        'views/laboratory_patient_test_view.xml',
        'views/laboratory_sample_view.xml',
        'views/hms_base_view.xml',
        'views/res_config.xml',
        'views/portal_template.xml',
        'views/templates_view.xml',
        'views/digest_view.xml',

        'views/menu_item.xml',
    ],
    'demo': [
        'data/laboratory_demo.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 61,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: