{
    "name": "FBR Integration POS",
    "version": "18.0.0.1",
    "summary": "Send invoices to FBR (Federal Board of Revenue Pakistan)",
    "description": "Integrate Odoo invoices with FBR's real-time invoice reporting system.",
    "category": "Accounting",
    "author": "Fawad Hussain (Developer) & Umer Hayat (Functional Consultant)",
    "depends": ["base", "point_of_sale", "product", "account"],
    "data": [
        "views/setting.xml",
        "views/move.xml",
        "views/views.xml",
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'fbr_integration_pos/static/src/**/*',
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    'price': 200,
    'currency': "USD",
    'images': ['static/description/banner.png'],
}
