from odoo import api, fields, models


class ConstructionProjectSubcategory(models.Model):
    _name = "construction.project.subcategory"
    _description = "Construction Project Sub-Category"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(copy=False, readonly=True)
    category_id = fields.Many2one(
        "construction.project.category", string="Category", required=True, ondelete="cascade"
    )
    active = fields.Boolean(default=True)

    _name_category_uniq = models.Constraint(
        "unique(name, category_id)", "Sub-category name must be unique per category."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                name = vals.get("name") or ""
                vals["code"] = "".join(w[0] for w in name.split() if w).upper()[:5]
        return super().create(vals_list)
