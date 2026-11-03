{
    'name': 'HRMS Process Workflows',
    'version': '17.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'New hire, resignation, termination and salary/position change '
               'requests with a configurable approval matrix and an HR Director dashboard',
    'description': """
HRMS Process Workflows
======================
* New Employee Registration (Hiring Manager -> HR Operations -> HR Director)
* Employee Resignation / Termination with final settlement
* Salary, position, grade, department and legal entity changes applied on the
  effective date with full history
* Configurable approval matrix per transaction type
* HR Director dashboard
""",
    'author': 'PackBytes',
    'website': 'https://packbytes.com',
    'license': 'LGPL-3',
    'depends': ['hr', 'hr_contract', 'mail', 'analytic'],
    'data': [
        'security/hrw_security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/master_data.xml',
        'data/approval_matrix_data.xml',
        'data/cron_data.xml',
        'wizard/hrw_reject_wizard_views.xml',
        'views/hrw_request_views.xml',
        'views/hrw_config_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_contract_views.xml',
        'views/res_config_settings_views.xml',
        'views/hrw_dashboard_action.xml',
        'views/menus.xml',
        'report/hrw_request_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hr_process_workflow/static/src/dashboard/**/*',
        ],
    },
    'price': 70,
    'currency': "USD",
    'application': True,
    'installable': True,
}
