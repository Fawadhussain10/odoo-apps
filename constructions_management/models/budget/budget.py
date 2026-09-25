from odoo import api, fields, models

# FDD 6.2 "Budget and Cost-Control Engine" - these fields deliberately reuse existing data
# (revised_amount from the BOQ/variation engine, consumed_qty from Stage 5 inventory,
# certified_qty from the WIP-stage progress certificates, forecast_qty already on the line)
# rather than duplicating cost logic that already exists elsewhere in the module.


class ConstructionBoqLineBudget(models.Model):
    _inherit = "construction.boq.line"

    forecast_rate = fields.Float(
        string="Forecast Rate",
        help="Latest expected final unit rate for this item. Defaults to the budget rate; "
             "override when a rate revision is expected but not yet a formal Variation.",
    )
    purchase_line_ids = fields.One2many("purchase.order.line", "construction_boq_line_id", string="Purchase Lines")

    committed_amount = fields.Monetary(
        compute="_compute_budget_control", store=True, currency_field="currency_id",
        string="Open PO Commitment",
        help="Confirmed PO value not yet invoiced. Purchase-order lines already invoiced are "
             "excluded so they are not counted as both a commitment and an actual cost.",
    )
    actual_cost = fields.Monetary(
        compute="_compute_budget_control", store=True, currency_field="currency_id",
        help="Posted material consumption cost (consumed qty x budget rate). Subcontract/labour/"
             "overhead actuals are captured at cost-sheet/WIP level via analytic postings; this "
             "field is the material-cost component visible directly on the BOQ line.",
    )
    etc = fields.Monetary(
        compute="_compute_budget_control", store=True, currency_field="currency_id",
        string="ETC (Estimate to Complete)",
        help="Remaining planned work at forecast quantity/rate: (Revised Qty - Consumed Qty) x Forecast Rate.",
    )
    eac = fields.Monetary(
        compute="_compute_budget_control", store=True, currency_field="currency_id",
        string="EAC (Estimate at Completion)",
        help="Actual cost + open commitment + ETC not already committed.",
    )
    variance_at_completion = fields.Monetary(
        compute="_compute_budget_control", store=True, currency_field="currency_id",
        help="Revised Budget - EAC. Positive = saving; negative = overrun.",
    )
    variance_pct = fields.Float(
        compute="_compute_budget_control", store=True,
        string="Variance %", help="Variance at Completion / Revised Budget.",
    )
    quantity_variance = fields.Float(
        compute="_compute_budget_control", store=True,
        help="Revised BOQ Quantity - Forecast Final Quantity.",
    )
    rate_variance = fields.Monetary(
        compute="_compute_budget_control", store=True, currency_field="currency_id",
        help="(Budget Rate - Forecast Rate) x Forecast Quantity.",
    )
    usage_variance = fields.Monetary(
        compute="_compute_budget_control", store=True, currency_field="currency_id",
        help="(Allowed Quantity for Progress - Consumed Quantity) x Budget Rate. Allowed quantity "
             "= Revised Qty x WBS Physical Progress %.",
    )

    @api.depends(
        "revised_net_qty", "revised_amount", "rate", "forecast_rate", "forecast_qty",
        "consumed_qty", "wbs_id.progress_physical",
        "purchase_line_ids.state", "purchase_line_ids.price_subtotal",
        "purchase_line_ids.qty_invoiced", "purchase_line_ids.product_qty",
    )
    def _compute_budget_control(self):
        for rec in self:
            confirmed_lines = rec.purchase_line_ids.filtered(lambda l: l.state in ("purchase", "done"))
            committed = 0.0
            for line in confirmed_lines:
                invoiced_ratio = (line.qty_invoiced / line.product_qty) if line.product_qty else 0.0
                committed += line.price_subtotal * max(1.0 - invoiced_ratio, 0.0)
            rec.committed_amount = committed

            rec.actual_cost = rec.consumed_qty * rec.rate

            forecast_rate = rec.forecast_rate or rec.rate
            remaining_qty = max(rec.revised_net_qty - rec.consumed_qty, 0.0)
            rec.etc = remaining_qty * forecast_rate

            rec.eac = rec.actual_cost + rec.committed_amount + max(rec.etc - rec.committed_amount, 0.0)
            rec.variance_at_completion = rec.revised_amount - rec.eac
            rec.variance_pct = (rec.variance_at_completion / rec.revised_amount) if rec.revised_amount else 0.0

            forecast_qty = rec.forecast_qty or rec.revised_net_qty
            rec.quantity_variance = rec.revised_net_qty - forecast_qty
            rec.rate_variance = (rec.rate - forecast_rate) * forecast_qty

            allowed_qty = rec.revised_net_qty * ((rec.wbs_id.progress_physical or 0.0) / 100.0)
            rec.usage_variance = (allowed_qty - rec.consumed_qty) * rec.rate


class ConstructionWbsBudget(models.Model):
    _inherit = "construction.wbs"

    original_budget = fields.Monetary(compute="_compute_wbs_budget", store=True, currency_field="currency_id")
    revised_budget = fields.Monetary(compute="_compute_wbs_budget", store=True, currency_field="currency_id")
    committed_amount = fields.Monetary(compute="_compute_wbs_budget", store=True, currency_field="currency_id")
    actual_cost = fields.Monetary(compute="_compute_wbs_budget", store=True, currency_field="currency_id")
    eac = fields.Monetary(compute="_compute_wbs_budget", store=True, currency_field="currency_id")
    variance_at_completion = fields.Monetary(compute="_compute_wbs_budget", store=True, currency_field="currency_id")
    variance_pct = fields.Float(compute="_compute_wbs_budget", store=True)

    @api.depends(
        "boq_line_ids.amount", "boq_line_ids.revised_amount", "boq_line_ids.committed_amount",
        "boq_line_ids.actual_cost", "boq_line_ids.eac", "boq_line_ids.display_type",
    )
    def _compute_wbs_budget(self):
        for rec in self:
            lines = rec.boq_line_ids.filtered(lambda l: not l.display_type)
            rec.original_budget = sum(lines.mapped("amount"))
            rec.revised_budget = sum(lines.mapped("revised_amount"))
            rec.committed_amount = sum(lines.mapped("committed_amount"))
            rec.actual_cost = sum(lines.mapped("actual_cost"))
            rec.eac = sum(lines.mapped("eac"))
            rec.variance_at_completion = rec.revised_budget - rec.eac
            rec.variance_pct = (rec.variance_at_completion / rec.revised_budget) if rec.revised_budget else 0.0


class ProjectProjectBudget(models.Model):
    _inherit = "project.project"

    original_budget = fields.Monetary(compute="_compute_project_budget", store=True, currency_field="currency_id")
    revised_budget = fields.Monetary(compute="_compute_project_budget", store=True, currency_field="currency_id")
    committed_amount = fields.Monetary(compute="_compute_project_budget", store=True, currency_field="currency_id")
    actual_cost = fields.Monetary(compute="_compute_project_budget", store=True, currency_field="currency_id")
    eac = fields.Monetary(compute="_compute_project_budget", store=True, currency_field="currency_id")
    variance_at_completion = fields.Monetary(compute="_compute_project_budget", store=True, currency_field="currency_id")
    variance_pct = fields.Float(compute="_compute_project_budget", store=True)

    @api.depends("wbs_ids.original_budget", "wbs_ids.revised_budget", "wbs_ids.committed_amount",
                 "wbs_ids.actual_cost", "wbs_ids.eac")
    def _compute_project_budget(self):
        for rec in self:
            rec.original_budget = sum(rec.wbs_ids.mapped("original_budget"))
            rec.revised_budget = sum(rec.wbs_ids.mapped("revised_budget"))
            rec.committed_amount = sum(rec.wbs_ids.mapped("committed_amount"))
            rec.actual_cost = sum(rec.wbs_ids.mapped("actual_cost"))
            rec.eac = sum(rec.wbs_ids.mapped("eac"))
            rec.variance_at_completion = rec.revised_budget - rec.eac
            rec.variance_pct = (rec.variance_at_completion / rec.revised_budget) if rec.revised_budget else 0.0
