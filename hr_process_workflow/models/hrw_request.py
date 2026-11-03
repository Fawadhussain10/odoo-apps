import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import clean_context

from .hrw_approval_step import REQUEST_TYPES, STEP_CATEGORIES

_logger = logging.getLogger(__name__)

STATES = [
    ('draft', 'Draft'),
    ('in_approval', 'In Approval'),
    ('approved', 'Approved'),
    ('done', 'Applied'),
    ('rejected', 'Rejected'),
    ('cancel', 'Cancelled'),
]

TYPE_PREFIX = {
    'new_hire': 'hr.workflow.request.new_hire',
    'resignation': 'hr.workflow.request.resignation',
    'termination': 'hr.workflow.request.termination',
    'change': 'hr.workflow.request.change',
}

ALL_ACCESS_GROUPS = (
    'hr_process_workflow.group_hrw_hr_ops',
    'hr_process_workflow.group_hrw_payroll',
    'hr_process_workflow.group_hrw_gm',
    'hr_process_workflow.group_hrw_ceo',
)


class HrWorkflowRequest(models.Model):
    _name = 'hr.workflow.request'
    _description = 'HR Workflow Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    _check_company_auto = True

    name = fields.Char('Reference', readonly=True, copy=False, default=lambda self: _('New'))
    request_type = fields.Selection(REQUEST_TYPES, string='Transaction Type', required=True,
                                    tracking=True, default=lambda self: self.env.context.get('default_request_type') or 'new_hire')
    state = fields.Selection(STATES, default='draft', required=True, tracking=True, copy=False, index=True)
    company_id = fields.Many2one('res.company', string='Legal Entity', required=True,
                                 default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    requested_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True, copy=False)
    request_date = fields.Date(default=fields.Date.context_today, required=True, copy=False)
    submit_date = fields.Datetime(readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)
    done_date = fields.Datetime('Applied On', readonly=True, copy=False)
    effective_date = fields.Date(tracking=True,
                                 help='Joining date for new hires, last working day for exits, '
                                      'effective date for salary/position changes.')
    reason = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', 'hrw_request_attachment_rel', 'request_id', 'attachment_id',
                                      string='Attachments')
    attachment_count = fields.Integer('Attachments Count', compute='_compute_attachment_count')
    notes = fields.Html()

    # ------------------------------------------------------------------ employee / current values
    employee_id = fields.Many2one('hr.employee', tracking=True, check_company=True, index=True)
    contract_id = fields.Many2one('hr.contract', string='Current Contract', check_company=True)
    employee_code = fields.Char('Employee ID')
    business_unit_id = fields.Many2one('hr.business.unit', string='Business Unit')
    department_id = fields.Many2one('hr.department', string='Department')
    job_id = fields.Many2one('hr.job', string='Job Position')
    job_title = fields.Char('Job Title')
    manager_id = fields.Many2one('hr.employee', string='Reporting Manager')
    grade_id = fields.Many2one('hr.employee.grade', string='Grade')
    cost_center_id = fields.Many2one('account.analytic.account', string='Cost Center')

    # ------------------------------------------------------------------ new / proposed values
    new_employee_name = fields.Char('Employee Name (English)')
    new_employee_name_ar = fields.Char('Employee Name (Arabic)')
    new_company_id = fields.Many2one('res.company', string='New Legal Entity')
    new_business_unit_id = fields.Many2one('hr.business.unit', string='New Business Unit')
    new_department_id = fields.Many2one('hr.department', string='New Department')
    new_job_id = fields.Many2one('hr.job', string='New Job Position')
    new_job_title = fields.Char('New Job Title')
    new_manager_id = fields.Many2one('hr.employee', string='New Reporting Manager')
    new_grade_id = fields.Many2one('hr.employee.grade', string='New Grade')
    new_cost_center_id = fields.Many2one('account.analytic.account', string='New Cost Center')

    # ------------------------------------------------------------------ new hire particulars
    nationality_id = fields.Many2one('res.country', string='Nationality')
    identification_id = fields.Char('Identification No')
    passport_id = fields.Char('Passport No')
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    birthday = fields.Date('Date of Birth')
    work_email = fields.Char()
    mobile_phone = fields.Char('Mobile')
    contract_type_id = fields.Many2one('hr.contract.type', string='Contract Type')
    contract_end_date = fields.Date('Contract End Date')
    bank_id = fields.Many2one('res.bank', string='Bank')
    bank_acc_number = fields.Char('Bank Account / IBAN')
    statutory_line_ids = fields.One2many('hr.statutory.line', 'request_id', string='Statutory Registrations')
    position_approved = fields.Boolean('Position in Approved Manpower Plan')
    docs_validated = fields.Boolean('Documents Validated')
    position_validated = fields.Boolean('Approved Position Validated')
    contract_validated = fields.Boolean('Contract Validated')
    eligibility_validated = fields.Boolean('Eligibility Validated')

    # ------------------------------------------------------------------ exits
    departure_reason_id = fields.Many2one('hr.departure.reason', string='Departure Reason')
    notice_date = fields.Date('Resignation / Notice Date')
    notice_period_days = fields.Integer('Notice Period (days)')
    legal_opinion = fields.Text('Legal Review Notes')
    settlement_line_ids = fields.One2many('hr.workflow.settlement.line', 'request_id', string='Final Settlement')
    settlement_earnings = fields.Monetary(compute='_compute_settlement', store=True)
    settlement_deductions = fields.Monetary(compute='_compute_settlement', store=True)
    settlement_net = fields.Monetary('Net Settlement', compute='_compute_settlement', store=True)

    # ------------------------------------------------------------------ salary
    salary_line_ids = fields.One2many('hr.workflow.salary.line', 'request_id', string='Salary Components')
    old_total = fields.Monetary('Old Gross', compute='_compute_salary_totals', store=True)
    new_total = fields.Monetary('New Gross', compute='_compute_salary_totals', store=True)
    total_difference = fields.Monetary('Difference', compute='_compute_salary_totals', store=True)
    total_difference_pct = fields.Float('Difference %', compute='_compute_salary_totals', store=True)
    cost_impact = fields.Monetary('Monthly Cost Impact', compute='_compute_salary_totals', store=True,
                                  help='New hires add their gross, exits remove their gross, '
                                       'changes add the difference.')
    budget_approved = fields.Boolean('Budget Approved', tracking=True)
    budget_reference = fields.Char('Budget Reference')
    signed_amendment = fields.Binary('Signed Amendment', attachment=True, copy=False)
    signed_amendment_name = fields.Char(copy=False)
    change_summary = fields.Char(compute='_compute_change_summary')

    # ------------------------------------------------------------------ approvals
    round = fields.Integer(default=0, copy=False)
    approval_ids = fields.One2many('hr.workflow.approval', 'request_id', string='Approval History', copy=False)
    current_approval_ids = fields.One2many('hr.workflow.approval', compute='_compute_current_approvals', string='Current Round Approvals')
    current_approval_id = fields.Many2one('hr.workflow.approval', compute='_compute_current', store=True)
    current_step_name = fields.Char('Current Step', compute='_compute_current', store=True)
    current_step_category = fields.Selection(STEP_CATEGORIES, compute='_compute_current', store=True)
    current_approver_ids = fields.Many2many('res.users', 'hrw_request_current_approver_rel', 'request_id', 'user_id',
                                            string='Pending With', compute='_compute_current', store=True)
    current_deadline = fields.Date('Step Deadline', compute='_compute_current', store=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue')
    can_approve = fields.Boolean(compute='_compute_can_approve')
    cycle_days = fields.Float('Cycle Time (days)', compute='_compute_cycle_days', store=True, group_operator='avg')
    progress = fields.Integer(compute='_compute_current_approvals')

    # ================================================================== computes
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    @api.depends('settlement_line_ids.amount', 'settlement_line_ids.line_type')
    def _compute_settlement(self):
        for rec in self:
            earn = sum(rec.settlement_line_ids.filtered(lambda l: l.line_type == 'earning').mapped('amount'))
            ded = sum(rec.settlement_line_ids.filtered(lambda l: l.line_type == 'deduction').mapped('amount'))
            rec.settlement_earnings = earn
            rec.settlement_deductions = ded
            rec.settlement_net = earn - ded

    @api.depends('salary_line_ids.old_amount', 'salary_line_ids.new_amount', 'request_type')
    def _compute_salary_totals(self):
        for rec in self:
            old = sum(rec.salary_line_ids.mapped('old_amount'))
            new = sum(rec.salary_line_ids.mapped('new_amount'))
            rec.old_total = old
            rec.new_total = new
            rec.total_difference = new - old if rec.request_type == 'change' else 0.0
            rec.total_difference_pct = ((new - old) / old * 100.0) if rec.request_type == 'change' and old else 0.0
            if rec.request_type == 'new_hire':
                rec.cost_impact = new
            elif rec.request_type in ('resignation', 'termination'):
                rec.cost_impact = -old
            else:
                rec.cost_impact = new - old

    @api.depends('new_company_id', 'new_department_id', 'new_job_id', 'new_job_title', 'new_manager_id',
                 'new_grade_id', 'new_business_unit_id', 'total_difference', 'request_type')
    def _compute_change_summary(self):
        for rec in self:
            if rec.request_type != 'change':
                rec.change_summary = False
                continue
            parts = [label for label, changed in rec._get_change_flags().items() if changed]
            rec.change_summary = ', '.join(parts) or _('No change')

    def _get_change_flags(self):
        self.ensure_one()
        return {
            _('Salary'): any(l.new_amount != l.old_amount for l in self.salary_line_ids),
            _('Legal Entity'): bool(self.new_company_id and self.new_company_id != self.company_id),
            _('Business Unit'): bool(self.new_business_unit_id and self.new_business_unit_id != self.business_unit_id),
            _('Department'): bool(self.new_department_id and self.new_department_id != self.department_id),
            _('Position'): bool((self.new_job_id and self.new_job_id != self.job_id)
                                or (self.new_job_title and self.new_job_title != self.job_title)),
            _('Manager'): bool(self.new_manager_id and self.new_manager_id != self.manager_id),
            _('Grade'): bool(self.new_grade_id and self.new_grade_id != self.grade_id),
            _('Cost Center'): bool(self.new_cost_center_id and self.new_cost_center_id != self.cost_center_id),
        }

    @api.depends('approval_ids.state', 'round')
    def _compute_current_approvals(self):
        for rec in self:
            lines = rec.approval_ids.filtered(lambda a: a.round == rec.round)
            rec.current_approval_ids = lines
            done = len(lines.filtered(lambda a: a.state == 'approved'))
            rec.progress = int(done * 100 / len(lines)) if lines else 0

    @api.depends('approval_ids.state', 'approval_ids.approver_ids', 'approval_ids.deadline', 'round', 'state')
    def _compute_current(self):
        for rec in self:
            line = rec.approval_ids.filtered(
                lambda a: a.round == rec.round and a.state == 'pending').sorted('sequence')[:1]
            if rec.state != 'in_approval':
                line = self.env['hr.workflow.approval']
            rec.current_approval_id = line
            rec.current_step_name = line.name or False
            rec.current_step_category = line.category or False
            rec.current_approver_ids = [Command.set(line.approver_ids.ids)]
            rec.current_deadline = line.deadline or False

    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = bool(rec.state == 'in_approval' and rec.current_deadline and rec.current_deadline < today)

    def _search_is_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        domain = [('state', '=', 'in_approval'), ('current_deadline', '<', today)]
        positive = (operator == '=' and value) or (operator == '!=' and not value)
        return domain if positive else ['!', '&'] + domain

    @api.depends_context('uid')
    def _compute_can_approve(self):
        is_admin = self.env.user.has_group('hr_process_workflow.group_hrw_admin')
        for rec in self:
            rec.can_approve = rec.state == 'in_approval' and bool(rec.current_approval_id) and (
                self.env.user in rec.current_approver_ids or is_admin)

    @api.depends('submit_date', 'approved_date')
    def _compute_cycle_days(self):
        for rec in self:
            if rec.submit_date and rec.approved_date:
                rec.cycle_days = round((rec.approved_date - rec.submit_date).total_seconds() / 86400.0, 2)
            else:
                rec.cycle_days = 0.0

    # ================================================================== onchanges / defaults
    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.request_type == 'new_hire':
            return
        self._load_employee_snapshot()

    @api.onchange('request_type')
    def _onchange_request_type(self):
        if self.request_type == 'new_hire':
            self.employee_id = False
            if not self.statutory_line_ids:
                self.statutory_line_ids = [Command.create({'type_id': t.id})
                                           for t in self.env['hr.statutory.type'].search([])]
        self._load_salary_lines()

    @api.onchange('new_department_id')
    def _onchange_new_department_id(self):
        dep = self.new_department_id
        if dep and self.request_type == 'new_hire':
            if dep.manager_id and not self.new_manager_id:
                self.new_manager_id = dep.manager_id
            if dep.business_unit_id and not self.new_business_unit_id:
                self.new_business_unit_id = dep.business_unit_id

    @api.onchange('new_job_id')
    def _onchange_new_job_id(self):
        if self.new_job_id and not self.new_job_title:
            self.new_job_title = self.new_job_id.sudo().name

    def _load_employee_snapshot(self):
        emp = self.employee_id.sudo()
        contract = emp.contract_id
        self.contract_id = contract.id
        self.company_id = emp.company_id or self.company_id
        self.employee_code = emp.employee_code
        self.business_unit_id = emp.business_unit_id.id
        self.department_id = emp.department_id.id
        self.job_id = emp.job_id.id
        self.job_title = emp.job_title
        self.manager_id = emp.parent_id.id
        self.grade_id = emp.grade_id.id
        self.cost_center_id = emp.cost_center_id.id
        self._load_salary_lines()

    def _load_salary_lines(self):
        """(Re)build salary lines from the active components and the current contract."""
        contract = self.contract_id.sudo()
        components = self.env['hr.salary.component'].search([])
        existing = {l.component_id.id: l.new_amount for l in self.salary_line_ids}
        commands = [Command.clear()]
        for comp in components:
            old = comp._get_contract_amount(contract) if self.request_type != 'new_hire' else 0.0
            new = existing.get(comp.id) if self.request_type == 'new_hire' else old
            commands.append(Command.create({
                'component_id': comp.id,
                'old_amount': old,
                'new_amount': new or (old if self.request_type != 'new_hire' else 0.0),
            }))
        self.salary_line_ids = commands

    # ================================================================== ORM
    @api.model_create_multi
    def create(self, vals_list):
        is_hr = self.env.user.has_group('hr_process_workflow.group_hrw_hr_ops')
        for vals in vals_list:
            rtype = vals.get('request_type') or self.env.context.get('default_request_type') or 'new_hire'
            if not is_hr and rtype != 'new_hire' and not self.env.su:
                raise AccessError(_('Only HR can initiate resignation, termination and change requests.'))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(TYPE_PREFIX[rtype]) or _('New')
        records = super().create(vals_list)
        for rec in records:
            if rec.request_type != 'new_hire' and rec.employee_id and not rec.salary_line_ids:
                rec._load_employee_snapshot()
            elif rec.request_type == 'new_hire' and not rec.salary_line_ids:
                rec._load_salary_lines()
            rec._link_attachments()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'attachment_ids' in vals:
            self._link_attachments()
        return res

    def _link_attachments(self):
        # only re-home the user's own fresh uploads (many2many_binary creates them with res_id 0);
        # never attachments of other records the user could not read otherwise.
        uid = self.env.uid
        for rec in self:
            fresh = rec.sudo().attachment_ids.filtered(
                lambda a: not a.res_id and (self.env.su or a.create_uid.id == uid))
            fresh.write({'res_model': self._name, 'res_id': rec.id})

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(rec.state not in ('draft', 'cancel') for rec in self):
            raise UserError(_('Only draft or cancelled requests can be deleted.'))

    # ================================================================== helpers
    def _get_line_manager(self):
        self.ensure_one()
        if self.request_type == 'new_hire':
            return self.new_manager_id
        return self.manager_id or self.employee_id.sudo().parent_id

    def _get_department(self):
        self.ensure_one()
        if self.request_type == 'new_hire':
            return self.new_department_id
        return self.department_id or self.employee_id.sudo().department_id

    def _get_display_employee_name(self):
        self.ensure_one()
        return self.employee_id.sudo().name or self.new_employee_name or ''

    def _check_submit_requirements(self):
        self.ensure_one()
        missing = []
        if self.request_type == 'new_hire':
            required = {
                'new_employee_name': _('Employee name (English)'),
                'new_employee_name_ar': _('Employee name (Arabic)'),
                'employee_code': _('Employee ID'),
                'nationality_id': _('Nationality'),
                'new_department_id': _('Department'),
                'new_grade_id': _('Grade'),
                'new_manager_id': _('Reporting manager'),
                'effective_date': _('Joining date'),
                'contract_type_id': _('Contract type'),
                'bank_acc_number': _('Bank account'),
            }
            missing += [label for f, label in required.items() if not self[f]]
            if not (self.new_job_id or self.new_job_title):
                missing.append(_('Job position / title'))
            if not (self.identification_id or self.passport_id):
                missing.append(_('Identification or passport number'))
            if not any(l.new_amount > 0 for l in self.salary_line_ids):
                missing.append(_('Salary components'))
            if self.employee_code and self.env['hr.employee'].sudo().with_context(active_test=False).search_count(
                    [('employee_code', '=', self.employee_code), ('company_id', '=', self.company_id.id)]):
                raise ValidationError(_('Employee ID %s is already used.', self.employee_code))
        else:
            if not self.employee_id:
                missing.append(_('Employee'))
            if not self.effective_date:
                missing.append(_('Last working day') if self.request_type != 'change' else _('Effective date'))
            if not self.reason:
                missing.append(_('Reason'))
            if self.request_type == 'resignation' and not self.notice_date:
                missing.append(_('Resignation date'))
            if self.request_type == 'change' and not any(self._get_change_flags().values()):
                raise ValidationError(_('Nothing changes in this request: set a new salary, position, grade, '
                                        'department, manager, cost center or legal entity.'))
        if not self.attachment_ids:
            missing.append(_('Attachment (approved hiring request / resignation letter / approved form)'))
        if missing:
            raise ValidationError(_('Please provide the following before submitting:\n- %s', '\n- '.join(missing)))

    def _check_step_requirements(self, line):
        self.ensure_one()
        cat = line.category
        if cat == 'hr_validation' and self.request_type == 'new_hire':
            if not (self.docs_validated and self.position_validated and self.contract_validated
                    and self.eligibility_validated):
                raise ValidationError(_('HR Operations must tick all validation checks (documents, approved '
                                        'position, contract and eligibility) before approving.'))
        if cat == 'legal' and not self.legal_opinion:
            raise ValidationError(_('Please write the legal review notes before approving.'))
        if cat == 'finance' and self.request_type == 'change' and self.total_difference > 0 and not self.budget_approved:
            raise ValidationError(_('Finance must confirm the budget approval for a salary increase.'))
        if self.request_type in ('resignation', 'termination') and cat in ('settlement', 'final') \
                and not self.settlement_line_ids:
            raise ValidationError(_('Please compute the final settlement before approving this step.'))

    # ================================================================== chatter helper
    def _hrw_post(self, body, partner_ids=None):
        """Post on the chatter; users without an email address get an internal log note instead
        of the 'configure the sender's email address' error."""
        for rec in self:
            if self.env.user.email and partner_ids:
                rec.message_post(body=body, partner_ids=partner_ids, subtype_xmlid='mail.mt_comment')
            elif self.env.user.email:
                rec.message_post(body=body)
            else:
                rec._message_log(body=body)

    # ================================================================== workflow actions
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft requests can be submitted.'))
            rec._check_submit_requirements()
            if rec.request_type == 'change':
                rec._refresh_old_values()
            steps = self.env['hr.workflow.approval.step'].search([
                ('request_type', '=', rec.request_type),
                '|', ('company_id', '=', False), ('company_id', '=', rec.company_id.id)])
            if not steps:
                raise UserError(_('No approval matrix is configured for %s.',
                                  dict(REQUEST_TYPES)[rec.request_type]))
            new_round = rec.round + 1
            vals = []
            for step in steps:
                approvers = step._resolve_approvers(rec)
                if not approvers:
                    raise UserError(_('No approver found for step "%(step)s". Check the approval matrix, '
                                      'the user groups or the manager/department head.', step=step.name))
                vals.append({
                    'request_id': rec.id, 'round': new_round, 'step_id': step.id, 'name': step.name,
                    'sequence': step.sequence, 'category': step.category, 'sla_days': step.sla_days,
                    'approver_ids': [Command.set(approvers.ids)],
                })
            self.env['hr.workflow.approval'].sudo().create(vals)
            rec.sudo().write({'round': new_round, 'state': 'in_approval', 'submit_date': fields.Datetime.now(),
                              'approved_date': False})
            rec._activate_current_step()
            rec._hrw_post(_('Request submitted for approval.'))
        return True

    def _refresh_old_values(self):
        """Old values must reflect the employee/contract at submission time."""
        self.ensure_one()
        new_amounts = {l.component_id.id: l.new_amount for l in self.salary_line_ids}
        self._load_employee_snapshot()
        for line in self.salary_line_ids:
            if line.component_id.id in new_amounts:
                line.new_amount = new_amounts[line.component_id.id]

    def _activate_current_step(self):
        self.ensure_one()
        line = self.current_approval_id
        if not line:
            return
        today = fields.Date.context_today(self)
        line.sudo().write({'activated_date': fields.Datetime.now(),
                           'deadline': today + timedelta(days=line.sla_days or 0)})
        summary = _('%(step)s: %(ref)s', step=line.name, ref=self.name)
        for user in line.approver_ids:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo', date_deadline=line.deadline,
                summary=summary, note=_('Please review and approve %s.', self._get_display_employee_name()),
                user_id=user.id)

    def _close_step_activities(self, feedback):
        self.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == self.env.ref('mail.mail_activity_data_todo')
            and a.summary and self.name in a.summary).action_feedback(feedback=feedback)

    def action_approve(self):
        for rec in self:
            line = rec.current_approval_id
            if rec.state != 'in_approval' or not line:
                raise UserError(_('There is nothing to approve on %s.', rec.name))
            if not rec.can_approve:
                raise AccessError(_('You are not an approver of the step "%s".', line.name))
            rec._check_step_requirements(line)
            line.sudo().write({'state': 'approved', 'decided_by': self.env.user.id,
                               'decided_date': fields.Datetime.now()})
            rec._close_step_activities(_('Approved by %s', self.env.user.name))
            rec._hrw_post(_('Step "%s" approved.', line.name))
            if rec.current_approval_id:
                rec._activate_current_step()
            else:
                rec.sudo().write({'state': 'approved', 'approved_date': fields.Datetime.now()})
                rec._notify_final_approval()
        return True

    def _notify_final_approval(self):
        self.ensure_one()
        partners = self.requested_by.partner_id
        self._hrw_post(_('Request fully approved.'), partner_ids=partners.ids)
        group = 'hr_process_workflow.group_hrw_payroll' if self.request_type == 'change' \
            else 'hr_process_workflow.group_hrw_hr_ops'
        users = self.env.ref(group).sudo().users.filtered(lambda u: self.company_id in u.company_ids)
        what = _('Create the employee') if self.request_type == 'new_hire' else _('Apply on effective date')
        for user in users:
            self.sudo().activity_schedule('mail.mail_activity_data_todo',
                                          date_deadline=self.effective_date or fields.Date.context_today(self),
                                          summary=_('%(what)s: %(ref)s', what=what, ref=self.name), user_id=user.id)

    def action_open_reject_wizard(self):
        self.ensure_one()
        if not self.can_approve:
            raise AccessError(_('You are not an approver of the current step.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'hr.workflow.reject.wizard', 'view_mode': 'form',
            'target': 'new', 'name': _('Reject Request'),
            'context': {'default_request_id': self.id},
        }

    def _do_reject(self, comment):
        self.ensure_one()
        line = self.current_approval_id
        if not self.can_approve:
            raise AccessError(_('You are not an approver of the current step.'))
        line.sudo().write({'state': 'rejected', 'decided_by': self.env.user.id,
                           'decided_date': fields.Datetime.now(), 'comment': comment})
        self.approval_ids.filtered(lambda a: a.round == self.round and a.state == 'pending').sudo().write(
            {'state': 'skipped'})
        self._close_step_activities(_('Rejected by %s', self.env.user.name))
        self.sudo().write({'state': 'rejected'})
        self._hrw_post(_('Rejected at step "%(step)s": %(c)s', step=line.name, c=comment),
                       partner_ids=self.requested_by.partner_id.ids)

    def action_cancel(self):
        for rec in self:
            if rec.state in ('done',):
                raise UserError(_('An applied request cannot be cancelled.'))
            if not (rec.requested_by == self.env.user or self.env.user.has_group('hr_process_workflow.group_hrw_hr_ops')):
                raise AccessError(_('Only the requester or HR can cancel this request.'))
            rec.approval_ids.filtered(lambda a: a.round == rec.round and a.state == 'pending').sudo().write(
                {'state': 'skipped'})
            rec._close_step_activities(_('Cancelled'))
            rec.sudo().write({'state': 'cancel'})
        return True

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('rejected', 'cancel'):
                raise UserError(_('Only rejected or cancelled requests can be reset to draft.'))
            rec.sudo().write({'state': 'draft'})
        return True

    # ================================================================== settlement
    def action_compute_settlement(self):
        for rec in self:
            if rec.request_type not in ('resignation', 'termination'):
                continue
            if rec.state in ('done', 'cancel', 'rejected'):
                raise UserError(_('The settlement can no longer be changed.'))
            if not rec.effective_date:
                raise UserError(_('Set the last working day first.'))
            rec.settlement_line_ids.filtered('auto').sudo().unlink()
            rec.sudo().write({'settlement_line_ids': [Command.create(v) for v in rec._prepare_settlement_lines()]})
        return True

    def _prepare_settlement_lines(self):
        self.ensure_one()
        company = self.company_id
        month_days = company.hrw_month_days or 30.0
        contract = self.contract_id.sudo() or self.employee_id.sudo().contract_id
        gross = self.old_total
        basic = contract.wage if contract else 0.0
        lwd = self.effective_date
        lines = []
        # unpaid salary of the last month
        days_worked = lwd.day
        if gross:
            lines.append({'name': _('Salary for %(d)s day(s) of %(m)s', d=days_worked, m=lwd.strftime('%B %Y')),
                          'line_type': 'earning', 'amount': round(gross / month_days * days_worked, 2),
                          'auto': True, 'sequence': 1})
        # leave encashment
        emp = self.employee_id.sudo()
        remaining = emp.remaining_leaves if 'remaining_leaves' in emp._fields else 0.0
        if remaining and basic:
            lines.append({'name': _('Leave encashment (%s day(s))', round(remaining, 2)), 'line_type': 'earning',
                          'amount': round(basic / month_days * remaining, 2), 'auto': True, 'sequence': 2})
        # end of service gratuity
        start = emp.first_contract_date or (contract and contract.date_start)
        if start and basic:
            years = (lwd - start).days / 365.0
            if years >= (company.hrw_gratuity_min_years or 0.0):
                days = min(years, 5.0) * company.hrw_gratuity_days_first + max(years - 5.0, 0.0) * company.hrw_gratuity_days_after
                lines.append({'name': _('End of service gratuity (%(y)s years, %(d)s days)', y=round(years, 2), d=round(days, 2)),
                              'line_type': 'earning', 'amount': round(basic / month_days * days, 2),
                              'auto': True, 'sequence': 3})
        # notice period shortfall
        if self.notice_period_days and self.notice_date:
            served = (lwd - self.notice_date).days
            short = self.notice_period_days - served
            if short > 0 and gross:
                lines.append({'name': _('Notice period shortfall (%s day(s))', short), 'line_type': 'deduction',
                              'amount': round(gross / month_days * short, 2), 'auto': True, 'sequence': 10})
        return lines

    # ================================================================== apply
    def action_apply(self):
        self.ensure_one()
        self._check_can_apply()
        if self.request_type == 'new_hire':
            return self.action_create_employee()
        if self.effective_date > fields.Date.context_today(self):
            raise UserError(_('This request takes effect on %s; it will be applied automatically that day.',
                              self.effective_date))
        self._apply()
        return True

    def _check_can_apply(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved requests can be applied.'))
        group = 'hr_process_workflow.group_hrw_payroll' if self.request_type == 'change' \
            else 'hr_process_workflow.group_hrw_hr_ops'
        if not (self.env.su or self.env.user.has_group(group)
                or self.env.user.has_group('hr_process_workflow.group_hrw_admin')):
            raise AccessError(_('You are not allowed to apply this request.'))
        if self.request_type == 'change' and not self.signed_amendment:
            raise UserError(_('Upload the signed contract amendment before applying the change.'))

    def _apply(self):
        self.ensure_one()
        rec = self.sudo().with_context(clean_context(self.env.context), tracking_disable=False)
        if rec.request_type == 'change':
            rec._apply_change()
        elif rec.request_type in ('resignation', 'termination'):
            rec._apply_exit()
        rec.write({'state': 'done', 'done_date': fields.Datetime.now()})
        rec._close_step_activities(_('Applied'))
        rec._hrw_post(_('Request applied to the employee record.'))

    def _apply_change(self):
        emp = self.employee_id
        flags = self._get_change_flags()
        emp_vals = {}
        if self.new_company_id and self.new_company_id != emp.company_id:
            emp_vals['company_id'] = self.new_company_id.id
        if self.new_business_unit_id:
            emp_vals['business_unit_id'] = self.new_business_unit_id.id
        if self.new_department_id:
            emp_vals['department_id'] = self.new_department_id.id
        if self.new_job_id:
            emp_vals['job_id'] = self.new_job_id.id
        if self.new_job_title:
            emp_vals['job_title'] = self.new_job_title
        if self.new_manager_id:
            emp_vals['parent_id'] = self.new_manager_id.id
        if self.new_grade_id:
            emp_vals['grade_id'] = self.new_grade_id.id
        if self.new_cost_center_id:
            emp_vals['cost_center_id'] = self.new_cost_center_id.id
        old_contract = emp.contract_id
        salary_changed = flags[_('Salary')] or flags[_('Legal Entity')]
        if emp_vals:
            emp.write(emp_vals)
        if not old_contract:
            return
        if salary_changed:
            eff = self.effective_date
            if old_contract.date_start >= eff:
                raise UserError(_('The effective date must be after the start of the current contract (%s).',
                                  old_contract.date_start))
            new_contract = old_contract.copy({
                'name': '%s (%s)' % (emp.name, eff.strftime('%d/%m/%Y')),
                'date_start': eff,
                'date_end': old_contract.date_end if old_contract.date_end and old_contract.date_end > eff else False,
                'state': 'draft',
                'company_id': emp.company_id.id,
                'department_id': emp.department_id.id,
                'job_id': emp.job_id.id,
                'hrw_request_id': self.id,
            })
            old_contract.write({'date_end': eff - timedelta(days=1)})
            if old_contract.state == 'open' and old_contract.date_end < fields.Date.context_today(self):
                old_contract.write({'state': 'close'})
            self._write_components(new_contract)
            new_contract.write({'state': 'open'})
            self.contract_id = new_contract
        else:
            old_contract.write({'department_id': emp.department_id.id, 'job_id': emp.job_id.id})
        if self.new_cost_center_id and 'analytic_account_id' in emp.contract_id._fields:
            emp.contract_id.analytic_account_id = self.new_cost_center_id

    def _write_components(self, contract):
        vals = {}
        line_cmds = []
        for line in self.salary_line_ids:
            comp = line.component_id
            field_name = comp.sudo().contract_field_id.name
            if field_name and field_name in contract._fields:
                vals[field_name] = line.new_amount
            else:
                existing = contract.hrw_salary_line_ids.filtered(lambda l: l.component_id == comp)
                if existing:
                    line_cmds.append(Command.update(existing.id, {'amount': line.new_amount}))
                elif line.new_amount:
                    line_cmds.append(Command.create({'component_id': comp.id, 'amount': line.new_amount}))
        if line_cmds:
            vals['hrw_salary_line_ids'] = line_cmds
        if vals:
            contract.write(vals)

    def _apply_exit(self):
        emp = self.employee_id
        eff = self.effective_date
        emp.write({
            'departure_reason_id': self.departure_reason_id.id or emp.departure_reason_id.id,
            'departure_date': eff,
            'departure_description': self.reason and '<p>%s</p>' % self.reason or False,
        })
        for contract in emp.contract_ids.filtered(lambda c: c.state in ('open', 'draft')):
            if contract.date_start > eff:
                contract.write({'state': 'cancel'})
                continue
            if not contract.date_end or contract.date_end > eff:
                contract.write({'date_end': eff})
            if eff < fields.Date.context_today(self) and contract.state == 'open':
                contract.write({'state': 'close'})
        if self.company_id.hrw_archive_on_exit:
            emp.write({'active': False})

    @api.model
    def _cron_apply_due_requests(self):
        today = fields.Date.context_today(self)
        due = self.search([('state', '=', 'approved'), ('request_type', '!=', 'new_hire'),
                           ('effective_date', '<=', today)])
        for rec in due:
            if rec.request_type == 'change' and not rec.signed_amendment:
                continue
            try:
                with self.env.cr.savepoint():
                    rec._apply()
            except Exception as e:  # noqa: BLE001 - keep the cron alive, report on the record
                _logger.exception('HR workflow request %s could not be applied', rec.name)
                rec._message_log(body=_('Automatic application failed: %s', e))

    # ------------------------------------------------------------------ new hire
    def action_create_employee(self):
        self.ensure_one()
        self._check_can_apply()
        if self.employee_id:
            return self.action_open_employee()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'hr.employee', 'view_mode': 'form',
            'views': [(False, 'form')], 'target': 'current', 'name': _('New Employee'),
            'context': {'hrw_new_hire_request_id': self.id},
        }

    def _get_new_employee_defaults(self):
        self.ensure_one()
        vals = {
            'name': self.new_employee_name,
            'name_ar': self.new_employee_name_ar,
            'employee_code': self.employee_code,
            'company_id': self.company_id.id,
            'business_unit_id': self.new_business_unit_id.id,
            'department_id': self.new_department_id.id,
            'job_id': self.new_job_id.id,
            'job_title': self.new_job_title or self.new_job_id.name,
            'parent_id': self.new_manager_id.id,
            'grade_id': self.new_grade_id.id,
            'cost_center_id': self.new_cost_center_id.id,
            'country_id': self.nationality_id.id,
            'identification_id': self.identification_id,
            'passport_id': self.passport_id,
            'gender': self.gender,
            'birthday': self.birthday,
            'work_email': self.work_email,
            'mobile_phone': self.mobile_phone,
        }
        return {k: v for k, v in vals.items() if v}

    def _finalize_new_hire(self, employee):
        """Called once the HR user saved the new employee created from this request."""
        self.ensure_one()
        rec = self.sudo().with_context(clean_context(self.env.context))
        rec = rec.with_context(hrw_new_hire_request_id=False)
        employee = employee.sudo().with_env(rec.env)
        if rec.bank_acc_number and not employee.bank_account_id:
            partner = employee.work_contact_id
            if partner:
                bank = rec.env['res.partner.bank'].create({
                    'acc_number': rec.bank_acc_number, 'bank_id': rec.bank_id.id,
                    'partner_id': partner.id, 'company_id': employee.company_id.id})
                employee.bank_account_id = bank
        rec.statutory_line_ids.write({'employee_id': employee.id})
        contract_vals = {
            'name': _('%(name)s - Contract', name=employee.name),
            'employee_id': employee.id,
            'company_id': employee.company_id.id,
            'date_start': rec.effective_date,
            'date_end': rec.contract_end_date,
            'department_id': employee.department_id.id,
            'job_id': employee.job_id.id,
            'contract_type_id': rec.contract_type_id.id,
            'wage': 0.0,
            'hrw_request_id': rec.id,
        }
        if rec.new_cost_center_id and 'analytic_account_id' in rec.env['hr.contract']._fields:
            contract_vals['analytic_account_id'] = rec.new_cost_center_id.id
        contract = rec.env['hr.contract'].create(contract_vals)
        rec._write_components(contract)
        if rec.effective_date <= fields.Date.context_today(rec):
            contract.state = 'open'
        else:
            contract.kanban_state = 'done'
        rec.write({'employee_id': employee.id, 'contract_id': contract.id,
                   'state': 'done', 'done_date': fields.Datetime.now()})
        rec._close_step_activities(_('Employee created'))
        rec._hrw_post(_('Employee %s and contract created.', employee.name))

    # ------------------------------------------------------------------ smart buttons / misc
    def action_open_employee(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'hr.employee', 'view_mode': 'form',
                'res_id': self.employee_id.id, 'target': 'current'}

    def action_open_contract(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'hr.contract', 'view_mode': 'form',
                'res_id': self.contract_id.id, 'target': 'current'}

    def action_print(self):
        return self.env.ref('hr_process_workflow.action_report_hrw_request').report_action(self)
