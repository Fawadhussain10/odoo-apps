# -*- coding: utf-8 -*-
{
    'name': 'Video Call/Conference Call with Jitsi Meet',
    'version': '19.0.1.0.0',
    'summary': 'Video Call/Conference Call with Jitsi Meet By PackBytes',
    'description': """
        Video Call/Conference Call with Jitsi Meet By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Extra-Addons',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['calendar','pb_video_call'],
    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'view/res_config_view.xml',
        'view/templates_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 41,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: