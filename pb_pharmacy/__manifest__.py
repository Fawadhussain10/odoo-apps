# -*- coding: utf-8 -*-
# Lot blocking related logic reference is taken from OCA module of v8
{
    'name': 'Pharmacy Management',
    'summary': 'Pharmacy Management system. Manage pharmacy operations of sale, purchase, batch pricing and barcoding',
    'description': """
        Pharmacy Management system. Manage pharmacy operations of sale, purchase, batch pricing and barcoding Pharmacy Menus. Barcode generation Batch Wise Pricing Product Expiry Product Manufacture Lock Lot pb hms medical healthcare health care.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms_base', 'pb_product_barcode_generator', 'pb_invoice_with_stock_move', 'pb_invoice_barcode'],
    'data': [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/stock_view.xml",
        "views/product_view.xml",
        "views/invoice_view.xml",
        "report/lot_barcode_report.xml",
        "report/picking_barcode_report.xml",
        "report/paper_format.xml",
        "report/report_invoice.xml",
        "report/medicine_expiry_report.xml",
        "wizard/stock_wizard.xml",
        "wizard/wiz_lock_lot_view.xml",
        "wizard/wiz_medicine_expiry_view.xml",
        "views/menu_item.xml",
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 51,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: