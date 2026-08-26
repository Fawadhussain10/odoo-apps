# -*- coding: utf-8 -*-
{ 
    'name': 'Hospital Pharmacy Management',
    'summary': 'Hospital Pharmacy Management system. Manage pharmacy operations of sale, purchase, batch pricing and barcoding',
    'description': """
        Hospital Pharmacy Management system. Manage pharmacy operations of sale, purchase, batch pricing and barcoding Pharmacy Menus. Barcode generation Batch Wise Pricing Product Expiry Product Manufacture Lock Lot pb hms medical healthcare health care.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms', 'pb_pharmacy'],
    'data': [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hms_base_view.xml",
        "views/menu_item.xml",
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 10,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: