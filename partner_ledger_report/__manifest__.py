{
    'name': 'Odoo Partner Ledger/Aged Partner Reports',
    'version': '17.0.0.0',
    'summary': 'Partner pdf partner accounting excel report',
    'author': 'Fawad',
    'category': 'Accounting',
    'license':'OPL-1',
    'depends': ['account'],
    'price': 70,
    'currency': 'USD',
    'data': [
        'security/ir.model.access.csv',
        'reports/reports.xml',
        'reports/report_partnerledger.xml',
        'reports/report_aged_partner.xml',
        'wizard/partner_ledger.xml',
        'wizard/excel_report.xml',
        'wizard/account_aged_partner_balance.xml'

    ],
    'installable': True,
    'auto_install': False,
    'images':['static/description/Banner.png'],
}


