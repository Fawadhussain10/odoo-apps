# -*- coding: utf-8 -*-
{
    'name': 'Video Consultation/Call/Conference with Jitsi Meet',
    'version': '19.0.1.0.0',
    'summary': 'Video Consultation/Call/Conference using Jitsi Meet By PackBytes',
    'description': """
        Video Consultation/Call/Conference using Jitsi Meet By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms', 'pb_jitsi_meet'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'view/pb_video_call_view.xml',
        'view/pb_hms_views.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 21,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
