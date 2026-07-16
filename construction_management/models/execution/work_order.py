from odoo import _, api, fields, models
from odoo.exceptions import UserError

WORK_ORDER_STATE_SELECTION = [
    ("draft", "Draft"),
    ("in_progress", "In Progress"),
    ("inspection", "Inspection"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
]


class ConstructionWorkOrder(models.Model):
    _name = "construction.work.order"
    _description = "Construction Work Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    boq_line_ids = fields.Many2many(
        "construction.boq.line", "construction_work_order_boq_line_rel", "work_order_id", "boq_line_id",
        string="BOQ Lines", domain="[('project_id', '=', project_id), ('display_type', '=', False)]",
    )
    responsible_id = fields.Many2one("res.users", string="Responsible", default=lambda self: self.env.user, tracking=True)
    date_start = fields.Date()
    date_end = fields.Date()
    state = fields.Selection(WORK_ORDER_STATE_SELECTION, default="draft", tracking=True, copy=False)

    material_line_ids = fields.One2many("construction.work.order.material.line", "work_order_id", string="Material", copy=True)
    labour_line_ids = fields.One2many("construction.work.order.labour.line", "work_order_id", string="Labour", copy=True)
    equipment_line_ids = fields.One2many("construction.work.order.equipment.line", "work_order_id", string="Equipment", copy=True)

    material_issue_ids = fields.One2many("construction.material.issue", "work_order_id", string="Material Issues")
    material_issue_count = fields.Integer(compute="_compute_material_issue_count")

    company_id = fields.Many2one(related="project_id.company_id", store=True)

    _sql_date_check = models.Constraint(
        "CHECK(date_end IS NULL OR date_start IS NULL OR date_end >= date_start)",
        "Work Order end date cannot be before its start date.",
    )

    @api.depends("material_issue_ids")
    def _compute_material_issue_count(self):
        for rec in self:
            rec.material_issue_count = len(rec.material_issue_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.work.order") or "New"
        return super().create(vals_list)

    def action_start(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            if not rec.boq_line_ids:
                raise UserError(_("Add at least one BOQ line before starting the work order."))
            rec.state = "in_progress"

    def action_send_inspection(self):
        self.filtered(lambda r: r.state == "in_progress").write({"state": "inspection"})

    def action_close(self):
        self.filtered(lambda r: r.state == "inspection").write({"state": "closed"})

    def action_cancel(self):
        self.filtered(lambda r: r.state not in ("closed", "cancelled")).write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self.filtered(lambda r: r.state not in ("draft", "closed")).write({"state": "draft"})


class ConstructionWorkOrderMaterialLine(models.Model):
    _name = "construction.work.order.material.line"
    _description = "Construction Work Order Material Line"
    _order = "id"

    work_order_id = fields.Many2one("construction.work.order", required=True, ondelete="cascade")
    state = fields.Selection(related="work_order_id.state", store=True)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one(related="boq_line_id.product_id", store=True, readonly=False)
    uom_id = fields.Many2one(related="boq_line_id.uom_id", store=True, readonly=False)
    planned_qty = fields.Float()
    actual_qty = fields.Float(help="Manual entry; not auto-derived from material consumption.")


class ConstructionWorkOrderLabourLine(models.Model):
    _name = "construction.work.order.labour.line"
    _description = "Construction Work Order Labour Line"
    _order = "id"

    work_order_id = fields.Many2one("construction.work.order", required=True, ondelete="cascade")
    state = fields.Selection(related="work_order_id.state", store=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", required=True)
    planned_hours = fields.Float()
    actual_hours = fields.Float()


class ConstructionWorkOrderEquipmentLine(models.Model):
    _name = "construction.work.order.equipment.line"
    _description = "Construction Work Order Equipment Line"
    _order = "id"

    work_order_id = fields.Many2one("construction.work.order", required=True, ondelete="cascade")
    state = fields.Selection(related="work_order_id.state", store=True)
    # No equipment master model exists yet - plain Char to avoid a cross-agent dependency.
    equipment_name = fields.Char(required=True)
    planned_hours = fields.Float()
    actual_hours = fields.Float()


class ConstructionMaterialIssueWorkOrder(models.Model):
    """Deferred in Stage 5 because construction.work.order did not exist yet."""
    _inherit = "construction.material.issue"

    work_order_id = fields.Many2one(
        "construction.work.order", string="Work Order", domain="[('project_id', '=', project_id)]",
    )


class ProjectProjectWorkOrder(models.Model):
    _inherit = "project.project"

    work_order_ids = fields.One2many("construction.work.order", "project_id", string="Work Orders")
    work_order_count = fields.Integer(compute="_compute_work_order_count")

    def _compute_work_order_count(self):
        for rec in self:
            rec.work_order_count = len(rec.work_order_ids)
