# -*- coding: utf-8 -*-
{
    'name': 'Dental Chart ( Odontology )',
    'version': '19.0.1.0.0',
    'summary': 'Dental Chart ( Odontology ) By PackBytes',
    'description': """
        Hospital Management System for Dental. Odontology management system for hospitals With this module you can manage Eye Patients pb hms packbytes dentist.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_dental'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/tooth_data.xml',
        'views/hms_dental_view.xml',
        'views/pb_hms_views.xml',
        'views/template.xml',
        'views/menu_item.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'pb_hms_dental_chart/static/src/scss/custom.scss',
            'pb_hms_dental_chart/static/src/js/popper.js',
            'pb_hms_dental_chart/static/src/js/dental_chart.js'
        ],
    },
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 201,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: