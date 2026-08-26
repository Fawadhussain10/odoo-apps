# -*- coding: utf-8 -*-
{
    'name' : 'Radiology WhatsApp Notification',
    'summary': 'Send WhatsApp notification to patient for Radiology Request and Results.',
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'license': 'OPL-1',
    'depends' : ['pb_whatsapp','pb_radiology'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'description': """
        Send WhatsApp notification to patient for Radiology Request and Results.
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
    'price': 16,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
