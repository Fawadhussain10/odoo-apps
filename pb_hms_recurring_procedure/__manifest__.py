# -*- coding: utf-8 -*-
{
    'name': 'Recurring Procedure (Hospital Management System)',
    'summary': 'manage Patients Recurring Procedure (Hospital Management System)',
    'description': """
        Recurring Procedure (Hospital Management System).
    """,
    'images': ['static/description/banner.png'],
    'category': 'Medical',
    'version': '19.0.1.0.0',
    'author': 'PackBytes',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/data.xml',
        'views/procedure_view.xml'
    ],
    'assets': {
        'web.assets_backend': [
            'pb_hms_recurring_procedure/static/src/scss/recurrence.scss',
        ],
    },
    'installable': True,
    'application': True,
    'sequence': 3,
    'price': 60,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: