# -*- coding: utf-8 -*-
{ 
    'name': 'Hospital Ambulance Management',
    'summary': 'Hospital Ambulance Management System by PackBytes',
    'description': """
        This Module will install Ambulance Module, which will help to register Ambulance bookings, Fleet management, Invoicing and related tracking. Packbytes pb hms medical hospital hims.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms','fleet'],
    'data': [
        'security/hms_security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/ambulance_views.xml',
        'views/hms_base_view.xml',
        'views/res_config_view.xml',
        'views/menu_items.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 2,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: