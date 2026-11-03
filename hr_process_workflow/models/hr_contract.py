from odoo import api, fields, models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    hrw_salary_line_ids = fields.One2many('hr.contract.component.line', 'contract_id', string='Salary Components',
                                          copy=True)
    hrw_gross = fields.Monetary('Gross Salary', compute='_compute_hrw_gross')
    hrw_request_id = fields.Many2one('hr.workflow.request', string='Origin Request', copy=False, readonly=True)

    @api.depends('wage', 'hrw_salary_line_ids.amount')
    def _compute_hrw_gross(self):
        components = self.env['hr.salary.component'].search([])
        for contract in self:
            contract.hrw_gross = sum(c._get_contract_amount(contract) for c in components)


class HrContractComponentLine(models.Model):
    _name = 'hr.contract.component.line'
    _description = 'Contract Salary Component'
    _order = 'sequence, id'

    contract_id = fields.Many2one('hr.contract', required=True, ondelete='cascade', index=True)
    component_id = fields.Many2one('hr.salary.component', required=True, ondelete='restrict',
                                   domain=[('contract_field_id', '=', False)])
    sequence = fields.Integer(related='component_id.sequence', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id')
    amount = fields.Monetary()

    _sql_constraints = [('component_uniq', 'unique(contract_id, component_id)',
                         'A component can only appear once per contract.')]
