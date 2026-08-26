# -*- coding: utf-8 -*-
{
    "name": "Patient Barcode in Hospital Management", 
    "description": """
        Barcode For Patient and Appointment creation This module add barcode on patient. hospital management system PB HMS.
    """, 
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    "depends": ["pb_hms", "barcodes"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "report/barcode_report_view.xml",
        "report/paper_format.xml",
        "views/patient_view.xml",
        "wizard/patient_barcode_wizard.xml",
    ],
    'sequence': 2,
    'price': 35,
    'currency': 'USD',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: