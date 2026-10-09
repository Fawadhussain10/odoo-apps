{
    'name': 'LinkedIn Sales Automation – AI Agents with Claude',
    'version': '18.0.1.0.0',
    'summary': 'AI LinkedIn prospecting for several accounts: Claude writes, Odoo sends within your '
               'limits (built-in LinkedIn engine, or Claude in Chrome on Odoo.sh). Connection, chat, '
               'follow-up and activity agents, posts, warm leads to CRM, dashboard and prospects map',
    'description': """
LinkedIn Sales Automation
=========================
AI-driven LinkedIn prospecting for one or many LinkedIn accounts, run from Odoo
and written by Claude. Warm leads land in Odoo CRM.

* Two ways of running, chosen per LinkedIn account: the built-in engine (Odoo
  installs and runs the open-source LinkedIn engine itself, with "Prepare
  engine" and "Connect LinkedIn" in Odoo: no server configuration) or Claude in
  Chrome (the only mode on Odoo.sh).
* Claude connects through one connector URL to Odoo's own MCP endpoint. No
  Claude API key, no extra Python package in Odoo.
* Personas (audience, service, LinkedIn account, target time zone); Connection
  and Chat Agent per persona, shared Follow-up and Activity Agents.
* Every rule is enforced in Odoo: daily limits, send windows and working days
  in each persona's time zone, delay gaps, stale-text check before each send,
  manual takeover, do-not-contact, pivot to CRM.
* Posts from idea to Claude's draft, approval and scheduled publishing.
* Dashboard with account health, work queue, KPIs, funnel and a world map of
  the prospects.

Customers are responsible for using LinkedIn in line with LinkedIn's terms.
""",
    'category': 'Sales/CRM',
    'author': 'PackBytes',
    'maintainer': 'PackBytes',
    'website': 'https://packbytes.com',
    'support': 'sales@packbytes.com',
    'license': 'OPL-1',
    'price': 780.0,
    'currency': 'EUR',
    'images': ['static/description/banner.png'],
    'depends': ['base', 'mail', 'crm', 'calendar', 'sales_team'],
    'data': [
        'security/li_security.xml',
        'security/ir.model.access.csv',
        'security/li_rules.xml',
        'data/li_data.xml',
        'data/li_user.xml',
        'data/li_cron.xml',
        'views/li_profile_views.xml',
        'views/li_service_views.xml',
        'views/li_persona_views.xml',
        'views/li_prospect_views.xml',
        'views/li_event_views.xml',
        'views/li_followup_agent_views.xml',
        'views/li_activity_agent_views.xml',
        'views/li_template_views.xml',
        'views/li_technical_views.xml',
        'views/li_mcp_token_views.xml',
        'views/li_post_views.xml',
        'views/crm_lead_views.xml',
        'views/res_config_settings_views.xml',
        'views/li_dashboard_views.xml',
        'views/li_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'linkedin_sales_automation/static/src/dashboard/li_dashboard.scss',
            'linkedin_sales_automation/static/src/dashboard/li_map.scss',
            'linkedin_sales_automation/static/src/dashboard/li_world.js',
            'linkedin_sales_automation/static/src/dashboard/li_map.js',
            'linkedin_sales_automation/static/src/dashboard/li_map.xml',
            'linkedin_sales_automation/static/src/dashboard/li_dashboard.js',
            'linkedin_sales_automation/static/src/dashboard/li_dashboard.xml',
            'linkedin_sales_automation/static/src/connect/li_connect.scss',
            'linkedin_sales_automation/static/src/connect/li_connect.js',
            'linkedin_sales_automation/static/src/connect/li_connect.xml',
        ],
        'web.assets_web_dark': [
            'linkedin_sales_automation/static/src/dashboard/li_dashboard.dark.scss',
        ],
    },
    'installable': True,
    'application': True,
}
