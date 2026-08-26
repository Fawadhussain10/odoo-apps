# -*- coding: utf-8 -*-
{
    'name' : 'HMS Online Appointment',
    'summary' : 'Allow patients to Book an Appointment on-line from portal',
    'description' : """
        HMS Website Portal to Book an Appointment online. pb hms medical Allow patients to Book an Appointment online from portal.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends' : ['pb_hms_portal','website_payment','account_payment'],
    'data' : [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/website_page.xml',
        'views/hms_base_view.xml',
        'views/schedule_views.xml',
        'views/template.xml',
        'views/res_config_settings_views.xml',
        'wizard/appointment_scheduler_wizard.xml',
        'wizard/payment_link_views.xml',
        'views/menu_item.xml',
    ],
    'assets': {
        'web.assets_frontend': [        
            'pb_hms_online_appointment/static/src/js/payment_form.js',
            'pb_hms_online_appointment/static/src/js/hms_portal.js',
            'pb_hms_online_appointment/static/src/scss/custom.scss',
        ]
    },
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 70,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: