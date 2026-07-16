from odoo import api, fields, models


class ConstructionProjectCategory(models.Model):
    _name = "construction.project.category"
    _description = "Construction Project Category"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(copy=False, readonly=True)
    active = fields.Boolean(default=True)
    stage_ids = fields.Many2many(
        "construction.wbs.stage.template",
        "construction_category_stage_rel",
        "category_id",
        "stage_id",
        string="Default WBS Stages",
    )
    subcategory_ids = fields.One2many(
        "construction.project.subcategory", "category_id", string="Sub-Categories"
    )
    project_count = fields.Integer(compute="_compute_project_count")

    _name_uniq = models.Constraint(
        "unique(name)", "Project category name must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = self._generate_code(vals.get("name") or "")
        return super().create(vals_list)

    @staticmethod
    def _generate_code(name):
        words = [w for w in name.strip().split() if w]
        if not words:
            return ""
        if len(words) == 1:
            return words[0][:3].upper()
        return "".join(w[0] for w in words).upper()

    def _compute_project_count(self):
        counts = self.env["project.project"]._read_group(
            [("construction_category_id", "in", self.ids)],
            ["construction_category_id"],
            ["__count"],
        )
        mapped = {cat.id: count for cat, count in counts}
        for rec in self:
            rec.project_count = mapped.get(rec.id, 0)
