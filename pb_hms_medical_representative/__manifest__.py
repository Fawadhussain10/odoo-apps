# -*- coding: utf-8 -*-
{
    'name': 'Medical Representative',
    'summary': 'Manage Medical Representative data and their visits for Hospital.',
    'description': """
        Functionality to manage Medical Representative data and their visits pb hms hospital management system medical represenative.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ["pb_hms"],
    'data' : [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/data.xml',
        'views/mr_view.xml',
        'views/res_config_view.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 2,
    'price': 25,
    'currency': 'USD',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: