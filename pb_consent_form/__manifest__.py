# -*- coding: utf-8 -*-
{
    'name': 'Electronic Consent Form',
    'summary': """Electronic Consent Forms for Employees and Customers.""",
    'description': """
        Electronic Consent Forms for employees and customers.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Extra Addons',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ["mail","portal"],
    'data' : [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'report/consent_document_report.xml',
        'views/consent_form_view.xml',
        'views/portal_template.xml',
        'views/menu_item.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 66,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: