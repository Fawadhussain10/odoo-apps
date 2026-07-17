from odoo import _, api, fields, models
from odoo.exceptions import UserError

VARIATION_STATE_SELECTION = [
    ("draft", "Change Request"),
    ("technical_review", "Technical Review"),
    ("commercial_eval", "Commercial Evaluation"),
    ("internal_approval", "Internal Approval"),
    ("customer_approval", "Customer / Consultant Approval"),
    ("approved", "Approved Variation"),
    ("rejected", "Rejected"),
]

RESPONSIBILITY_SELECTION = [
    ("client", "Client"),
    ("contractor", "Contractor"),
    ("design", "Design Change"),
    ("site_condition", "Site Condition"),
    ("other", "Other"),
]

_STATE_FLOW = ["draft", "technical_review", "commercial_eval", "internal_approval", "customer_approval", "approved"]


class ConstructionVariation(models.Model):
    _name = "construction.variation"
    _description = "Construction Variation / Change Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, id desc"

    name = fields.Char(required=True, default="New Variation", tracking=True)
    code = fields.Char(copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    boq_id = fields.Many2one(
        "construction.boq", string="BOQ", required=True,
        domain="[('project_id', '=', project_id), ('is_baseline', '=', True)]",
    )
    currency_id = fields.Many2one(related="boq_id.currency_id", store=True)
    state = fields.Selection(VARIATION_STATE_SELECTION, default="draft", tracking=True, copy=False)
    reason = fields.Text()
    responsibility = fields.Selection(RESPONSIBILITY_SELECTION, default="client")
    requested_by = fields.Many2one("res.users", default=lambda self: self.env.user)
    date_raised = fields.Date(default=fields.Date.context_today)

    line_ids = fields.One2many("construction.variation.line", "variation_id", string="Lines")
    total_cost_effect = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    total_revenue_effect = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    total_schedule_effect_days = fields.Integer(compute="_compute_totals", store=True)

    @api.depends("line_ids.cost_effect", "line_ids.revenue_effect", "line_ids.schedule_effect_days")
    def _compute_totals(self):
        for rec in self:
            rec.total_cost_effect = sum(rec.line_ids.mapped("cost_effect"))
            rec.total_revenue_effect = sum(rec.line_ids.mapped("revenue_effect"))
            rec.total_schedule_effect_days = sum(rec.line_ids.mapped("schedule_effect_days"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = self.env["ir.sequence"].next_by_code("construction.variation") or "New"
        return super().create(vals_list)

    def _advance(self, target):
        for rec in self:
            idx = _STATE_FLOW.index(rec.state) if rec.state in _STATE_FLOW else -1
            target_idx = _STATE_FLOW.index(target)
            if target_idx != idx + 1:
                raise UserError(_("Cannot move variation '%(name)s' from '%(state)s' to '%(target)s'.",
                                   name=rec.name, state=rec.state, target=target))
        self.write({"state": target})

    def action_submit_technical_review(self):
        self._advance("technical_review")

    def action_submit_commercial_eval(self):
        self._advance("commercial_eval")

    def action_submit_internal_approval(self):
        self._advance("internal_approval")

    def action_submit_customer_approval(self):
        self._advance("customer_approval")

    def action_approve(self):
        self._advance("approved")

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})


class ConstructionVariationLine(models.Model):
    _name = "construction.variation.line"
    _description = "Construction Variation Line"
    _order = "sequence, id"

    variation_id = fields.Many2one("construction.variation", required=True, ondelete="cascade")
    state = fields.Selection(related="variation_id.state", store=True)
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('boq_id', '=', parent.boq_id)]",
    )
    orig_qty = fields.Float(related="boq_line_id.net_qty", string="Original Qty")
    revised_qty = fields.Float(string="Revised Qty")
    delta_qty = fields.Float(compute="_compute_delta_qty", store=True)
    orig_rate = fields.Float(related="boq_line_id.rate", string="Original Rate")
    revised_rate = fields.Float(string="Revised Rate", help="Leave 0 to keep the original rate.")
    orig_customer_rate = fields.Float(related="boq_line_id.customer_rate", string="Original Customer Rate")
    revised_customer_rate = fields.Float(string="Revised Customer Rate", help="Leave 0 to keep the original customer rate.")
    cost_effect = fields.Monetary(compute="_compute_effects", store=True, currency_field="currency_id")
    revenue_effect = fields.Monetary(compute="_compute_effects", store=True, currency_field="currency_id")
    schedule_effect_days = fields.Integer(default=0)
    currency_id = fields.Many2one(related="variation_id.currency_id", store=True)
    reason = fields.Char()

    @api.depends("revised_qty", "orig_qty")
    def _compute_delta_qty(self):
        for rec in self:
            rec.delta_qty = rec.revised_qty - rec.orig_qty

    @api.depends("delta_qty", "revised_rate", "orig_rate", "revised_customer_rate", "orig_customer_rate")
    def _compute_effects(self):
        for rec in self:
            rate = rec.revised_rate or rec.orig_rate
            crate = rec.revised_customer_rate or rec.orig_customer_rate
            rec.cost_effect = rec.delta_qty * rate
            rec.revenue_effect = rec.delta_qty * crate

    @api.onchange("boq_line_id")
    def _onchange_boq_line_id(self):
        if self.boq_line_id:
            self.revised_qty = self.boq_line_id.net_qty
