from odoo import _, api, fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    business_unit_id = fields.Many2one('hr.business.unit', string='Business Unit')


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_code = fields.Char('Employee ID', groups='hr.group_hr_user', copy=False, tracking=True)
    name_ar = fields.Char('Name (Arabic)')
    business_unit_id = fields.Many2one('hr.business.unit', string='Business Unit', tracking=True)
    grade_id = fields.Many2one('hr.employee.grade', string='Grade', groups='hr.group_hr_user', tracking=True)
    cost_center_id = fields.Many2one('account.analytic.account', string='Cost Center', groups='hr.group_hr_user')
    statutory_line_ids = fields.One2many('hr.statutory.line', 'employee_id', string='Statutory Registrations',
                                         groups='hr.group_hr_user')
    hrw_request_ids = fields.One2many('hr.workflow.request', 'employee_id', string='HR Requests',
                                      groups='hr.group_hr_user')
    hrw_request_count = fields.Integer(compute='_compute_hrw_request_count', groups='hr.group_hr_user')

    _sql_constraints = [
        ('employee_code_company_uniq', 'unique(employee_code, company_id)',
         'The Employee ID must be unique per legal entity.'),
    ]

    def _compute_hrw_request_count(self):
        data = self.env['hr.workflow.request'].sudo()._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {emp.id: c for emp, c in data}
        for emp in self:
            emp.hrw_request_count = counts.get(emp.id, 0)

    @api.onchange('department_id')
    def _onchange_department_business_unit(self):
        if self.department_id.business_unit_id and not self.business_unit_id:
            self.business_unit_id = self.department_id.business_unit_id

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get('hrw_new_hire_request_id')
        if request_id:
            request = self.env['hr.workflow.request'].browse(request_id).exists()
            if request and request.state == 'approved' and not request.employee_id:
                res.update({k: v for k, v in request._get_new_employee_defaults().items() if k in fields_list})
        return res

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        request_id = self.env.context.get('hrw_new_hire_request_id')
        if request_id and len(employees) == 1:
            request = self.env['hr.workflow.request'].sudo().browse(request_id).exists()
            if request and request.request_type == 'new_hire' and request.state == 'approved' \
                    and not request.employee_id:
                request._finalize_new_hire(employees)
        return employees

    def action_open_hrw_requests(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hr_process_workflow.action_hrw_request_all')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id, 'default_request_type': 'change'}
        return action


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # fields of hr.employee without groups must exist on the public model too,
    # otherwise non-HR approvers get "not available on the public employee profile".
    name_ar = fields.Char('Name (Arabic)', readonly=True)
    business_unit_id = fields.Many2one('hr.business.unit', string='Business Unit', readonly=True)
