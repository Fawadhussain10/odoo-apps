# -*- coding: utf-8 -*-
{
    'name' : 'Vital Signs & Symptoms and Physical Examination',
    'summary': 'Manage Patient Vital Signs & Symptoms and Physical Examination.',
    'description': """
        Manage Patient Vital Signs & Symptoms and Physical Examination.
    """,
    'images': ['static/description/banner.png'],
    'version': '20.0.1.1.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends' : ['pb_hms'],
    'data' : [
        'security/security.xml',
        'security/ir.access.csv',
        'data/hms_vital_symptom_data.xml',
        'views/hms_base_view.xml',
    ],
    'application': False,
    'sequence': 2,
    'price': 105,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: