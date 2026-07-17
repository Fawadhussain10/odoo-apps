from odoo import _, api, fields, models
from odoo.exceptions import UserError

INSPECTION_STATE_SELECTION = [
    ("draft", "Draft"),
    ("in_progress", "In Progress"),
    ("passed", "Passed"),
    ("failed", "Failed"),
    ("conditional", "Conditional"),
]

LINE_RESULT_SELECTION = [("pass", "Pass"), ("fail", "Fail"), ("na", "N/A")]

NCR_STATE_SELECTION = [
    ("open", "Open"),
    ("in_progress", "In Progress"),
    ("closed_pending_verification", "Closed - Pending Verification"),
    ("closed", "Closed"),
]

SNAG_STATE_SELECTION = [
    ("open", "Open"),
    ("rectified", "Rectified"),
    ("verified", "Verified"),
    ("closed", "Closed"),
]


class ConstructionQualityItp(models.Model):
    """Reusable/template Inspection & Test Plan definition - configuration-like record, no
    state machine (same spirit as construction.wbs.stage.template)."""
    _name = "construction.quality.itp"
    _description = "Construction Inspection & Test Plan"
    _order = "name"

    name = fields.Char(required=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line",
        domain="[('project_id', '=', project_id), ('display_type', '=', False)]",
    )
    checklist_ids = fields.One2many("construction.quality.itp.checklist.item", "itp_id", string="Checklist Items", copy=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)


class ConstructionQualityItpChecklistItem(models.Model):
    _name = "construction.quality.itp.checklist.item"
    _description = "Construction ITP Checklist Item"
    _order = "sequence, id"

    itp_id = fields.Many2one("construction.quality.itp", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    description = fields.Char(required=True)
    is_mandatory = fields.Boolean(default=True)


class ConstructionQualityInspection(models.Model):
    _name = "construction.quality.inspection"
    _description = "Construction Quality Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line",
        domain="[('project_id', '=', project_id), ('display_type', '=', False)]",
    )
    itp_id = fields.Many2one(
        "construction.quality.itp", string="Inspection & Test Plan",
        domain="[('project_id', '=', project_id)]",
    )
    inspection_date = fields.Date(default=fields.Date.context_today, required=True)
    inspector_id = fields.Many2one("res.users", string="Inspector", default=lambda self: self.env.user, tracking=True)
    state = fields.Selection(INSPECTION_STATE_SELECTION, default="draft", tracking=True, copy=False)
    line_ids = fields.One2many("construction.quality.inspection.line", "inspection_id", string="Checklist Results", copy=True)
    ncr_ids = fields.One2many("construction.ncr", "inspection_id", string="NCRs Raised")
    ncr_count = fields.Integer(compute="_compute_ncr_count")
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.depends("ncr_ids")
    def _compute_ncr_count(self):
        for rec in self:
            rec.ncr_count = len(rec.ncr_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.quality.inspection") or "New"
        records = super().create(vals_list)
        for rec in records:
            if rec.itp_id and not rec.line_ids:
                rec._populate_lines_from_itp()
        return records

    @api.onchange("itp_id")
    def _onchange_itp_id(self):
        if self.itp_id:
            self.line_ids = [(5, 0, 0)] + [
                (0, 0, {"description": item.description, "result": "pass"})
                for item in self.itp_id.checklist_ids
            ]

    def _populate_lines_from_itp(self):
        self.ensure_one()
        Line = self.env["construction.quality.inspection.line"]
        for item in self.itp_id.checklist_ids:
            Line.create({"inspection_id": self.id, "description": item.description, "result": "pass"})

    def action_start(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "in_progress"})

    def action_confirm_result(self):
        """Deterministic rollup from line results (documented judgment call):
        - any line result 'fail' -> overall 'failed'
        - no fail and at least one explicit 'pass' (remaining lines may be 'na') -> 'passed'
        - no lines, or every line is 'na' -> 'conditional' (nothing was actually verified)
        """
        for rec in self.filtered(lambda r: r.state in ("draft", "in_progress")):
            results = rec.line_ids.mapped("result")
            if "fail" in results:
                new_state = "failed"
            elif "pass" in results:
                new_state = "passed"
            else:
                new_state = "conditional"
            rec.state = new_state


class ConstructionQualityInspectionLine(models.Model):
    _name = "construction.quality.inspection.line"
    _description = "Construction Quality Inspection Line"
    _order = "sequence, id"

    inspection_id = fields.Many2one("construction.quality.inspection", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    description = fields.Char(required=True)
    result = fields.Selection(LINE_RESULT_SELECTION, default="pass", required=True)
    remarks = fields.Char()


class ConstructionNcr(models.Model):
    _name = "construction.ncr"
    _description = "Construction Non-Conformance Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    inspection_id = fields.Many2one(
        "construction.quality.inspection", string="Source Inspection",
        domain="[('project_id', '=', project_id)]",
    )
    description = fields.Text(required=True)
    root_cause = fields.Text()
    corrective_action = fields.Text()
    owner_id = fields.Many2one("res.users", string="Owner", required=True, tracking=True,
                                help="Responsible for closure. Must differ from the user who closes the NCR.")
    target_date = fields.Date()
    state = fields.Selection(NCR_STATE_SELECTION, default="open", tracking=True, copy=False)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.ncr") or "New"
        return super().create(vals_list)

    @api.onchange("inspection_id")
    def _onchange_inspection_id(self):
        if self.inspection_id:
            self.project_id = self.inspection_id.project_id
            self.wbs_id = self.inspection_id.wbs_id

    def action_start(self):
        self.filtered(lambda r: r.state == "open").write({"state": "in_progress"})

    def action_submit_for_verification(self):
        self.filtered(lambda r: r.state == "in_progress").write({"state": "closed_pending_verification"})

    def action_close(self):
        """Independent-verifier control: the user closing the NCR must not be its owner
        (mirrors construction.cycle.count.action_approve's counter-vs-approver guard)."""
        for rec in self.filtered(lambda r: r.state == "closed_pending_verification"):
            if rec.owner_id == self.env.user:
                raise UserError(_("The NCR owner cannot also verify/close their own NCR; an independent user must close it."))
            rec.state = "closed"


class ConstructionSnag(models.Model):
    _name = "construction.snag"
    _description = "Construction Snag List / Defect Liability Item"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line",
        domain="[('project_id', '=', project_id), ('display_type', '=', False)]",
    )
    description = fields.Text(required=True)
    raised_by = fields.Many2one("res.users", default=lambda self: self.env.user)
    raised_date = fields.Date(default=fields.Date.context_today)
    target_date = fields.Date()
    state = fields.Selection(SNAG_STATE_SELECTION, default="open", tracking=True, copy=False)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.snag") or "New"
        return super().create(vals_list)

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if self.project_id.date_defect_liability_end:
            self.target_date = self.project_id.date_defect_liability_end

    def action_rectify(self):
        self.filtered(lambda r: r.state == "open").write({"state": "rectified"})

    def action_verify(self):
        self.filtered(lambda r: r.state == "rectified").write({"state": "verified"})

    def action_close(self):
        self.filtered(lambda r: r.state == "verified").write({"state": "closed"})
