from odoo import api, fields, models

from .hrw_approval_step import STEP_CATEGORIES


class HrWorkflowApproval(models.Model):
    _name = 'hr.workflow.approval'
    _description = 'HR Workflow Approval Line'
    _order = 'round desc, sequence, id'

    request_id = fields.Many2one('hr.workflow.request', required=True, ondelete='cascade', index=True)
    round = fields.Integer(default=1)
    step_id = fields.Many2one('hr.workflow.approval.step', string='Matrix Step', ondelete='set null')
    name = fields.Char('Step', required=True)
    sequence = fields.Integer()
    category = fields.Selection(STEP_CATEGORIES)
    approver_ids = fields.Many2many('res.users', 'hrw_approval_user_rel', 'approval_id', 'user_id', string='Approvers')
    state = fields.Selection([('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'),
                              ('skipped', 'Not Reached')], default='pending', required=True, index=True)
    sla_days = fields.Integer('SLA (days)')
    activated_date = fields.Datetime('Received On')
    deadline = fields.Date()
    decided_by = fields.Many2one('res.users')
    decided_date = fields.Datetime('Decided On')
    comment = fields.Text()
    response_hours = fields.Float(compute='_compute_response_hours', store=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True)

    @api.depends('activated_date', 'decided_date')
    def _compute_response_hours(self):
        for line in self:
            if line.activated_date and line.decided_date:
                line.response_hours = round((line.decided_date - line.activated_date).total_seconds() / 3600.0, 2)
            else:
                line.response_hours = 0.0


class HrWorkflowSalaryLine(models.Model):
    _name = 'hr.workflow.salary.line'
    _description = 'HR Workflow Salary Component Line'
    _order = 'sequence, id'

    request_id = fields.Many2one('hr.workflow.request', required=True, ondelete='cascade', index=True)
    component_id = fields.Many2one('hr.salary.component', required=True, ondelete='restrict')
    sequence = fields.Integer(related='component_id.sequence', store=True)
    currency_id = fields.Many2one(related='request_id.currency_id')
    old_amount = fields.Monetary('Old Amount')
    new_amount = fields.Monetary('New Amount')
    difference = fields.Monetary(compute='_compute_difference', store=True)
    difference_pct = fields.Float('Difference %', compute='_compute_difference', store=True)

    @api.depends('old_amount', 'new_amount')
    def _compute_difference(self):
        for line in self:
            line.difference = line.new_amount - line.old_amount
            line.difference_pct = (line.difference / line.old_amount * 100.0) if line.old_amount else 0.0


class HrWorkflowSettlementLine(models.Model):
    _name = 'hr.workflow.settlement.line'
    _description = 'Final Settlement Line'
    _order = 'sequence, id'

    request_id = fields.Many2one('hr.workflow.request', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=5)
    name = fields.Char('Description', required=True)
    line_type = fields.Selection([('earning', 'Earning'), ('deduction', 'Deduction')], required=True,
                                 default='earning')
    currency_id = fields.Many2one(related='request_id.currency_id')
    amount = fields.Monetary(required=True)
    auto = fields.Boolean('Computed', readonly=True,
                          help='Computed lines are replaced when the settlement is recomputed.')
    note = fields.Char()


class HrStatutoryLine(models.Model):
    _name = 'hr.statutory.line'
    _description = 'Statutory Registration'
    _order = 'type_sequence, id'

    request_id = fields.Many2one('hr.workflow.request', ondelete='set null', index=True)
    employee_id = fields.Many2one('hr.employee', ondelete='cascade', index=True)
    type_id = fields.Many2one('hr.statutory.type', string='Registration', required=True)
    type_sequence = fields.Integer(related='type_id.sequence', store=True)
    reference = fields.Char()
    status = fields.Selection([('pending', 'Pending'), ('in_progress', 'In Progress'),
                               ('registered', 'Registered'), ('exempt', 'Exempt / N.A.'),
                               ('expired', 'Expired')], default='pending', required=True)
    date = fields.Date('Registration Date')
    expiry_date = fields.Date()
