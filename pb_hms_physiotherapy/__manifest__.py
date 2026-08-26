# -*- coding: utf-8 -*-
{ 
    'name': 'Physiotherapy Hospital Management System',
    'summary': 'Physiotherapy Hospital Management System to manage Physiotherapy related flows.',
    'description': """
        Physiotherapy Hospital Management System to manage Physiotherapy related flows.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/data.xml',
        'data/physiotherapy_note_data.xml',
        'wizard/physiotherapy_view_wizard.xml',
        'views/res_config.xml',
        'views/physiotherapy_view.xml',
        'views/pb_hms_views.xml',
        'views/menu_items.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 101,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: