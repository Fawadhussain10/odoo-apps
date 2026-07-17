from odoo import _, api, fields, models
from odoo.exceptions import UserError

BOQ_STATE_SELECTION = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("negotiated", "Negotiated"),
    ("contract", "Contract"),
    ("approved", "Approved Baseline"),
    ("superseded", "Superseded"),
    ("as_built", "As-Built"),
]

# Control/tracking quantities may still be updated by execution modules even after the BOQ
# baseline is locked - only these fields are exempt from the immutability guard below.
LIVE_TRACKING_FIELDS = {
    "requested_qty", "ordered_qty", "received_qty", "issued_qty",
    "consumed_qty", "certified_qty", "invoiced_qty", "forecast_qty",
}


class ConstructionBoq(models.Model):
    _name = "construction.boq"
    _description = "Construction Project BOQ"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, revision_no desc"

    name = fields.Char(required=True, default="BOQ", tracking=True)
    code = fields.Char(copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)
    template_id = fields.Many2one("construction.boq.template", string="Source Template", readonly=True)

    revision_no = fields.Integer(default=1, readonly=True, copy=False)
    origin_boq_id = fields.Many2one("construction.boq", string="Original BOQ", readonly=True, copy=False)
    previous_revision_id = fields.Many2one("construction.boq", string="Previous Revision", readonly=True, copy=False)
    is_current = fields.Boolean(compute="_compute_is_current", store=True)
    is_baseline = fields.Boolean(compute="_compute_is_baseline", store=True,
                                  help="True while this revision is the approved, immutable governing baseline.")

    state = fields.Selection(BOQ_STATE_SELECTION, default="draft", tracking=True, copy=False)
    date_approved = fields.Datetime(readonly=True, copy=False)

    line_ids = fields.One2many("construction.boq.line", "boq_id", string="Lines", copy=True)
    total_amount = fields.Monetary(compute="_compute_total_amount", store=True, currency_field="currency_id")

    _sql_revision_uniq = models.Constraint(
        "unique(project_id, origin_boq_id, revision_no)",
        "Revision number must be unique within a BOQ family.",
    )

    @api.depends("line_ids.amount", "line_ids.display_type")
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.filtered(lambda l: not l.display_type).mapped("amount"))

    @api.depends("state")
    def _compute_is_baseline(self):
        for rec in self:
            rec.is_baseline = rec.state == "approved"

    @api.depends("state", "previous_revision_id")
    def _compute_is_current(self):
        superseded_ids = set(self.search([("id", "!=", False)]).filtered(
            lambda b: b.previous_revision_id
        ).mapped("previous_revision_id.id"))
        for rec in self:
            rec.is_current = rec.id not in superseded_ids and rec.state != "superseded"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = self.env["ir.sequence"].next_by_code("construction.boq") or "New"
        records = super().create(vals_list)
        for rec in records:
            if not rec.origin_boq_id:
                rec.origin_boq_id = rec.id
        return records

    def write(self, vals):
        protected = {"project_id"}
        if protected & set(vals) and any(rec.state in ("approved", "superseded", "as_built") for rec in self):
            raise UserError(_("An approved or superseded BOQ baseline cannot be re-pointed to another project."))
        return super().write(vals)

    # -- Workflow --
    def action_submit(self):
        self.filtered(lambda b: b.state == "draft").write({"state": "submitted"})

    def action_negotiate(self):
        self.filtered(lambda b: b.state == "submitted").write({"state": "negotiated"})

    def action_confirm_contract(self):
        self.filtered(lambda b: b.state == "negotiated").write({"state": "contract"})

    def action_reset_to_draft(self):
        self.filtered(lambda b: b.state in ("submitted", "negotiated", "contract")).write({"state": "draft"})

    def action_approve(self):
        for rec in self.filtered(lambda b: b.state == "contract"):
            rec.write({"state": "approved", "date_approved": fields.Datetime.now()})
            if rec.previous_revision_id and rec.previous_revision_id.state == "approved":
                rec.previous_revision_id.write({"state": "superseded"})

    def action_mark_as_built(self):
        self.filtered(lambda b: b.state == "approved").write({"state": "as_built"})

    def action_create_revision(self):
        self.ensure_one()
        if self.state not in ("approved", "as_built"):
            raise UserError(_("Only an approved baseline can be revised."))
        new_boq = self.copy({
            "name": self.name,
            "revision_no": self.revision_no + 1,
            "origin_boq_id": self.origin_boq_id.id,
            "previous_revision_id": self.id,
            "state": "draft",
            "date_approved": False,
            "code": False,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.boq",
            "res_id": new_boq.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_load_template_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.boq.load.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_boq_id": self.id},
        }

    def action_load_from_template(self, template):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Lines can only be loaded from a template while the BOQ is in Draft."))
        if self.line_ids:
            raise UserError(_("This BOQ already has lines. Clear them before loading a different template."))
        self.project_id.action_generate_wbs_from_category()
        wbs_by_template = {w.stage_template_id.id: w for w in self.project_id.wbs_ids if w.stage_template_id}
        Line = self.env["construction.boq.line"]
        for tline in template.line_ids:
            wbs = wbs_by_template.get(tline.stage_template_id.id)
            Line.create({
                "boq_id": self.id,
                "sequence": tline.sequence,
                "display_type": tline.display_type,
                "name": tline.name,
                "technical_basis": tline.technical_basis,
                "source_remarks": tline.source_remarks,
                "cost_code_id": tline.cost_code_id.id,
                "work_type_id": tline.work_type_id.id,
                "product_id": tline.product_id.id,
                "product_category_id": tline.product_category_id.id,
                "uom_id": tline.uom_id.id,
                "formula_type": tline.formula_type,
                "number": tline.number,
                "length": tline.length,
                "width": tline.width,
                "height": tline.height,
                "deduction": tline.deduction,
                "waste_pct": tline.waste_pct,
                "rate": tline.rate,
                "customer_rate": tline.customer_rate,
                "wbs_id": wbs.id if wbs else False,
            })
        self.template_id = template.id
        return True


class ConstructionBoqLine(models.Model):
    _name = "construction.boq.line"
    _description = "Construction Project BOQ Line"
    _inherit = ["construction.boq.line.mixin", "analytic.mixin"]
    _order = "boq_id, sequence, id"

    boq_id = fields.Many2one("construction.boq", required=True, ondelete="cascade", index=True)
    boq_state = fields.Selection(related="boq_id.state", store=True)
    project_id = fields.Many2one(related="boq_id.project_id", store=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")

    # Control quantities (FDD 5.2 "Control" group) - updated by procurement/inventory/subcontract/
    # billing modules even after the BOQ baseline is approved.
    requested_qty = fields.Float(default=0.0)
    ordered_qty = fields.Float(default=0.0)
    received_qty = fields.Float(default=0.0)
    issued_qty = fields.Float(default=0.0)
    consumed_qty = fields.Float(default=0.0)
    certified_qty = fields.Float(default=0.0)
    invoiced_qty = fields.Float(default=0.0)
    forecast_qty = fields.Float(default=0.0)

    variation_line_ids = fields.One2many("construction.variation.line", "boq_line_id", string="Variations")
    revised_net_qty = fields.Float(compute="_compute_revised", store=True)
    revised_rate = fields.Float(compute="_compute_revised", store=True)
    revised_amount = fields.Monetary(compute="_compute_revised", store=True, currency_field="currency_id")

    available_to_request = fields.Float(
        compute="_compute_available_to_request",
        help="Revised BOQ Quantity - Pending Requests - Ordered Quantity. requested_qty only counts "
             "requests not yet converted to an order, so a converted request is never subtracted twice.",
    )

    @api.depends(
        "net_qty", "rate",
        "variation_line_ids.state", "variation_line_ids.delta_qty", "variation_line_ids.revised_rate",
    )
    def _compute_revised(self):
        for rec in self:
            approved = rec.variation_line_ids.filtered(lambda l: l.state == "approved")
            rec.revised_net_qty = rec.net_qty + sum(approved.mapped("delta_qty"))
            last_rate = approved.sorted("write_date")[-1:].mapped("revised_rate")
            rec.revised_rate = last_rate[0] if last_rate and last_rate[0] else rec.rate
            rec.revised_amount = rec.revised_net_qty * rec.revised_rate

    @api.depends("revised_net_qty", "requested_qty", "ordered_qty")
    def _compute_available_to_request(self):
        for rec in self:
            rec.available_to_request = rec.revised_net_qty - rec.requested_qty - rec.ordered_qty

    def _check_baseline_editable(self, vals):
        if set(vals) <= LIVE_TRACKING_FIELDS:
            return
        for rec in self:
            if rec.boq_id.state in ("approved", "superseded", "as_built"):
                raise UserError(_(
                    "BOQ line '%(name)s' belongs to an approved/superseded baseline and cannot be edited; "
                    "use a Variation or create a new BOQ revision instead.",
                    name=rec.name,
                ))

    def write(self, vals):
        if not self.env.context.get("allow_boq_baseline_write"):
            self._check_baseline_editable(vals)
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("allow_boq_baseline_write"):
            for rec in self:
                if rec.boq_id.state in ("approved", "superseded", "as_built"):
                    raise UserError(_("Lines of an approved/superseded BOQ baseline cannot be deleted."))
        return super().unlink()
