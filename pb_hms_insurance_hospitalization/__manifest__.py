# -*- coding: utf-8 -*-
{
    'name': 'Hospitalization Insurance Management System',
    'summary': 'Patient Insurance Management for Hospitalization and related Claims',
    'description': """
        Patient Insurance Management for Hospitalization and related Claims. Hospital Management with Insurance Claim.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'version': '19.0.1.0.0',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_hospitalization', 'pb_hms_insurance'],
    'data': [
        'security/ir.model.access.csv',
        'report/claim_report.xml',
        'views/hms_base_view.xml',
        'views/claim_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 3,
    'price': 15,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: