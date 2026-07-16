from odoo import api, fields, models

COMPONENT_TYPE_SELECTION = [
    ("material", "Material"),
    ("labour", "Labour"),
    ("equipment", "Equipment"),
    ("subcontract", "Subcontract"),
    ("transport", "Transport"),
    ("testing", "Testing"),
    ("direct_overhead", "Direct Overhead"),
    ("site_overhead", "Site Overhead"),
    ("contingency", "Contingency"),
    ("margin", "Margin"),
]


class ConstructionRateAnalysis(models.Model):
    _name = "construction.rate.analysis"
    _description = "Construction Rate Analysis"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True)
    product_id = fields.Many2one("product.product", string="Product")
    uom_id = fields.Many2one("uom.uom", string="Per UoM")
    boq_line_id = fields.Many2one("construction.boq.line", string="BOQ Line")
    boq_template_line_id = fields.Many2one("construction.boq.template.line", string="BOQ Template Line")
    date_effective = fields.Date(default=fields.Date.context_today)
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    line_ids = fields.One2many("construction.rate.analysis.line", "rate_analysis_id", string="Components")
    total_rate = fields.Monetary(compute="_compute_total_rate", store=True, currency_field="currency_id")
    active = fields.Boolean(default=True)

    @api.depends("line_ids.amount")
    def _compute_total_rate(self):
        for rec in self:
            rec.total_rate = sum(rec.line_ids.mapped("amount"))

    def action_apply_to_boq_line(self):
        self.ensure_one()
        if self.boq_line_id:
            self.boq_line_id.with_context(allow_boq_baseline_write=self.boq_line_id.boq_id.state not in
                                           ("approved", "superseded", "as_built")).rate = self.total_rate
        return True


class ConstructionRateAnalysisLine(models.Model):
    _name = "construction.rate.analysis.line"
    _description = "Construction Rate Analysis Component"
    _order = "sequence, id"

    rate_analysis_id = fields.Many2one("construction.rate.analysis", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    component_type = fields.Selection(COMPONENT_TYPE_SELECTION, required=True, default="material")
    product_id = fields.Many2one("product.product", string="Product / Resource")
    description = fields.Char()
    quantity = fields.Float(default=1.0)
    uom_id = fields.Many2one("uom.uom", string="UoM")
    rate = fields.Float(string="Unit Rate")
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="rate_analysis_id.currency_id", store=True)

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.quantity * rec.rate

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.uom_id = self.product_id.uom_id
            self.rate = self.product_id.standard_price
