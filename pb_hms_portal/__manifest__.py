# -*- coding: utf-8 -*-
{
    'name' : 'Hospital Patient Portal Management',
    'summary' : 'This Module Adds Hospital Portal facility for Patients to allow access to their appointments and prescriptions',
    'description' : """
        This Module Adds Hospital Portal facility for Patients to allow access to their appointments and prescriptions HMS Website Portal pb hms hospital management system medical.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends' : ['portal','pb_hms','website'],
    'data' : [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/email_template.xml',
        'data/data.xml',
        'views/pb_hms_view.xml',
        'views/template.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'web/static/lib/Chart/Chart.js',
            'pb_hms_portal/static/src/js/portal_chart.js'
        ]
    },
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 51,
    'currency': 'USD',
}
