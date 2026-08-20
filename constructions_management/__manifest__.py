{
    "name": "Construction Management",
    "version": "19.0.1.0.0",
    "summary": "BOQ, budget, procurement, site inventory, subcontract RA billing, WIP and dashboards for construction projects",
    "description": """
Construction Management
========================
Generic construction ERP built on standard Odoo Project, Purchase, Inventory,
Accounting, Analytic Accounting and Employees. Every quantity and financial
transaction traces through Company -> Project -> WBS -> BOQ Line -> Cost Code
-> Analytic Account.

Covers: reusable BOQ templates with Excel import/export, project BOQ with
immutable approved baselines and revisions, budget and cost control (original,
revised, committed, actual, ETC, EAC, variances), project-wise procurement
(material requests, purchase requisitions/orders), site inventory (receipt,
issue, consumption, return, wastage, transfer, cycle count), subcontract
agreements with RA certificates, work orders and daily site reports, cost
sheets, WIP accounting and revenue recognition, customer progress billing,
earned value / forecasting, quality and HSE registers, equipment and document
control, and role-based dashboards.
""",
    "author": "Fawad Hussain",
    "website": "https://packbytes.com",
    "license": "OPL-1",
    "price": 950.00,
    "currency": "EUR",
    "category": "Industries",
    "application": True,
    "images": [
        "static/description/banner.gif",
    ],
    "depends": [
        "base",
        "mail",
        "web",
        "project",
        "sale_project",
        "purchase",
        "purchase_requisition",
        "purchase_stock",
        "stock",
        "stock_account",
        "account",
        "analytic",
        "hr_timesheet",
    ],
    "data": [
        "security/construction_security.xml",
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/sequences.xml",
        "data/config_data.xml",
        "data/stock_data.xml",
        "data/pakistan_uom_data.xml",
        "views/config_views.xml",
        "views/wbs_views.xml",
        "views/boq_views.xml",
        "views/boq_template_views.xml",
        "views/rate_analysis_views.xml",
        "views/variation_views.xml",
        "views/budget_views.xml",
        "views/material_request_views.xml",
        "views/purchase_ext_views.xml",
        "views/measurement_views.xml",
        "views/ra_certificate_views.xml",
        "views/subcontract_views.xml",
        "views/inventory_views.xml",
        "views/daily_report_views.xml",
        "views/work_order_views.xml",
        "views/cost_sheet_views.xml",
        "views/quality_hse_views.xml",
        "views/equipment_views.xml",
        "views/document_views.xml",
        "views/wip_views.xml",
        "views/progress_certificate_views.xml",
        "wizard/boq_import_wizard_views.xml",
        "report/report_actions.xml",
        "report/boq_report_templates.xml",
        "report/ra_certificate_report_templates.xml",
        "report/progress_certificate_report_templates.xml",
        "report/cost_sheet_report_templates.xml",
        "views/dashboard_views.xml",
        # project_views.xml is the "hub" view with smart buttons to many other stages' actions -
        # always keep it loaded last among view files, right before menus.xml.
        "views/project_views.xml",
        "views/menus.xml",
        "data/demo_boq_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "constructions_management/static/src/dashboard/*.js",
            "constructions_management/static/src/dashboard/*.xml",
            "constructions_management/static/src/dashboard/*.scss",
        ],
    },
    "installable": True,
    "application": True,
}
