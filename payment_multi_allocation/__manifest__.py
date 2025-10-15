{
    'name': 'Payment Multi Allocation / Reconciliation',
    'summary': 'Allocation, Partial Payment Allocation, Payment Distribution, Payment Reconciliation, Partial Payment Distribution, Sales Allocation, Purchase Allocation',
    'author': 'Fawad Hussain',
    "version": "17.0.0.1",
    'category': 'Accounting',
    'description': """
    """,
    'depends': ['account'],
    'data': [
        'views/account_payment_allocation.xml',
        'views/account_partial_reconcile.xml',
        'views/account_full_reconcile.xml',
        'views/account_payment.xml',
        'views/action.xml',
        'views/menu.xml',
        'security/ir.model.access.csv'
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    "license": "OPL-1",
    "price": 100.99,
    "currency": 'EUR',
    'odoo-apps': True,
    'images': [
        'static/description/cover.png'
    ],
}
