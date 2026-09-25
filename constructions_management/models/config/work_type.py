from odoo import fields, models

from .cost_code import COST_TYPE_SELECTION


class ConstructionWorkType(models.Model):
    _name = "construction.work.type"
    _description = "Construction Work Type"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char()
    category = fields.Selection(COST_TYPE_SELECTION, required=True, default="material")
    default_cost_code_id = fields.Many2one("construction.cost.code", string="Default Cost Code")
    active = fields.Boolean(default=True)
