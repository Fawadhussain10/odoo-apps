# -*- coding: utf-8 -*-
{
    'name': 'Rating in Hospital Services',
    'version': '19.0.1.0.0',
    'summary': 'Rating in Hospital Management System By PackBytes',
    'description': """
        Manage Rating of hospital Services. Get Avg Rating of Doctor and Department. Rating in Hospital Management System By PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms', 'rating'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'data/data.xml',
        'views/pb_rating_view.xml',
        'views/pb_hms_views.xml',
        'views/res_config_view.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
