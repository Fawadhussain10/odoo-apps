# -*- coding: utf-8 -*-
{
    'name': 'Patient Insurance Management System',
    'summary': 'Patient Insurance Management for Hospital Appointment related Claims',
    'description': """
        Patient Insurance Management for Appointment and related Claims. Hospital Management with Insurance Claim.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'version': '19.0.1.0.0',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms', 'pb_document_base', 'pb_invoice_split'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'report/claim_report.xml',
        'report/claim_sheet_report.xml',
        'views/hms_base_view.xml',
        'views/tpa_view.xml',
        'views/insurance_view.xml',
        'views/claim_view.xml', 
        'views/portal_template.xml',
        'views/claim_sheet_view.xml',
        'views/menu_items.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 2,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: