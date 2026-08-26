# -*- coding: utf-8 -*-
{
    'name': 'Facility Management System',
    'category': 'Extra Tools',
    'version': '19.0.1.0.0',
    'author' : 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'summary': """Application to manage Facility of office or premises in odoo""",
    'description': """
        Application to manage Facility of office or premises in odoo. Facility Management Cleaning of office Cleaning management Office Cleaning Maintenance Register Cleaning Register Premises Cleaning Activity Register pb hms hopital management system medical.
    """,
    'images': ['static/description/banner.png'],
    'depends': ["base","mail"],
    'data' : [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/facility_views.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'auto_install': False,
    'price': 25,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: