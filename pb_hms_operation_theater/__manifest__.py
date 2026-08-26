# -*- coding: utf-8 -*-
{
    'name': 'HMS Operation Theater Booking',
    'summary': 'Manage Operation Theater Advance booking in Hospital to utilize OT more efficiently',
    'description': """
        HMS Operation Theater Booking packbytes odoo pb hms medical hospital management system Manage Operation Theater Advance booking in Hospital to utilize OT more efficiently.
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'version': '19.0.1.0.0',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_hospitalization'],
    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'reports/ot_report_template.xml',
        'wizard/ot_report_views.xml',
        'views/ot_view.xml',
        'views/hms_base.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 36,
    'currency': 'USD',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
