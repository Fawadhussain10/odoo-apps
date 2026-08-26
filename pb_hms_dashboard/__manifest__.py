# -*- coding: utf-8 -*-
{
    "name": "PB HMS Dashboards", 
    "summary": "HMS Dashboard for users. Separte deashboard detials for doctor, receptionist and admin user so they can get thier related infrmation and statistics from single view",
    "description": """
        HMS Dashboard for users. Separte deashboard detials for doctor, receptionist and admin user so they can get thier related infrmation and statistics from single view. Hospital Management System hospital dashboard physician dashboard admin dashboard PB HMS.
    """, 
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    "depends": ["pb_hms"],
    "data": [
        "security/security.xml",
        "views/user_dashboard_view.xml",
        "views/user_view.xml",
    ],
    'assets': {
        'web.assets_backend': [
            'pb_hms_dashboard/static/src/scss/pb_dashboard.scss'
        ]
    },
    'application': False,
    'sequence': 2,
    'price': 75,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: