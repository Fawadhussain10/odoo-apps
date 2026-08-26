# -*- coding: utf-8 -*-
{
    'name': 'Partner Incentive / Commission Management',
    'category': 'Accouting',
    'summary': 'Option to give commission & payment to Customer, Referral, Employee and third party contact in system',
    'description': """
        Incentive for Employees Incentive Management application to manage user commission for different objects.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'wizard/create_commission_bill_views.xml',
        'reports/commission_sheet_report.xml',
        'views/commission_view.xml',
        'views/commission_sheet_view.xml',
        'views/partner_view.xml',
        'views/res_config_settings_views.xml',
        'views/account_view.xml',
        'views/menu_item.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 36,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: