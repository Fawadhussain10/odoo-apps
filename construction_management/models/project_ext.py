from odoo import _, api, fields, models
from odoo.exceptions import UserError

CONSTRUCTION_STATE_SELECTION = [
    ("draft", "Draft"),
    ("tender", "Tender / Awarded"),
    ("mobilization", "Mobilization"),
    ("in_progress", "In Progress"),
    ("on_hold", "On Hold"),
    ("practical_completion", "Practical Completion"),
    ("defect_liability", "Defect Liability"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
]

CONTRACT_TYPE_SELECTION = [
    ("contractor", "Contractor (WIP on Contract Costing)"),
    ("property_developer", "Property Developer (WIP on Development Costing)"),
]

BILLING_POLICY_SELECTION = [
    ("milestone", "Fixed Milestone"),
    ("boq_qty", "BOQ Quantity"),
    ("percentage", "Percentage Completion"),
    ("cost_plus", "Cost Plus"),
]


class ProjectProject(models.Model):
    _inherit = "project.project"

    is_construction = fields.Boolean(
        string="Construction Project", default=False,
        help="Enables BOQ, budget, procurement, site inventory, subcontracting, WIP and construction dashboards on this project.",
    )
    construction_category_id = fields.Many2one("construction.project.category", string="Project Category")
    construction_subcategory_id = fields.Many2one(
        "construction.project.subcategory", string="Sub-Category",
        domain="[('category_id', '=', construction_category_id)]",
    )
    construction_team_id = fields.Many2one("construction.team", string="Construction Team")
    construction_state = fields.Selection(CONSTRUCTION_STATE_SELECTION, default="draft", tracking=True, copy=False)
    contract_type = fields.Selection(
        CONTRACT_TYPE_SELECTION, string="WIP / Accounting Profile", default="contractor", tracking=True,
        help="Fixed per project; the WIP and revenue recognition engine behaves differently for each profile. Changing it after activity has been posted requires finance approval.",
    )
    billing_policy = fields.Selection(BILLING_POLICY_SELECTION, string="Customer Billing Policy", default="boq_qty")

    # Organization (FDD 3.2)
    quantity_surveyor_id = fields.Many2one("res.users", string="Quantity Surveyor")
    site_engineer_id = fields.Many2one("res.users", string="Site Engineer")
    procurement_officer_id = fields.Many2one("res.users", string="Procurement Officer")
    storekeeper_id = fields.Many2one("res.users", string="Storekeeper")
    finance_controller_id = fields.Many2one("res.users", string="Finance Controller")

    # Dates (FDD 3.2)
    date_tender = fields.Date(string="Tender Date")
    date_award = fields.Date(string="Award Date")
    date_commencement = fields.Date(string="Commencement Date")
    date_contractual_completion = fields.Date(string="Contractual Completion")
    date_revised_completion = fields.Date(string="Revised Completion")
    date_defect_liability_end = fields.Date(string="Defect Liability End")

    # Commercial (FDD 3.2)
    original_contract_value = fields.Monetary(string="Original Contract Value", currency_field="currency_id")
    advance_amount = fields.Monetary(string="Customer Advance", currency_field="currency_id")
    retention_pct = fields.Float(string="Retention %", default=10.0)
    guarantee_amount = fields.Monetary(string="Performance Guarantee", currency_field="currency_id")
    penalty_amount = fields.Monetary(string="Penalties To Date", currency_field="currency_id")

    # Compliance registers (FDD 3.2) - lightweight text for now, formalized via construction.document register
    permit_reference = fields.Char(string="Permit Reference")
    insurance_reference = fields.Char(string="Insurance Reference")

    wbs_ids = fields.One2many("construction.wbs", "project_id", string="WBS / Phases")
    wbs_count = fields.Integer(compute="_compute_wbs_count")

    @api.depends("wbs_ids")
    def _compute_wbs_count(self):
        for rec in self:
            rec.wbs_count = len(rec.wbs_ids)

    @api.onchange("construction_category_id")
    def _onchange_construction_category_id(self):
        if self.construction_subcategory_id.category_id != self.construction_category_id:
            self.construction_subcategory_id = False

    def action_view_wbs(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("construction_management.action_construction_wbs")
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {"default_project_id": self.id}
        return action

    def action_generate_wbs_from_category(self):
        """Create one construction.wbs per default stage template of the project's category, if not already present."""
        self.ensure_one()
        if not self.construction_category_id:
            raise UserError(_("Set a Project Category first."))
        existing_templates = self.wbs_ids.mapped("stage_template_id")
        Wbs = self.env["construction.wbs"]
        sequence = 10
        for tmpl in self.construction_category_id.stage_ids.sorted("sequence"):
            if tmpl not in existing_templates:
                Wbs.create({
                    "name": tmpl.name,
                    "project_id": self.id,
                    "stage_template_id": tmpl.id,
                    "sequence": sequence,
                })
            sequence += 10
        return True

    def _construction_state_transition(self, new_state, allowed_from):
        for rec in self:
            if rec.construction_state not in allowed_from:
                raise UserError(_(
                    "Cannot move project '%(name)s' from '%(state)s' to '%(new_state)s'.",
                    name=rec.name, state=rec.construction_state, new_state=new_state,
                ))
        self.write({"construction_state": new_state})

    def action_construction_set_tender(self):
        self._construction_state_transition("tender", ["draft"])

    def action_construction_set_mobilization(self):
        self._construction_state_transition("mobilization", ["tender"])

    def action_construction_set_in_progress(self):
        self._construction_state_transition("in_progress", ["mobilization", "on_hold"])

    def action_construction_set_on_hold(self):
        self._construction_state_transition("on_hold", ["in_progress"])

    def action_construction_set_practical_completion(self):
        self._construction_state_transition("practical_completion", ["in_progress"])

    def action_construction_set_defect_liability(self):
        self._construction_state_transition("defect_liability", ["practical_completion"])

    def action_construction_set_closed(self):
        for rec in self:
            rec._check_construction_closure_ready()
        self._construction_state_transition("closed", ["defect_liability", "practical_completion"])

    def action_construction_set_cancelled(self):
        self.write({"construction_state": "cancelled"})

    def _check_construction_closure_ready(self):
        """Hook for other stages (procurement, inventory, subcontract, WIP, billing) to extend
        with their own outstanding-transaction checks before allowing project closure."""
        self.ensure_one()


class ProjectTask(models.Model):
    _inherit = "project.task"

    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    boq_line_id = fields.Many2one("construction.boq.line", string="BOQ Line")
    is_construction_task = fields.Boolean(related="project_id.is_construction", store=True)
