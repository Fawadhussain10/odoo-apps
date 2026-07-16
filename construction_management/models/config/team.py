from odoo import fields, models


class ConstructionTeam(models.Model):
    _name = "construction.team"
    _description = "Construction Project Team"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    member_ids = fields.Many2many("res.users", string="Members")
    category_id = fields.Many2one("construction.project.category", string="Category")
    subcategory_id = fields.Many2one("construction.project.subcategory", string="Sub-Category")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
