# -*- coding: utf-8 -*-
{ 
    'name': 'Hospital Blood Bank Management',
    'summary': 'Hospital Blood Bank Management System by PackBytes',
    'description': """
        This Module will install Blood Bank Module, which will help to register user, and managed blood in the Blood Bank. Packbytes pb hms medical hospital hims.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms','product_expiry'],
    'data': [
        'security/hms_security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/blood_bank_views.xml',
        'views/partner_view.xml',
        'views/patient_view.xml',
        'views/stock_view.xml',
        'views/res_config_view.xml',
        'views/menu_items.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 2,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: