from datetime import date, datetime
from odoo.exceptions import ValidationError

from odoo import api, fields, models, _


class OkrForm(models.Model):
    _name = 'okr.form'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "OKR Form"

    okr_no = fields.Char(string='OKR NO', required=True, copy=False, readonly=True,
                         default=lambda self: _('New'))
    doc_date = fields.Date(string='Document Date', default=fields.Date.today)
    year = fields.Char(string='Year', default=lambda self: str(datetime.now().year))
    quarter = fields.Selection([
        ('q1', "Q1"),
        ('q2', "Q2"),
        ('q3', "Q3"),
        ('q4', "Q4"),
    ], string='Quarter', required=True)
    name = fields.Char(string='Title')
    description = fields.Text(string='Description')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('em_r', "Employee Rating"),
        ('team_l_r', "Team Leader Rating"),
        ('hod_r', "HOD Rating"),
        ('hr_r', "HR Rating"),
        ('done', "Done"),
    ], string='State', required=True, default='draft')
    target = fields.Selection([
        ('com', 'Comapny'),
        ('dep', 'Department'),
        ('em', "Employee's"),
    ], required=True, string='Target')
    type = fields.Many2one('okr.type', string='Type')
    ev_on = fields.Char(string='Evaluation on')
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    company = fields.Many2one('res.company', string='Company')
    employee = fields.Many2one('hr.employee', string='Employee')
    department = fields.Many2one('hr.department', string='Department')
    okr_line = fields.One2many('okr.line', 'connecting_field', string='OKR')

    @api.constrains('end_date')
    def _check_end_date(self):
        current_date = fields.Date.context_today(self)
        for record in self:
            if record.end_date < current_date:
                raise ValidationError(
                    "You cannot create a record for that Quarter because the end date has already passed.")

    @api.model
    def create(self, values):
        if values.get('okr_no', _('New')) == _('New'):
            values['okr_no'] = self.env['ir.sequence'].next_by_code('okr.form') or _('New')
        res = super(OkrForm, self).create(values)
        return res

    def action_employee_rating(self):
        self.state = 'em_r'

    def action_tm_leader(self):
        self.state = 'team_l_r'

    def action_hod(self):
        self.state = 'hod_r'

    def action_hr_rating(self):
        self.state = 'hr_r'

    def action_done(self):
        self.state = 'done'

    @api.onchange('quarter')
    def get_time_period(self):
        for rec in self:
            res = self.env['okr.time'].search([('quarter', '=', rec.quarter), ('year', '=', rec.year)])
            rec.start_date = res.start_date
            rec.end_date = res.end_date


