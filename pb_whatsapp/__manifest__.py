# -*- coding: utf-8 -*-
{
    'name' : 'WhatsApp Integration',
    'summary': 'Odoo WhatsApp Integration to send Watsapp messages from Odoo.',
    'category' : 'Extra-Addons',
    'version': '19.0.1.0.0',
    'license': 'OPL-1',
    'depends' : ['hr'],
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'description': """
        Odoo WhatsApp Integration to send Watsapp messages from Odoo. Notification WhatsApp to customer or users, Pb hms.
    """,
    'images': ['static/description/banner.png'],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/data.xml",
        "wizard/create_whatsapp_message_view.xml",
        "wizard/whatsapp_messages_view.xml",

        "views/message_template_view.xml",
        "views/message_view.xml",
        "views/announcement_view.xml",
        "views/partner_view.xml",
        "views/company_view.xml",
        "views/menu_item.xml",
    ],
    'assets': {
        'web.assets_backend': [
            'pb_whatsapp/static/src/scss/custom_backend.scss',
        ]
    },
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 41,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: