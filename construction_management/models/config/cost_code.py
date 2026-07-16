from odoo import api, fields, models
from odoo.exceptions import ValidationError

COST_TYPE_SELECTION = [
    ("material", "Material"),
    ("labour", "Labour"),
    ("subcontract", "Subcontract"),
    ("equipment", "Equipment"),
    ("overhead", "Overhead"),
    ("other", "Other"),
]


class ConstructionCostCode(models.Model):
    _name = "construction.cost.code"
    _description = "Construction Cost Code"
    _order = "code"
    _parent_store = True
    _rec_name = "complete_name"

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    complete_name = fields.Char(compute="_compute_complete_name", store=True, recursive=True)
    parent_id = fields.Many2one("construction.cost.code", string="Parent Cost Code", ondelete="cascade")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("construction.cost.code", "parent_id", string="Child Cost Codes")
    cost_type = fields.Selection(COST_TYPE_SELECTION, required=True, default="material")
    expense_account_id = fields.Many2one("account.account", string="Expense / WIP Account")
    analytic_applicable = fields.Boolean(default=True, string="Analytic Posting Applicable")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("unique(code)", "Cost code must be unique.")

    @api.depends("name", "code", "parent_id.complete_name")
    def _compute_complete_name(self):
        for rec in self:
            if rec.parent_id:
                rec.complete_name = f"{rec.parent_id.complete_name} / [{rec.code}] {rec.name}"
            else:
                rec.complete_name = f"[{rec.code}] {rec.name}" if rec.code else rec.name

    @api.constrains("parent_id")
    def _check_parent_recursion(self):
        if not self._check_recursion():
            raise ValidationError(self.env._("You cannot create a recursive cost code hierarchy."))
