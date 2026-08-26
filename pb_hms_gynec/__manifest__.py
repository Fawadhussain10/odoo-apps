# -*- coding: utf-8 -*-
{
    'name': 'Hospital Management System for Gynecologist',
    'version': '19.0.1.0.0',
    'summary': 'Hospital Management System for Gynecologist',
    'description': """
        Hospital Management System for Gynecologist. HealthCare Gynec system for hospitals With this module you can manage : - Gynec Patients - Maintain Child Birth Register - Record Abdominal Vaginal and Rectal examinations - Manage and print the reports for Pelvic Sonogrpahy, Follical Sonography and Obstetric Sonography - Manage the Appointments for Pregnancies and hospitalizations. - Record Colposcopy Mamography and Pap test  pb hms packbytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_hospitalization'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',    
        'data/data.xml',
        'views/hms_gynec_view.xml',
        'views/hms_base_view.xml',
        'views/hms_appointment_view.xml',
        'views/hms_pregnancy.xml',
        'views/hms_sonography_view.xml',
        'views/hms_childbirth_view.xml',
        'report/report_sono_follical.xml',
        'report/report_birth_card.xml',
        'report/report_sono_pelvis.xml',
        'report/report_sono_obstetric.xml',
        'report/report_pregnancy.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 151,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: