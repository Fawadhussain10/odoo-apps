# Copyright (C) PackBytes.
{
    "name": "PDC Cheque Management",
    "author": "PackBytes",
    "website": "https://www.packbytes.com",
    "support": "sales@packbytes.com",
    "category": "Accounting",
    "license": "OPL-1",
    "summary": "Post-dated cheque management for customers and vendors: register, deposit, clear, return and bounce cheques with automatic journal entries, smart buttons and PDF reports.",
    "description": """
Post-Dated Cheque Management
============================
Manage customer and vendor post-dated cheques in their own app. Each state change posts
the right journal entries, and the module adds kanban, calendar and analysis views,
due-date reminders, and voucher, register and partner-wise PDF reports.
Works on every Odoo 20 edition.
""",
    "version": "20.0.1.0.0",
    "depends": [
        "account",
    ],
    "data": [
        "data/ir_sequence.xml",
        "data/account_data.xml",
        "data/ir_cron_cust.xml",
        "data/ir_cron_ven.xml",
        "data/mail_templates.xml",
        "security/ir.access.csv",
        "security/pdc_security.xml",
        "report/pdc_payment_report_views.xml",
        "report/pdc_customer_report.xml",
        "views/res_config_settings_views.xml",
        "wizard/pdc_payment_wizard_views.xml",
        "wizard/pdc_multi_action_views.xml",
        "wizard/pdc_customer_report_wizard_views.xml",
        "views/views.xml",
        "views/res_partner_views.xml",
        "views/pdc_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pb_pdc/static/src/scss/pdc.scss",
        ],
    },

    "images": ["static/description/banner.png"],
    "application": True,
    "auto_install": False,
    "installable": True,
    "price": 150,
    "currency": "EUR",
}
