# -*- coding: utf-8 -*-
{
    'name' : 'Patient Body Chart/Image Editor',
    'summary': 'PB Patient Body Chart/Image Editor.',
    'description': """
        Hospital / Patient Image Editor. Patient Body Chart editor pb hms medical.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends' : ['pb_hms','pb_document_base'],
    'data' : [
        'data/data.xml',
        'views/pb_hms_views.xml',
        'views/template.xml',
        'views/res_config_settings_views.xml',
    ],
    "cloc_exclude": [
        "static/src/*",
    ],
    'application': False,
    'sequence': 2,
    'price': 100,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: