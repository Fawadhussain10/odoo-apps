# -*- coding: utf-8 -*-
{
    'name' : 'HMS Portal User Image',
    'summary': 'Added option to add image from the portal view for users by PackBytes',
    'version': '19.0.1.0.0',
    'category' : 'Extra Tools',
    'depends' : ['portal'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'description': """
        Added option to set user image from the portal view by PackBytes.
    """,
    'images': ['static/description/banner.png'],
    'data': [
        'views/template.xml',
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 21,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: