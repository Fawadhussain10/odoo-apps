# -*- coding: utf-8 -*-
{
    'name': 'Certificate Management System',
    'summary': """This Module will Add functionality to provide certificate to Customers, Vendors, Employees and Users. Maintain history of certificate allocation.""",
    'description': """
        This Module will Add functionality to provide certificate to Customers, Vendors, Employees and Users. Maintain history of certificate allocation. Certification User Certification Employee Certification Employee Certificate Product Warranty Certificate.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Extra Addons',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ["mail", "digest"],
    'data' : [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/digest_data.xml',
        'views/certificate_management_view.xml',
        'views/digest_view.xml',
        'report/certificate_report.xml',
        'views/menu_item.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 35,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: