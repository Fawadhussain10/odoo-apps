from odoo import api, fields, models

REQUEST_TYPES = [
    ('new_hire', 'New Hire'),
    ('resignation', 'Resignation'),
    ('termination', 'Termination'),
    ('change', 'Salary / Position Change'),
]

STEP_CATEGORIES = [
    ('review', 'Review & Approve'),
    ('hr_validation', 'HR Validation (documents checklist)'),
    ('legal', 'Legal Review'),
    ('finance', 'Finance Review (budget)'),
    ('settlement', 'Final Settlement'),
    ('final', 'Final Authority'),
]


class HrWorkflowApprovalStep(models.Model):
    _name = 'hr.workflow.approval.step'
    _description = 'HR Workflow Approval Matrix Step'
    _order = 'request_type, sequence, id'

    name = fields.Char('Step', required=True, translate=True)
    request_type = fields.Selection(REQUEST_TYPES, string='Transaction', required=True)
    sequence = fields.Integer(default=10)
    category = fields.Selection(STEP_CATEGORIES, required=True, default='review')
    approver_type = fields.Selection([
        ('groups', 'Users of Groups'),
        ('users', 'Specific Users'),
        ('line_manager', 'Line Manager'),
        ('department_head', 'Department Head'),
    ], required=True, default='groups')
    group_ids = fields.Many2many('res.groups', string='Groups')
    user_ids = fields.Many2many('res.users', string='Users', domain=[('share', '=', False)])
    sla_days = fields.Integer('SLA (days)', default=2, help='Days allowed for this step before it becomes overdue.')
    company_id = fields.Many2one('res.company', string='Legal Entity',
                                 help='Leave empty to apply to all legal entities.')
    active = fields.Boolean(default=True)

    def _resolve_approvers(self, request):
        """Return the res.users allowed to approve this step for ``request``."""
        self.ensure_one()
        users = self.env['res.users']
        company = request.company_id
        if self.approver_type == 'groups':
            users = self.group_ids.sudo().users
        elif self.approver_type == 'users':
            users = self.user_ids
        elif self.approver_type == 'line_manager':
            users = request._get_line_manager().user_id
        elif self.approver_type == 'department_head':
            users = request._get_department().manager_id.user_id or request._get_line_manager().user_id
        users = users.filtered(lambda u: u.active and not u.share)
        if self.approver_type in ('groups', 'users') and company:
            users = users.filtered(lambda u: company in u.company_ids)
        return users
