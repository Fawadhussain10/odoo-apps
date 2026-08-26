# -*- coding: utf-8 -*-
{
    'name': 'HMS Subscriptions (Appointment)',
    'version': '19.0.1.0.0',
    'summary': 'Manage Subscription in Hospital Management System.',
    'description': """
        Manage Subscriptions in Hospital Management System Appointment subscription package hms package Manage Subscription in Hospital Management System in Appointments pb hms PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/hms_contract_view.xml',
        'views/pb_hms_views.xml',
        'views/hms_subscription_view.xml',
        'report/report_subscription.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 61,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: