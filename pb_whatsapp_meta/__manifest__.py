# -*- coding: utf-8 -*-
{
    'name' : 'WhatsApp Meta API Integration (Whatsapp official API) (BETA)',
    'summary': 'Odoo WhatsApp Integration to send Watsapp messages from Odoo using official Meta API',
    'category' : 'Extra-Addons',
    'version': '19.0.1.0.0',
    'license': 'OPL-1',
    'depends' : ['pb_whatsapp'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'description': """
        Odoo WhatsApp Integration to send Watsapp messages from Odoo. Notification WhatsApp to customer or users, Pb hms Whatsapp official API official whatsapp API.
    """,
    'images': ['static/description/banner.png'],
    "data": [
        'security/ir.model.access.csv',
        "views/company_view.xml",
        "views/whatsapp_view.xml",
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 101,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: