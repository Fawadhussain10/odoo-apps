from odoo import api, fields, models

DAILY_REPORT_STATE_SELECTION = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


class ConstructionDailyReport(models.Model):
    _name = "construction.daily.report"
    _description = "Construction Daily Site Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    weather = fields.Char()
    state = fields.Selection(DAILY_REPORT_STATE_SELECTION, default="draft", tracking=True, copy=False)

    manpower_line_ids = fields.One2many("construction.daily.report.manpower", "report_id", string="Manpower", copy=True)
    equipment_line_ids = fields.One2many("construction.daily.report.equipment.line", "report_id", string="Equipment", copy=True)
    subcontractor_line_ids = fields.One2many(
        "construction.daily.report.subcontractor.line", "report_id", string="Subcontractors Present", copy=True,
    )
    executed_line_ids = fields.One2many(
        "construction.daily.report.executed.line", "report_id", string="Work Executed", copy=True,
    )

    delays = fields.Text()
    instructions = fields.Text()
    quality_notes = fields.Text(help="Quality inspections / safety events. Attach photographs via the chatter.")

    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.daily.report") or "New"
        return super().create(vals_list)

    def action_submit(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            rec.state = "submitted"

    def action_approve(self):
        for rec in self.filtered(lambda r: r.state == "submitted"):
            rec.state = "approved"
            # Approved quantities update physical progress; rejected or draft reports have no
            # effect (FDD). recompute_physical_progress_from_boq() is idempotent/safe to call.
            wbs_recs = rec.executed_line_ids.mapped("wbs_id") | rec.wbs_id
            wbs_recs.recompute_physical_progress_from_boq()

    def action_reject(self):
        self.filtered(lambda r: r.state == "submitted").write({"state": "rejected"})

    def action_reset_to_draft(self):
        self.filtered(lambda r: r.state in ("submitted", "rejected")).write({"state": "draft"})


class ConstructionDailyReportManpower(models.Model):
    _name = "construction.daily.report.manpower"
    _description = "Construction Daily Report Manpower Line"
    _order = "id"

    report_id = fields.Many2one("construction.daily.report", required=True, ondelete="cascade")
    state = fields.Selection(related="report_id.state", store=True)
    trade = fields.Char(required=True)
    headcount = fields.Integer(required=True)


class ConstructionDailyReportEquipmentLine(models.Model):
    _name = "construction.daily.report.equipment.line"
    _description = "Construction Daily Report Equipment Line"
    _order = "id"

    report_id = fields.Many2one("construction.daily.report", required=True, ondelete="cascade")
    state = fields.Selection(related="report_id.state", store=True)
    # No equipment master model exists yet - plain Char to avoid a cross-agent dependency.
    equipment_name = fields.Char(required=True)
    hours_used = fields.Float()


class ConstructionDailyReportSubcontractorLine(models.Model):
    _name = "construction.daily.report.subcontractor.line"
    _description = "Construction Daily Report Subcontractor Present Line"
    _order = "id"

    report_id = fields.Many2one("construction.daily.report", required=True, ondelete="cascade")
    state = fields.Selection(related="report_id.state", store=True)
    subcontract_id = fields.Many2one(
        "construction.subcontract", string="Subcontract", required=True,
        domain="[('project_id', '=', parent.project_id)]",
    )
    manpower_count = fields.Integer(string="Manpower Count")


class ConstructionDailyReportExecutedLine(models.Model):
    _name = "construction.daily.report.executed.line"
    _description = "Construction Daily Report Executed Quantity Line"
    _order = "id"

    report_id = fields.Many2one("construction.daily.report", required=True, ondelete="cascade")
    state = fields.Selection(related="report_id.state", store=True)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    wbs_id = fields.Many2one(related="boq_line_id.wbs_id", store=True)
    executed_qty = fields.Float(
        string="Executed Qty",
        help="Quantity of this BOQ item physically executed/completed today. This is progress, "
             "not material consumption.",
    )
    remarks = fields.Char()


class ConstructionBoqLineDailyExecuted(models.Model):
    """Own, non-conflicting tracking field fed by approved daily reports only. Does not touch
    certified_qty (billing-owned) or any other control quantity already computed elsewhere."""
    _inherit = "construction.boq.line"

    daily_report_executed_line_ids = fields.One2many("construction.daily.report.executed.line", "boq_line_id")
    daily_executed_qty = fields.Float(compute="_compute_daily_executed_qty", store=True)

    @api.depends("daily_report_executed_line_ids.executed_qty", "daily_report_executed_line_ids.state")
    def _compute_daily_executed_qty(self):
        for rec in self:
            approved = rec.daily_report_executed_line_ids.filtered(lambda l: l.state == "approved")
            rec.daily_executed_qty = sum(approved.mapped("executed_qty"))


class ProjectProjectDailyReport(models.Model):
    _inherit = "project.project"

    daily_report_ids = fields.One2many("construction.daily.report", "project_id", string="Daily Reports")
    daily_report_count = fields.Integer(compute="_compute_daily_report_count")

    def _compute_daily_report_count(self):
        for rec in self:
            rec.daily_report_count = len(rec.daily_report_ids)
