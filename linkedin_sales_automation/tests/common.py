from odoo.tests.common import TransactionCase, new_test_user


class LiCommon:
    """Shared fixture: one service, two connected LinkedIn profiles, a manager
    and a sales rep; personas are created per test."""

    @classmethod
    def _setup_li(cls):
        env = cls.env
        cls.manager = new_test_user(env, 'li_manager', groups='base.group_user,linkedin_sales_automation.group_li_manager',
                                    name='Sales Manager')
        cls.rep = new_test_user(env, 'li_rep', groups='base.group_user,linkedin_sales_automation.group_li_user',
                                name='Sales Rep 1')
        cls.tech_user = env.ref('linkedin_sales_automation.user_li_mcp_agent')
        cls.service = env['li.service'].create({
            'name': 'Odoo', 'description': 'Odoo ERP implementation for growing brands.',
            'crm_tag_ids': [(0, 0, {'name': 'ERP'})],
        })
        cls.profile = env['li.profile'].create({
            'name': 'Taha Sohail – Main', 'linkedin_url': 'https://www.linkedin.com/in/taha-test/',
            'owner_id': cls.rep.id, 'account_key': 'taha',
            'my_display_name': 'Taha Sohail', 'account_type': 'free',
        })
        cls.profile2 = env['li.profile'].create({
            'name': 'Sales Rep 1 – Profile', 'linkedin_url': 'https://www.linkedin.com/in/rep1-test/',
            'owner_id': cls.manager.id, 'account_key': 'rep1',
            'my_display_name': 'Rep One', 'account_type': 'premium',
        })
        # the tool tests drive Claude in Chrome profiles; engine tests switch to the engine.
        # Account check far ahead so li_get_work starts with real work (frozen test clocks).
        (cls.profile | cls.profile2).write({'connection_state': 'connected', 'execution_mode': 'chrome',
                                            'chrome_verified_at': '2099-01-01 00:00:00'})
        days = env['li.weekday'].search([])
        cls.mon_fri = days.filtered(lambda d: d.code <= 4)
        cls.sun_thu = days.filtered(lambda d: d.code in (6, 0, 1, 2, 3))
        cls.all_days = days

    @classmethod
    def _make_persona(cls, name, profile=None, tz='UTC', days=None, **vals):
        values = {
            'name': name,
            'linkedin_profile_id': (profile or cls.profile).id,
            'service_id': cls.service.id,
            'job_titles': 'Founder, CEO',
            'icp_description': 'Founders of fashion brands selling on Shopify.',
            'target_timezone': tz,
            'target_working_days': [(6, 0, (days or cls.all_days).ids)],
            'salesperson_id': cls.rep.id,
        }
        values.update(vals)
        return cls.env['li.persona'].create(values)


class LiTransactionCase(TransactionCase, LiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_li()
        cls.tools = cls.env['li.mcp.tools']

    def call(self, _tool, **arguments):
        return self.tools.call_tool(_tool, arguments)

    def work_all(self, **kw):
        """li_get_work for one profile, or for every profile in turn (combined)."""
        if kw.get('linkedin_profile'):
            return self.call('li_get_work', **kw)
        combined = {'items': [], 'reasons': [], 'message': ''}
        for profile in self.env['li.profile'].search([]):
            result = self.call('li_get_work', linkedin_profile=profile.account_key, **kw)
            combined['items'] += result['items']
            combined['reasons'] += result.get('reasons', [])
            combined['message'] = ' '.join(filter(None, [combined['message'], result.get('message', '')]))
        combined['count'] = len(combined['items'])
        return combined
