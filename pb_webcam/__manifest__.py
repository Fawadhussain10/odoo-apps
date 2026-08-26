# -*- coding: utf-8 -*-
{
    'name': 'Set User/Partner/Customer image using Webcam',
    'version': '19.0.1.0.0',
    'summary': 'Set User/Partner/Customer image using Webcam Image By PackBytes',
    'description': """
        Set User/Partner/Customer image using Webcam Image By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Extra-Addons',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['web'],
    'data': [
        'view/pb_webcam_view.xml',
        'view/templates_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pb_webcam/static/src/scss/backend.scss',
        ],    
    },
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
