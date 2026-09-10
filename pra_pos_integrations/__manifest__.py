{
    "name": "PRA POS Integration (Punjab Revenue Authority)",
    "version": "19.0.1.0.0",
    "summary": "Report POS sales to the Punjab Revenue Authority (PRA) e-IMS in real time",
    "description": """
Punjab Revenue Authority - POS / e-IMS Integration
====================================================
Connects Odoo Point of Sale to PRA's Electronic Invoice Monitoring System (e-IMS),
based on PRAL's "POS Component and eIMS" specification:

* Reports every validated POS order to PRA (sandbox or production) as soon as it is paid.
* Stores the PRA fiscal invoice number, request/response and sync status on the order.
* Prints the PRA fiscal invoice number and a verification QR code on the receipt.
* Lets each Point of Sale (branch/counter) be registered with its own PRA POS ID and token.
* Retries orders that failed to sync via a scheduled action, with a manual resync action too.
""",
    "category": "Accounting",
    "author": "Fawad Hussain",
    "website": "https://packbytes.com",
    "license": "LGPL-3",
    "images": ["static/description/banner.png"],
    "depends": ["point_of_sale"],
    "data": [
        "data/pra_cron.xml",
        "views/res_config_settings_views.xml",
        "views/product_template_views.xml",
        "views/pos_payment_method_views.xml",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pra_pos_integrations/static/src/overrides/components/order_receipt.xml",
        ],
    },
    'price': 168,
    'currency': "USD",
    "installable": True,
    "application": True,
}
