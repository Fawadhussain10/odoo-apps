# -*- coding: utf-8 -*-
{
    'name': 'Set Patient/Physician/User image using Webcam',
    'version': '19.0.1.0.0',
    'summary': 'Set Patient/Physician/User image using Webcam Image By PackBytes',
    'description': """
        Set Patient/Physician/User image using Webcam Image By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_base', 'pb_webcam'],
    'data': [
        'view/hms_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 15,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: