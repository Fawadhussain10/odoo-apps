# -*- coding: utf-8 -*-
{
    'name': 'Document Management Base',
    'summary': 'Manage Documents at single place or see all related documents directly.',
    'description': """
        Manage Documents at single place or see all related documents directly on patint. Patient Document Management System. hospital management medical management PB HMS.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['mail', 'hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'view/document_view.xml',
        'view/attachment_view.xml',
        'view/menu_item.xml',
    ],
    'application': False,
    'sequence': 2,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: