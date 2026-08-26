# -*- coding: utf-8 -*-
{
    'name': 'Clinic - Hospital Management System ( PackBytes HMS )',
    'summary': 'Hospital Management System for managing Hospital and medical facilities flows',
    'description': """
        Hospital Management System for managing Hospital and medical facilities flows Medical Flows PB HMS Clinic Management Manage Clinic. This module helps you to manage your hospitals and clinics which includes managing Patient details, Doctor details, Prescriptions, Treatments, Appointments with concerned doctors, Invoices for the patients. You can also define the medical alerts of a patient and get warining in appointment,treatments and prescriptions.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_base', 'pb_web_timer_widget', 'website', 'digest'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'report/patient_cardreport.xml',
        'report/report_medical_advice.xml',
        'report/report_prescription.xml',
        'report/appointment_report.xml',
        'report/evaluation_report.xml',
        'report/treatment_report.xml',
        'report/procedure_report.xml',

        'data/sequence.xml',
        'data/mail_template.xml',
        'data/hms_data.xml',
        'data/digest_data.xml',

        'wizard/cancel_reason_view.xml',
        'wizard/pain_level_view.xml',
        'wizard/reschedule_appointments_view.xml',

        'views/hms_base_views.xml',
        'views/patient_view.xml',
        'views/physician_view.xml',
        'views/evaluation_view.xml',
        'views/appointment_view.xml',
        'views/diseases_view.xml',
        'views/medicament_view.xml',
        'views/prescription_view.xml',
        'views/medication_view.xml',
        'views/treatment_view.xml',
        'views/procedure_view.xml',
        'views/resource_cal.xml',
        'views/medical_alert.xml',
        'views/account_view.xml',
        'views/product_kit_view.xml',
        'views/template.xml',
        'views/res_config_settings_views.xml',
        'views/digest_view.xml',
        'views/menu_item.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pb_hms/static/src/js/hms_graph_field.js',
            'pb_hms/static/src/js/hms_graph_field.xml',
            'pb_hms/static/src/js/hms_graph_field.scss',
            'pb_hms/static/src/scss/custom.scss',
        ]
    },
    'demo': [
        'demo/doctor_demo.xml',
        'demo/patient_demo.xml',
        'demo/appointment_demo.xml',
        'demo/medicament_demo.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
