from odoo import api, fields, models


class HrBusinessUnit(models.Model):
    _name = 'hr.business.unit'
    _description = 'Business Unit'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    company_id = fields.Many2one('res.company', string='Legal Entity', default=lambda self: self.env.company)
    manager_id = fields.Many2one('hr.employee', string='Head of Business Unit')
    active = fields.Boolean(default=True)


class HrEmployeeGrade(models.Model):
    _name = 'hr.employee.grade'
    _description = 'Employee Grade'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    min_salary = fields.Monetary(string='Minimum Salary', currency_field='currency_id')
    max_salary = fields.Monetary(string='Maximum Salary', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    active = fields.Boolean(default=True)


class HrStatutoryType(models.Model):
    _name = 'hr.statutory.type'
    _description = 'Statutory Registration Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class HrSalaryComponent(models.Model):
    _name = 'hr.salary.component'
    _description = 'Salary Component'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    contract_field_id = fields.Many2one(
        'ir.model.fields', string='Contract Field', ondelete='set null',
        domain="[('model', '=', 'hr.contract'), ('ttype', 'in', ('float', 'monetary')), ('store', '=', True)]",
        help='When set, the component is read from / written to this contract field '
             '(e.g. Wage). Otherwise it is kept in the contract salary component lines.')
    active = fields.Boolean(default=True)

    _sql_constraints = [('code_uniq', 'unique(code)', 'The component code must be unique.')]

    def _get_contract_amount(self, contract):
        self.ensure_one()
        if not contract:
            return 0.0
        field_name = self.sudo().contract_field_id.name
        if field_name and field_name in contract._fields:
            return contract[field_name] or 0.0
        line = contract.hrw_salary_line_ids.filtered(lambda l: l.component_id == self)
        return sum(line.mapped('amount'))
