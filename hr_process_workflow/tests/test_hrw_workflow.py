import base64
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install', 'hrw')
class TestHrWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_create_nolog=True,
                                       mail_notrack=True, no_reset_password=True))
        cls.company = cls.env.company

        def user(login, groups):
            return cls.env['res.users'].create({
                'name': login.title(), 'login': 'hrw_%s' % login, 'email': '%s@hrw.test' % login,
                'company_id': cls.company.id, 'company_ids': [Command.set([cls.company.id])],
                'groups_id': [Command.set([cls.env.ref(g).id for g in groups])],
            })

        g = 'hr_process_workflow.group_hrw_'
        cls.u_hiring = user('hiring', [g + 'requester'])
        cls.u_hrops = user('hrops', [g + 'hr_ops'])
        cls.u_director = user('director', [g + 'hr_director'])
        cls.u_legal = user('legal', [g + 'legal'])
        cls.u_finance = user('finance', [g + 'finance'])
        cls.u_gfm = user('gfm', [g + 'group_finance'])
        cls.u_gm = user('gm', [g + 'gm'])
        cls.u_ceo = user('ceo', [g + 'ceo'])
        cls.u_payroll = user('payroll', [g + 'payroll'])
        cls.u_head = user('head', [g + 'requester'])

        cls.head_emp = cls.env['hr.employee'].create({'name': 'Dept Head', 'user_id': cls.u_head.id,
                                                      'company_id': cls.company.id})
        cls.bu = cls.env['hr.business.unit'].create({'name': 'Retail'})
        cls.dept = cls.env['hr.department'].create({'name': 'HRW Sales', 'manager_id': cls.head_emp.id,
                                                    'business_unit_id': cls.bu.id, 'company_id': cls.company.id})
        cls.dept2 = cls.env['hr.department'].create({'name': 'HRW Ops', 'company_id': cls.company.id})
        cls.grade1 = cls.env['hr.employee.grade'].create({'name': 'G5'})
        cls.grade2 = cls.env['hr.employee.grade'].create({'name': 'G6'})
        cls.job = cls.env['hr.job'].create({'name': 'Sales Executive'})
        cls.housing = cls.env.ref('hr_process_workflow.component_housing')
        cls.basic = cls.env.ref('hr_process_workflow.component_basic')

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Existing Emp', 'company_id': cls.company.id, 'department_id': cls.dept.id,
            'parent_id': cls.head_emp.id, 'job_id': cls.job.id, 'grade_id': cls.grade1.id,
            'employee_code': 'E-100',
        })
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Existing contract', 'employee_id': cls.employee.id, 'wage': 5000.0,
            'date_start': date.today() - timedelta(days=800), 'state': 'open', 'company_id': cls.company.id,
            'hrw_salary_line_ids': [Command.create({'component_id': cls.housing.id, 'amount': 1500.0})],
        })

    def _att(self, user):
        return self.env['ir.attachment'].with_user(user).create({
            'name': 'form.pdf', 'datas': base64.b64encode(b'%PDF-1.4'),
            'res_model': 'hr.workflow.request', 'res_id': 0})

    def _approve_all(self, req):
        users = {
            'hr_ops': self.u_hrops, 'hr_director': self.u_director, 'legal': self.u_legal,
            'finance': self.u_finance, 'group_finance': self.u_gfm, 'gm': self.u_gm, 'ceo': self.u_ceo,
        }
        guard = 0
        while req.state == 'in_approval':
            guard += 1
            self.assertLess(guard, 10)
            approver = req.current_approver_ids[:1]
            self.assertTrue(approver, 'step %s has no approver' % req.current_step_name)
            req.with_user(approver).action_approve()
        return users

    # ------------------------------------------------------------------ new hire
    def test_new_hire_flow(self):
        Req = self.env['hr.workflow.request'].with_user(self.u_hiring)
        with Form(Req.with_context(default_request_type='new_hire')) as f:
            f.new_employee_name = 'Ali Khan'
            f.new_employee_name_ar = 'علي خان'
            f.employee_code = 'E-200'
            f.nationality_id = self.env.ref('base.pk')
            f.identification_id = '35202-1234567-1'
            f.new_department_id = self.dept
            f.new_job_id = self.job
            f.new_grade_id = self.grade1
            f.effective_date = date.today()
            f.contract_type_id = self.env['hr.contract.type'].search([], limit=1)
            f.bank_acc_number = 'PK00TEST0000001'
            with f.salary_line_ids.edit(0) as line:
                line.new_amount = 4000
        req = f.save()
        self.assertEqual(req.new_manager_id, self.head_emp, 'manager defaulted from department')
        self.assertTrue(req.name.startswith('NH/'))
        self.assertTrue(req.statutory_line_ids)
        with self.assertRaises(ValidationError):  # missing attachment
            req.action_submit()
        req.attachment_ids = [Command.link(self._att(self.u_hiring).id)]
        self.assertEqual(req.attachment_ids.res_id, req.id)
        req.action_submit()
        self.assertEqual(req.state, 'in_approval')
        self.assertEqual(req.current_step_category, 'hr_validation')
        self.assertIn(self.u_hrops, req.current_approver_ids)
        with self.assertRaises(AccessError):
            req.with_user(self.u_hiring).action_approve()
        with self.assertRaises(ValidationError):  # checklist not ticked
            req.with_user(self.u_hrops).action_approve()
        req.with_user(self.u_hrops).write({'docs_validated': True, 'position_validated': True,
                                           'contract_validated': True, 'eligibility_validated': True})
        self._approve_all(req)
        self.assertEqual(req.state, 'approved')
        self.assertGreaterEqual(req.cycle_days, 0)
        action = req.with_user(self.u_hrops).action_create_employee()
        ctx = action['context']
        with Form(self.env['hr.employee'].with_user(self.u_hrops).with_context(**ctx)) as ef:
            self.assertEqual(ef.name, 'Ali Khan')
            if 'religion' in self.env['hr.employee']._fields:
                ef.religion = self.env['hr.employee']._fields['religion'].selection[0][0]
        emp = ef.save()
        self.assertEqual(req.state, 'done')
        self.assertEqual(req.employee_id, emp)
        self.assertEqual(emp.employee_code, 'E-200')
        self.assertEqual(emp.parent_id, self.head_emp)
        self.assertEqual(emp.bank_account_id.acc_number, 'PK00TEST0000001')
        self.assertEqual(emp.statutory_line_ids, req.statutory_line_ids)
        self.assertEqual(req.sudo().contract_id.wage, 4000)
        self.assertEqual(req.sudo().contract_id.state, 'open')
        self.assertEqual(req.cost_impact, 4000)
        self.assertFalse(emp.sudo().work_contact_id.parent_id, 'context defaults must not leak into partners')

    # ------------------------------------------------------------------ salary change
    def test_salary_change_flow(self):
        Req = self.env['hr.workflow.request'].with_user(self.u_hrops)
        with Form(Req.with_context(default_request_type='change')) as f:
            f.employee_id = self.employee
            self.assertEqual(f.department_id, self.dept)
            f.new_grade_id = self.grade2
            f.new_department_id = self.dept2
            f.effective_date = date.today()
            f.reason = 'Promotion'
            for i in range(len(f.salary_line_ids)):
                with f.salary_line_ids.edit(i) as line:
                    if line.component_id == self.basic:
                        self.assertEqual(line.old_amount, 5000)
                        line.new_amount = 6000
                    elif line.component_id == self.housing:
                        self.assertEqual(line.old_amount, 1500)
                        line.new_amount = 2000
        req = f.save()
        req.attachment_ids = [Command.link(self._att(self.u_hrops).id)]
        self.assertEqual(req.total_difference, 1500)
        self.assertAlmostEqual(req.total_difference_pct, 23.08, places=2)
        req.action_submit()
        req.with_user(self.u_director).action_approve()
        self.assertEqual(req.current_step_category, 'finance')
        with self.assertRaises(ValidationError):  # budget not confirmed
            req.with_user(self.u_finance).action_approve()
        req.with_user(self.u_finance).budget_approved = True
        self._approve_all(req)
        self.assertEqual(req.state, 'approved')
        with self.assertRaises(UserError):  # signed amendment missing
            req.with_user(self.u_payroll).action_apply()
        req.signed_amendment = base64.b64encode(b'%PDF-1.4')
        req.with_user(self.u_payroll).action_apply()
        self.assertEqual(req.state, 'done')
        new_contract = self.employee.contract_id
        self.assertNotEqual(new_contract, self.contract, 'history kept: a new contract version is created')
        self.assertEqual(new_contract.wage, 6000)
        self.assertEqual(new_contract.hrw_salary_line_ids.amount, 2000)
        self.assertEqual(self.contract.date_end, date.today() - timedelta(days=1))
        self.assertEqual(self.employee.grade_id, self.grade2)
        self.assertEqual(self.employee.department_id, self.dept2)
        for user in (self.u_director, self.u_finance):
            pdf, _fmt = self.env['ir.actions.report'].with_user(user)._render_qweb_pdf(
                'hr_process_workflow.action_report_hrw_request', req.ids)
            self.assertTrue(pdf)

    def test_change_requires_a_change(self):
        req = self.env['hr.workflow.request'].with_user(self.u_hrops).create({
            'request_type': 'change', 'employee_id': self.employee.id, 'effective_date': date.today(),
            'reason': 'x', 'attachment_ids': [Command.link(self._att(self.u_hrops).id)]})
        self.assertEqual(req.old_total, 6500)
        with self.assertRaises(ValidationError):
            req.action_submit()

    # ------------------------------------------------------------------ resignation
    def test_resignation_flow_and_reject_resubmit(self):
        req = self.env['hr.workflow.request'].with_user(self.u_hrops).create({
            'request_type': 'resignation', 'employee_id': self.employee.id,
            'effective_date': date.today() - timedelta(days=1), 'notice_date': date.today() - timedelta(days=20),
            'notice_period_days': 30, 'reason': 'Personal', 'attachment_ids': [Command.link(self._att(self.u_hrops).id)]})
        req.action_submit()
        self.assertEqual(req.current_approver_ids, self.u_head, 'department head approves first')
        # reject then resubmit: history kept in previous round
        self.env['hr.workflow.reject.wizard'].with_user(self.u_head).create(
            {'request_id': req.id, 'comment': 'Talk first'}).action_reject()
        self.assertEqual(req.state, 'rejected')
        req.action_reset_draft()
        req.action_submit()
        self.assertEqual(req.round, 2)
        self.assertEqual(len(req.approval_ids.filtered(lambda a: a.round == 1 and a.state == 'rejected')), 1)
        req.with_user(self.u_head).action_approve()
        req.with_user(self.u_director).action_approve()
        self.assertEqual(req.current_step_category, 'settlement')
        with self.assertRaises(ValidationError):
            req.with_user(self.u_finance).action_approve()
        req.with_user(self.u_finance).action_compute_settlement()
        names = ' '.join(req.settlement_line_ids.mapped('name'))
        self.assertIn('gratuity', names)
        self.assertIn('Notice period shortfall', names)
        self.assertTrue(req.settlement_net)
        self._approve_all(req)
        self.assertEqual(req.state, 'approved')
        # cron applies it because the last working day is in the past
        self.env['hr.workflow.request']._cron_apply_due_requests()
        self.assertEqual(req.state, 'done')
        self.assertEqual(self.employee.departure_date, req.effective_date)
        self.assertEqual(self.contract.date_end, req.effective_date)
        self.assertEqual(self.contract.state, 'close')
        self.env.ref('hr_process_workflow.action_report_hrw_request')._render_qweb_html(
            'hr_process_workflow.report_hrw_request', req.ids)

    # ------------------------------------------------------------------ termination
    def test_termination_legal_and_future_date(self):
        req = self.env['hr.workflow.request'].with_user(self.u_hrops).create({
            'request_type': 'termination', 'employee_id': self.employee.id,
            'effective_date': date.today() + timedelta(days=10), 'reason': 'Misconduct',
            'attachment_ids': [Command.link(self._att(self.u_hrops).id)]})
        req.action_submit()
        req.with_user(self.u_director).action_approve()
        self.assertEqual(req.current_step_category, 'legal')
        legal = self.env['hr.workflow.request'].search([('current_step_category', '=', 'legal'), ('id', '=', req.id)])
        self.assertEqual(legal, req)
        with self.assertRaises(ValidationError):
            req.with_user(self.u_legal).action_approve()
        req.with_user(self.u_legal).legal_opinion = 'Process followed'
        req.with_user(self.u_legal).action_approve()
        req.with_user(self.u_finance).action_compute_settlement()
        self._approve_all(req)
        self.assertEqual(req.state, 'approved')
        with self.assertRaises(UserError):  # effective date in the future
            req.with_user(self.u_hrops).action_apply()
        self.env['hr.workflow.request']._cron_apply_due_requests()
        self.assertEqual(req.state, 'approved')

    # ------------------------------------------------------------------ visibility, overdue, dashboard
    def test_visibility_overdue_dashboard(self):
        req = self.env['hr.workflow.request'].with_user(self.u_hrops).create({
            'request_type': 'resignation', 'employee_id': self.employee.id, 'effective_date': date.today() + timedelta(days=5),
            'notice_date': date.today(), 'reason': 'x', 'attachment_ids': [Command.link(self._att(self.u_hrops).id)]})
        req.action_submit()
        Req = self.env['hr.workflow.request']
        self.assertFalse(Req.with_user(self.u_hiring).search([('id', '=', req.id)]), 'outsider cannot see it')
        self.assertTrue(Req.with_user(self.u_head).search([('id', '=', req.id)]), 'approver can see it')
        req.sudo().approval_ids.filtered(lambda a: a.state == 'pending')[:1].deadline = date.today() - timedelta(days=2)
        self.assertTrue(req.is_overdue)
        self.assertIn(req, Req.search([('is_overdue', '=', True)]))
        data = Req.with_user(self.u_director).get_hrw_dashboard_data({})
        kpis = {k['key']: k['value'] for k in data['kpis']}
        self.assertGreaterEqual(kpis['overdue'], 1)
        self.assertGreaterEqual(kpis['upcoming'], 1)
        self.assertTrue(any(a['id'] == self.u_head.id and a['overdue'] for a in data['approvers']))
        filtered = Req.with_user(self.u_director).get_hrw_dashboard_data(
            {'department_id': self.dept2.id, 'request_type': 'termination'})
        self.assertEqual({k['key']: k['value'] for k in filtered['kpis']}['overdue'], 0)
        self.assertTrue(Req.with_user(self.u_hiring).create({'request_type': 'new_hire'}))
        with self.assertRaises(AccessError):
            Req.with_user(self.u_hiring).create({'request_type': 'termination', 'employee_id': self.employee.id})
