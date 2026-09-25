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

INCIDENT_TYPE_SELECTION = [
    ("incident", "Incident"),
    ("near_miss", "Near Miss"),
    ("lost_time", "Lost-Time Event"),
    ("environmental", "Environmental Observation"),
]

SEVERITY_SELECTION = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

PROBABILITY_SELECTION = [
    ("unlikely", "Unlikely"),
    ("possible", "Possible"),
    ("likely", "Likely"),
    ("certain", "Almost Certain"),
]

INCIDENT_STATE_SELECTION = [
    ("open", "Open"),
    ("investigating", "Investigating"),
    ("closed_pending_verification", "Closed - Pending Verification"),
    ("closed", "Closed"),
]


class ConstructionHseToolbox(models.Model):
    """Toolbox talk log. Attendees are hr.employee (site workers), not res.users, since
    attendance is normally the workforce rather than system users."""
    _name = "construction.hse.toolbox"
    _description = "Construction HSE Toolbox Talk"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    topic = fields.Char(required=True)
    conducted_by = fields.Many2one("res.users", default=lambda self: self.env.user)
    attendee_ids = fields.Many2many("hr.employee", string="Attendees")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.hse.toolbox") or "New"
        return super().create(vals_list)


class ConstructionHseInspection(models.Model):
    """Mirrors construction.quality.inspection's shape/field-names, but for safety inspections
    and PPE/permit-to-work checks."""
    _name = "construction.hse.inspection"
    _description = "Construction HSE Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    inspection_date = fields.Date(default=fields.Date.context_today, required=True)
    inspector_id = fields.Many2one("res.users", string="Inspector", default=lambda self: self.env.user, tracking=True)
    permit_to_work_ref = fields.Char(string="Permit to Work Ref.")
    state = fields.Selection(INSPECTION_STATE_SELECTION, default="draft", tracking=True, copy=False)
    line_ids = fields.One2many("construction.hse.inspection.line", "inspection_id", string="Checklist Results", copy=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.hse.inspection") or "New"
        return super().create(vals_list)

    def action_start(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "in_progress"})

    def action_confirm_result(self):
        """Same deterministic rollup as construction.quality.inspection.action_confirm_result:
        any fail -> failed; no fail but >=1 explicit pass -> passed; all n/a (or no lines) ->
        conditional."""
        for rec in self.filtered(lambda r: r.state in ("draft", "in_progress")):
            results = rec.line_ids.mapped("result")
            if "fail" in results:
                new_state = "failed"
            elif "pass" in results:
                new_state = "passed"
            else:
                new_state = "conditional"
            rec.state = new_state


class ConstructionHseInspectionLine(models.Model):
    _name = "construction.hse.inspection.line"
    _description = "Construction HSE Inspection Line"
    _order = "sequence, id"

    inspection_id = fields.Many2one("construction.hse.inspection", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    description = fields.Char(required=True)
    result = fields.Selection(LINE_RESULT_SELECTION, default="pass", required=True)
    remarks = fields.Char()


class ConstructionHseIncident(models.Model):
    _name = "construction.hse.incident"
    _description = "Construction HSE Incident"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    incident_date = fields.Datetime(default=fields.Datetime.now, required=True)
    incident_type = fields.Selection(INCIDENT_TYPE_SELECTION, required=True, tracking=True)
    description = fields.Text(required=True)
    severity = fields.Selection(SEVERITY_SELECTION, default="low", required=True, tracking=True)
    probability = fields.Selection(PROBABILITY_SELECTION, default="possible", required=True, tracking=True)
    risk_score = fields.Integer(compute="_compute_risk_score", store=True)
    responsible_id = fields.Many2one("res.users", string="Responsible", required=True, tracking=True,
                                      help="Must differ from the user who closes the incident.")
    investigation_notes = fields.Text()
    corrective_action = fields.Text()
    state = fields.Selection(INCIDENT_STATE_SELECTION, default="open", tracking=True, copy=False)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    # Simple 4x4 risk matrix: risk_score = severity_level(1-4) * probability_level(1-4), giving a
    # 1-16 range. Banding (low/medium/high/critical) is left to reporting/views; only the raw
    # numeric score is stored here.
    _SEVERITY_MAP = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    _PROBABILITY_MAP = {"unlikely": 1, "possible": 2, "likely": 3, "certain": 4}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.hse.incident") or "New"
        return super().create(vals_list)

    @api.depends("severity", "probability")
    def _compute_risk_score(self):
        for rec in self:
            rec.risk_score = self._SEVERITY_MAP.get(rec.severity, 1) * self._PROBABILITY_MAP.get(rec.probability, 1)

    def action_investigate(self):
        self.filtered(lambda r: r.state == "open").write({"state": "investigating"})

    def action_submit_for_verification(self):
        self.filtered(lambda r: r.state == "investigating").write({"state": "closed_pending_verification"})

    def action_close(self):
        """Independent-verifier control: the user closing the incident must not be its
        responsible_id (mirrors construction.cycle.count.action_approve's counter-vs-approver
        guard, and construction.ncr.action_close above)."""
        for rec in self.filtered(lambda r: r.state == "closed_pending_verification"):
            if rec.responsible_id == self.env.user:
                raise UserError(_("The responsible user cannot also verify/close their own incident; an independent user must close it."))
            rec.state = "closed"
