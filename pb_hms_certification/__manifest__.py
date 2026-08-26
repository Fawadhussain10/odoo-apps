# -*- coding: utf-8 -*-
{
    'name': 'HMS Certificate Management System',
    'summary': """This Module will Add functionality to provide certificate to Patients. Maintain history of certificate allocation.""",
    'description': """
        This Module will Add functionality to provide certificate to Patients. Maintain history of certificate allocation. Certification hospital certificate medical certificate patient certification PB HMS.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ["pb_hms", "pb_certification"],
    'data' : [
        'security/security.xml',
        'security/ir.model.access.csv',
        'report/certificate_report.xml',
        'views/certificate_management_view.xml',
        'views/res_config_views.xml',
        'views/portal_template.xml',
        'views/template.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 2,
    'price': 10,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
