# -*- coding: utf-8 -*-
{
    'name' : 'Hospital WhatsApp Notification',
    'summary': 'Send WhatsApp notification to patient on Patient creation and Appointment Confirmation.',
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'license': 'OPL-1',
    'depends' : ['pb_whatsapp','pb_hms','pb_whatsapp_meta'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'description': """
        Send WhatsApp notification to patient on Patient creation and Appointment Confirmation.
    """,
    'images': ['static/description/banner.png'],
    "data": [
        "data/data.xml",
        "views/company_view.xml",
        "views/pb_hms_view.xml",
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 20,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
