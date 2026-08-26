# -*- coding: utf-8 -*-
{
    "name": "Survey for hospital Services", 
    'summary': 'Survey in Hospital Management System By PackBytes',
    "description": """
        Hospital Survey By PackBytes Manage Survey of hospital Services. Get Avg Survey of Doctor and Department. Survey in Hospital Management System By PackBytes.
    """, 
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    "depends": ['survey', 'pb_hms'],
    "data": [
        "security/ir.model.access.csv",
        "data/mail_template.xml",
        "views/appointment_view.xml",
        "views/res_config_view.xml",
    ],
    'installable': True,
    'application': False,
    'sequence': 2,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: