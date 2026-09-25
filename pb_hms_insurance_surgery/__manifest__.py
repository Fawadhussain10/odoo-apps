# -*- coding: utf-8 -*-
{
    'name': 'Surgery Insurance Management System',
    'summary': 'Patient Insurance Management for Surgery and related invoicing',
    'description': """
        Patient Insurance Management for Surgery and related invoicing. Hospital Management with Insurance Claim.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'version': '20.0.1.0.0',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_surgery', 'pb_hms_insurance'],
    'data': [
        'views/hms_base_view.xml',
        'views/insurance_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 3,
    'price': 20,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: