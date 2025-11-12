{
    'name': 'POS Punjab Revenue Authority (PRA) Integration',
    'version': '18.0.0.1',
    'category': 'Point of Sale',
    'summary': 'Integrate Odoo POS with PRA for invoice synchronization',
    'description': 'Sync POS invoices with Punjab Revenue Authority (PRA) and print PRA invoice numbers and QR codes on receipts.',
    'author': "Fawad Hussain (Developer) & Umer Hayat (Functional Consultant)",
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        # 'data/pra_sync_cron.xml',
        'security/group_rules.xml',
        'views/views.xml',
        'views/pos_payment_ext_view.xml',
        'views/product_template_ext.xml',
        'views/pra_log_history_view.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pra_integration/static/src/js/**/*',
            'pra_integration/static/src/xml/order_receipt.xml',
        ]

    },
    'license': 'LGPL-3',
    'price': 175,
    'currency': "EUR",
    'images': ['static/description/banner.png'],
    'auto_install': False,
    'installable': True,
    'application': False,
}
