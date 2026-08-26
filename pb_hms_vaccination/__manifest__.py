# -*- coding: utf-8 -*-
{
    'name': 'Hospital Vaccination Management',
    'summary': 'Hospital Vaccination Management to manage patient Vaccination flow and history',
    'description': """
        This Module will add a Page in Patient for managing Vaccine for Paediatrics in HMS.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'wizard/create_vaccination_view.xml',
        'views/res_config.xml',
        'views/vaccination_view.xml',
        'views/menu_item.xml',
        'report/vaccination_report.xml',
    ], 
    'demo': [
        'demo/vaccine_demo.xml'
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 30,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
