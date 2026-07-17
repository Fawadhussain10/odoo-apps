from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionWbs(models.Model):
    _name = "construction.wbs"
    _description = "Construction WBS / Phase"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"
    _parent_store = True
    _rec_name = "complete_name"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char()
    complete_name = fields.Char(compute="_compute_complete_name", store=True, recursive=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)
    parent_id = fields.Many2one("construction.wbs", string="Parent WBS", ondelete="cascade",
                                 domain="[('project_id', '=', project_id)]")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("construction.wbs", "parent_id", string="Sub WBS")
    stage_template_id = fields.Many2one("construction.wbs.stage.template", string="Stage Template")
    owner_id = fields.Many2one("res.users", string="Responsible")
    date_start = fields.Date()
    date_end = fields.Date()
    predecessor_ids = fields.Many2many(
        "construction.wbs", "construction_wbs_predecessor_rel", "wbs_id", "predecessor_id",
        string="Predecessors", domain="[('project_id', '=', project_id)]",
    )
    boq_line_ids = fields.One2many("construction.boq.line", "wbs_id", string="BOQ Lines")
    task_ids = fields.One2many("project.task", "wbs_id", string="Tasks")
    active = fields.Boolean(default=True)

    # -- Five distinct progress measures (FDD 4: never overwrite financial progress by editing a %) --
    progress_physical = fields.Float(string="Physical Progress %", default=0.0, tracking=True,
                                      help="Driven by approved daily site reports / measured BOQ quantities. Not user-editable directly.")
    progress_schedule = fields.Float(string="Schedule Progress %", compute="_compute_progress_schedule", store=True)
    progress_procurement = fields.Float(string="Procurement Progress %", default=0.0,
                                         help="Share of the revised BOQ quantity that has been ordered/received.")
    progress_billing = fields.Float(string="Billing Progress %", default=0.0,
                                     help="Share of the revised contract value certified to the customer.")
    progress_financial = fields.Float(string="Financial (Cost) Progress %", default=0.0,
                                       help="Actual eligible cost incurred / latest estimated total eligible cost.")

    _sql_date_check = models.Constraint(
        "CHECK(date_end IS NULL OR date_start IS NULL OR date_end >= date_start)",
        "WBS end date cannot be before its start date.",
    )

    @api.depends("name", "code", "parent_id.complete_name")
    def _compute_complete_name(self):
        for rec in self:
            label = f"[{rec.code}] {rec.name}" if rec.code else rec.name
            rec.complete_name = f"{rec.parent_id.complete_name} / {label}" if rec.parent_id else label

    @api.depends("date_start", "date_end")
    def _compute_progress_schedule(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_start or not rec.date_end or rec.date_end <= rec.date_start:
                rec.progress_schedule = 0.0
                continue
            if today <= rec.date_start:
                rec.progress_schedule = 0.0
            elif today >= rec.date_end:
                rec.progress_schedule = 100.0
            else:
                total = (rec.date_end - rec.date_start).days or 1
                elapsed = (today - rec.date_start).days
                rec.progress_schedule = round(100.0 * elapsed / total, 2)

    @api.constrains("parent_id")
    def _check_parent_recursion(self):
        if not self._check_recursion():
            raise ValidationError(self.env._("You cannot create a recursive WBS hierarchy."))

    def recompute_physical_progress_from_boq(self):
        """Weighted-average physical progress from linked BOQ lines' certified vs BOQ quantity.
        Called by daily-report approval once that model exists; safe to call any time."""
        for rec in self:
            lines = rec.boq_line_ids.filtered(lambda l: not l.display_type and l.net_qty)
            if not lines:
                continue
            weight_total = sum(lines.mapped("amount")) or 0.0
            if not weight_total:
                continue
            weighted = sum(
                (line.certified_qty / line.net_qty if line.net_qty else 0.0) * line.amount
                for line in lines
            )
            rec.progress_physical = round(100.0 * weighted / weight_total, 2)
