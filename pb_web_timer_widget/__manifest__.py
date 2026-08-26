# -*- coding: utf-8 -*-
{
    'name': "Web Timer Widget",
    'category': "web",
    'version': '19.0.1.0.0',
    'summary': """Add timer widget on web view.""",
    'description': """
        This module widget which allows you to set timer on any field by passing your start and end date as parameter. start stop timer working time.
    """,
    'images': ['static/description/banner.png'],
    "website": 'https://www.packbytes.com',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'license': 'OPL-1',
    'depends': ['base', 'web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'pb_web_timer_widget/static/src/js/TimeCounter.js',
            'pb_web_timer_widget/static/src/js/TimeCounter.xml',
        ]
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    "price": 14,
    "currency": "USD",
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: