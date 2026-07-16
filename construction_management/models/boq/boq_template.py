from odoo import api, fields, models


class ConstructionBoqTemplate(models.Model):
    _name = "construction.boq.template"
    _description = "Construction BOQ Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True, help='E.g. "3.5 Marla House - B Category", "10 Marla House", "1 Kanal House".')
    code = fields.Char(copy=False, readonly=True)
    category_id = fields.Many2one("construction.project.category", string="Project Category")
    subcategory_id = fields.Many2one(
        "construction.project.subcategory", string="Sub-Category",
        domain="[('category_id', '=', category_id)]",
    )
    plot_area = fields.Float(string="Plot Area")
    covered_area = fields.Float(string="Total Covered Area")
    grade = fields.Char(string="Material Grade", help='E.g. "B-Category / Mid-Range".')
    description = fields.Text()
    active = fields.Boolean(default=True)
    line_ids = fields.One2many("construction.boq.template.line", "template_id", string="Lines", copy=True)
    total_amount = fields.Monetary(compute="_compute_total_amount", store=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    use_count = fields.Integer(compute="_compute_use_count")

    @api.depends("line_ids.amount", "line_ids.display_type")
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.filtered(lambda l: not l.display_type).mapped("amount"))

    def _compute_use_count(self):
        counts = self.env["construction.boq"]._read_group(
            [("template_id", "in", self.ids)], ["template_id"], ["__count"]
        )
        mapped = {tmpl.id: count for tmpl, count in counts}
        for rec in self:
            rec.use_count = mapped.get(rec.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = self.env["ir.sequence"].next_by_code("construction.boq.template") or "New"
        return super().create(vals_list)


class ConstructionBoqTemplateLine(models.Model):
    _name = "construction.boq.template.line"
    _description = "Construction BOQ Template Line"
    _inherit = ["construction.boq.line.mixin"]
    _order = "template_id, sequence, id"

    template_id = fields.Many2one("construction.boq.template", required=True, ondelete="cascade")
    stage_template_id = fields.Many2one(
        "construction.wbs.stage.template", string="WBS Stage",
        help="Maps this line to a WBS phase when the template is applied to a project BOQ.",
    )