class OkrLine(models.Model):
    _name = 'okr.line'

    connecting_field = fields.Many2one('okr.form', string='Connecting Field')
    checkk = fields.Boolean(string='Check')
    title = fields.Char(string='Title')
    owner = fields.Many2one('hr.employee', string='Owner', default=lambda self: self.env.user.employee_id)
    department = fields.Many2one('hr.department', string='Department', related='owner.department_id')
    company = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)
    point = fields.Selection([
        ('one', '1'),
        ('two', '2'),
        ('three', '3'),
        ('four', '4'),
    ], string='Points', required=True, default=False)
    progress = fields.Integer(string='Progress')
    stage = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], string='Stage', required=True, default='draft')
    result = fields.Selection([
        ('zero', ' '),
        ('pas', 'Pass'),
        ('fail', 'Fail'),
    ], string='Result', required=True, default='zero')
    objective = fields.Many2one('okr.objective', string='Objective')
    competencies = fields.Many2one('okr.comp', string='Competencies')
    weight = fields.Float(string='Weight%', compute='get_weightage')
    point1 = fields.Selection([
        ('one', '1'),
        ('two', '2'),
        ('three', '3'),
        ('four', '4'),
    ], string='Points', default=False)
    progress1 = fields.Integer(string='Progress')
    result1 = fields.Selection([
        ('zero', ' '),
        ('pas', 'Pass'),
        ('fail', 'Fail'),
    ], string='Result', required=True, default='zero')
    point2 = fields.Selection([
        ('one', '1'),
        ('two', '2'),
        ('three', '3'),
        ('four', '4'),
    ], string='Points', default=False)
    progress2 = fields.Integer(string='Progress')
    result2 = fields.Selection([
        ('zero', ' '),
        ('pas', 'Pass'),
        ('fail', 'Fail'),
    ], string='Result', required=True, default='zero')
    point3 = fields.Selection([
        ('one', '1'),
        ('two', '2'),
        ('three', '3'),
        ('four', '4'),
    ], string='Points', default=False)
    progress3 = fields.Integer(string='Progress')
    result3 = fields.Selection([
        ('zero', ' '),
        ('pas', 'Pass'),
        ('fail', 'Fail'),
    ], string='Result', required=True, default='zero')

    @api.onchange('point', 'point1', 'point2', 'point3')
    def percentage_get(self):
        for rec in self:
            if rec.point == 'one':
                rec.progress = 25
            if rec.point == 'two':
                rec.progress = 50
            if rec.point == 'three':
                rec.progress = 75
            if rec.point == 'four':
                rec.progress = 100

            if rec.point in ['one', 'two']:
                rec.result = 'fail'
            elif not rec.point:
                rec.result = 'zero'
            else:
                rec.result = 'pas'

            if rec.point1 == 'one':
                rec.progress1 = 25
            if rec.point1 == 'two':
                rec.progress1 = 50
            if rec.point1 == 'three':
                rec.progress1 = 75
            if rec.point1 == 'four':
                rec.progress1 = 100

            if rec.point1 in ['one', 'two']:
                rec.result1 = 'fail'
            elif not rec.point1:
                rec.result1 = 'zero'
            else:
                rec.result1 = 'pas'

            if rec.point2 == 'one':
                rec.progress2 = 25
            if rec.point2 == 'two':
                rec.progress2 = 50
            if rec.point2 == 'three':
                rec.progress2 = 75
            if rec.point2 == 'four':
                rec.progress2 = 100

            if rec.point2 in ['one', 'two']:
                rec.result2 = 'fail'
            elif not rec.point2:
                rec.result2 = 'zero'
            else:
                rec.result2 = 'pas'

            if rec.point3 == 'one':
                rec.progress3 = 25
            if rec.point3 == 'two':
                rec.progress3 = 50
            if rec.point3 == 'three':
                rec.progress3 = 75
            if rec.point3 == 'four':
                rec.progress3 = 100

            if rec.point3 in ['one', 'two']:
                rec.result3 = 'fail'
            elif not rec.point3:
                rec.result3 = 'zero'
            else:
                rec.result3 = 'pas'

    def action_confirm(self):
        self.stage = 'confirm'

    def action_cancel(self):
        self.stage = 'cancel'

    @api.onchange('objective')
    def get_evaluations(self):
        for rec in self:
            if rec.objective:
                rec.point = rec.objective.rate
                rec.progress = rec.objective.percentage
                rec.result = rec.objective.result

    @api.depends('point', 'point1', 'point2', 'point3')
    def get_weightage(self):
        for rec in self:
            total_points = 0
            total_weight = 0

            if rec.point == 'one':
                total_points += 1
                total_weight += 1
            elif rec.point == 'two':
                total_points += 1
                total_weight += 2
            elif rec.point == 'three':
                total_points += 1
                total_weight += 3
            elif rec.point == 'four':
                total_points += 1
                total_weight += 4

            if rec.point1 == 'one':
                total_points += 1
                total_weight += 1
            elif rec.point1 == 'two':
                total_points += 1
                total_weight += 2
            elif rec.point1 == 'three':
                total_points += 1
                total_weight += 3
            elif rec.point1 == 'four':
                total_points += 1
                total_weight += 4

            if rec.point2 == 'one':
                total_points += 1
                total_weight += 1
            elif rec.point2 == 'two':
                total_points += 1
                total_weight += 2
            elif rec.point2 == 'three':
                total_points += 1
                total_weight += 3
            elif rec.point2 == 'four':
                total_points += 1
                total_weight += 4

            if rec.point3 == 'one':
                total_points += 1
                total_weight += 1
            elif rec.point3 == 'two':
                total_points += 1
                total_weight += 2
            elif rec.point3 == 'three':
                total_points += 1
                total_weight += 3
            elif rec.point3 == 'four':
                total_points += 1
                total_weight += 4

            if total_points > 0:
                rec.weight = total_weight / total_points
            else:
                rec.weight = 0

    @api.onchange('checkk')
    def check_quarter(self):
        for rec in self:
            if rec.connecting_field.quarter == 'q1':
                rec.checkk = False
            if rec.connecting_field.quarter == 'q2':
                rec.checkk = False
            if rec.connecting_field.quarter == 'q3':
                rec.checkk = False
            if rec.connecting_field.quarter == 'q4':
                rec.checkk = True