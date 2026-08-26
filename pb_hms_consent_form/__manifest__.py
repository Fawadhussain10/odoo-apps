# -*- coding: utf-8 -*-
{
    'name': 'Electronic Consent Forms for Hospitals',
    'summary': """Manage Electronic Consent Forms for Patiens.""",
    'description': """
        Manage Digital Signed Consent Forms for Patiens. Electronic Consent Forms for Hospital and patient.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'category': 'Medical',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ["pb_hms", "pb_consent_form"],
    'data' : [
        'security/ir.model.access.csv',
        'views/consent_form_view.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 1,
    'price': 26,
    'currency': 'USD',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: