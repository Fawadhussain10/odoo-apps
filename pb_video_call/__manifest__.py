# -*- coding: utf-8 -*-
{
    'name': 'Video Call/Conference Call Base',
    'version': '19.0.1.0.0',
    'summary': 'Video Call/Conference Call Base By PackBytes',
    'description': """
        Video Call/Conference Call Base By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Extra-Addons',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['calendar'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/mail_template.xml',
        'data/calendar_mail_template.xml',
        'view/pb_video_call_view.xml',
        'view/calendar_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pb_video_call/static/src/xml/systray.xml',
            'pb_video_call/static/src/js/systray.js'
        ],    
    },
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: