# -*- coding: utf-8 -*-
{
    'name' : 'Hospital SMS Notification',
    'summary': 'Send SMS notification to patient on Patient creation and Appointment Confirmation.',
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'license': 'OPL-1',
    'depends' : ['pb_sms','pb_hms'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'description': """
        Send SMS notification to patient on Patient creation and Appointment Confirmation.
    """,
    'images': ['static/description/banner.png'],
    "data": [
        "data/data.xml",
        "views/company_view.xml",
        "views/hms_base_view.xml",
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 15,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: