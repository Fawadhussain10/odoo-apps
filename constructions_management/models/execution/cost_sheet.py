from odoo import api, fields, models

COST_SHEET_STATE_SELECTION = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
]


class ConstructionCostSheet(models.Model):
    _name = "construction.cost.sheet"
    _description = "Construction Cost Sheet (Budget vs Actual)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one(
        "construction.wbs", string="WBS / Phase", required=True, domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    task_id = fields.Many2one("project.task", string="Task", domain="[('project_id', '=', project_id)]")
    date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection(COST_SHEET_STATE_SELECTION, default="draft", tracking=True, copy=False)

    line_ids = fields.One2many("construction.cost.sheet.line", "cost_sheet_id", string="Lines", copy=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    total_budget_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    total_actual_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    total_variance_amount = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")

    @api.depends("line_ids.budget_amount", "line_ids.actual_amount", "line_ids.variance_amount")
    def _compute_totals(self):
        for rec in self:
            rec.total_budget_amount = sum(rec.line_ids.mapped("budget_amount"))
            rec.total_actual_amount = sum(rec.line_ids.mapped("actual_amount"))
            rec.total_variance_amount = sum(rec.line_ids.mapped("variance_amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.cost.sheet") or "New"
        return super().create(vals_list)

    def action_confirm(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "confirmed"})

    def action_reset_to_draft(self):
        self.filtered(lambda r: r.state == "confirmed").write({"state": "draft"})


class ConstructionCostSheetLine(models.Model):
    _name = "construction.cost.sheet.line"
    _description = "Construction Cost Sheet Line"
    _order = "sequence, id"

    cost_sheet_id = fields.Many2one("construction.cost.sheet", required=True, ondelete="cascade")
    state = fields.Selection(related="cost_sheet_id.state", store=True)
    sequence = fields.Integer(default=10)
    currency_id = fields.Many2one(related="cost_sheet_id.currency_id", store=True)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    budget_qty = fields.Float(related="boq_line_id.revised_net_qty", store=True, readonly=True)
    budget_amount = fields.Monetary(related="boq_line_id.revised_amount", store=True, currency_field="currency_id", readonly=True)
    actual_qty = fields.Float(related="boq_line_id.consumed_qty", store=True, readonly=True)
    actual_amount = fields.Monetary(compute="_compute_actual_amount", store=True, currency_field="currency_id")
    variance_qty = fields.Float(compute="_compute_variance", store=True)
    variance_amount = fields.Monetary(compute="_compute_variance", store=True, currency_field="currency_id")

    @api.depends("actual_qty", "boq_line_id.rate")
    def _compute_actual_amount(self):
        for rec in self:
            rec.actual_amount = rec.actual_qty * rec.boq_line_id.rate

    @api.depends("budget_qty", "actual_qty", "budget_amount", "actual_amount")
    def _compute_variance(self):
        for rec in self:
            rec.variance_qty = rec.budget_qty - rec.actual_qty
            rec.variance_amount = rec.budget_amount - rec.actual_amount


class ProjectTaskCostSheet(models.Model):
    _inherit = "project.task"

    cost_sheet_ids = fields.One2many("construction.cost.sheet", "task_id", string="Cost Sheets")
    cost_sheet_count = fields.Integer(compute="_compute_cost_sheet_count")

    def _compute_cost_sheet_count(self):
        for rec in self:
            rec.cost_sheet_count = len(rec.cost_sheet_ids)

    def action_create_cost_sheet(self):
        self.ensure_one()
        sheet = self.env["construction.cost.sheet"].create({
            "project_id": self.project_id.id,
            "wbs_id": self.wbs_id.id,
            "task_id": self.id,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.cost.sheet",
            "res_id": sheet.id,
            "view_mode": "form",
            "target": "current",
        }
