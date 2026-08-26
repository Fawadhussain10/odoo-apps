# -*- coding: utf-8 -*-
{
    'name' : 'Hospital Next Patient Waiting Screen',
    'summary' : 'Hospital Patient Waiting Que Screen to show Next Upcoming Appointment Number and Related detils.',
    'description' : """
        This module provides screen of next patient who is going in consultation. PB HMS Hospital management system.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends' : [ 'website','pb_hms'],
    'data' : [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/template_view.xml',
        'views/waiting_screen_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 2,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: