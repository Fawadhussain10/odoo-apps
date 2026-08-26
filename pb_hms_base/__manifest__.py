# -*- coding: utf-8 -*-
{
    'name': 'Base - Hospital Management System ( PackBytes HMS )',
    'summary': 'Hospital Management System Base for further flows',
    'description': """
        Hospital Management System for managing Hospital and medical facilities flows Medical Flows PB HMS. This module helps you to manage your hospitals and clinics which includes managing Patient details, Doctor details, Prescriptions, Treatments, Appointments with concerned doctors, Invoices for the patients. You can also define the medical alerts of a patient and get warining in appointment,treatments and prescriptions.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['account', 'stock', 'hr', 'product_expiry', 'base_geolocalize'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'report/paper_format.xml',
        'report/report_layout.xml',
        'report/report_invoice.xml',

        'data/sequence.xml',
        'data/mail_template.xml',
        'data/company_data.xml',
        'data/patient_map_data.xml',

        'views/hms_base_views.xml',
        'views/patient_view.xml',
        'views/patient_map_view.xml',
        'views/physician_view.xml',
        'views/product_view.xml',
        'views/drug_view.xml',
        'views/account_view.xml',
        'views/res_config_settings.xml',
        'views/menu_item.xml',
    ],
    'demo': [
        'demo/company_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pb_hms_base/static/src/scss/report.scss',
            'pb_hms_base/static/src/scss/sidebar.scss',
            'pb_hms_base/static/src/js/required_field_notification.js',
            # leaflet.js/.css are deliberately NOT bundled here - patient_map.js
            # lazy-loads them on demand (loadJS/loadCSS) only when the map is
            # actually opened, so the ~150KB library doesn't load on every
            # single backend page for users who never view the map.
            'pb_hms_base/static/src/map/patient_map.scss',
            'pb_hms_base/static/src/map/patient_map.js',
            'pb_hms_base/static/src/map/patient_map.xml',
            # 'map' view type for hms.patient itself (List/Kanban/Map/Form
            # switcher on the Patients action) - reuses the same lazy Leaflet
            # loader and .pb-map-* CSS as the standalone map above.
            'pb_hms_base/static/src/map/patient_map_view.js',
            'pb_hms_base/static/src/map/patient_map_view.xml',
        ],
    },
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 36,
    'currency': 'USD',
}


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: