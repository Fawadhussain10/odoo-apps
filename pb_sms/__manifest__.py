# -*- coding: utf-8 -*-
{
    'name' : 'Notification SMS',
    'summary': 'Send SMS notification to Employee and Customer.',
    'category' : 'Extra-Addons',
    'version': '19.0.1.0.0',
    'license': 'OPL-1',
    'depends' : ['hr'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'description': """
        Send SMS notification to Employee and Customer.
    """,
    'images': ['static/description/banner.png'],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/company_view.xml",
        "views/sms_view.xml",
        "views/sms_template_view.xml",
        "views/announcement_view.xml",
        "views/partner_view.xml",
        "views/menu_item.xml",
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 20,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: