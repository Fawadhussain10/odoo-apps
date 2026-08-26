# -*- coding: utf-8 -*-
{
    'name': 'Medical Surgery',
    'category': 'Medical',
    'summary': 'Manage Medical Surgery related operations',
    'description': """
        Manage Medical Surgery related operations hospital management system medical PB HMS.
    """,
    'images': ['static/description/banner.png'],
    'version': '19.0.1.0.0',
    'author': 'PackBytes',
    'support': 'sales@packbytes.com',
    'website': 'https://www.packbytes.com',
    'license': 'OPL-1',
    'depends': ['pb_hms'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/digest_data.xml',
        'report/package_report.xml',
        'report/surgery_report.xml',
        'views/surgery_base.xml',
        'views/surgery_template_view.xml',
        'views/surgery_view.xml',
        'views/hms_base_view.xml',
        'views/package_view.xml',
        'views/res_config_settings_views.xml',
        'views/digest_view.xml',
        'views/menu_item.xml',
    ],
    'demo': [
        'demo/hms_demo.xml',
    ],
    'sequence': 1,
    'application': True,
    'price': 36,
    'currency': 'USD',
}
