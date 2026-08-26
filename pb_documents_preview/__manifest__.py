# -*- coding: utf-8 -*-
{
    'name' : 'Documents Preview',
    'summary': 'PB Hospital / Patient Documents Preview.',
    'description': """
        Hospital / Patient Documents Preview. Document management system document preview pb hms medical.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends' : ['portal','pb_document_base'],
    'data' : [
        'views/template.xml',
    ],
    "cloc_exclude": [
        "static/**/*", # exclude all files in a folder hierarchy recursively
    ],
    'application': False,
    'sequence': 0,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: