from odoo import _, api, fields, models
from odoo.exceptions import UserError

SUBCONTRACT_STATE_SELECTION = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
]


class ConstructionSubcontract(models.Model):
    _name = "construction.subcontract"
    _description = "Construction Subcontract Agreement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    code = fields.Char(copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    subcontractor_id = fields.Many2one("res.partner", string="Subcontractor", required=True, tracking=True)
    scope = fields.Text()
    date_start = fields.Date()
    date_end = fields.Date(string="Deadline")
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    state = fields.Selection(SUBCONTRACT_STATE_SELECTION, default="draft", tracking=True, copy=False)

    retention_pct = fields.Float(string="Retention %", default=10.0)
    advance_amount = fields.Monetary(string="Advance Given")
    advance_recovery_pct = fields.Float(string="Advance Recovery % per Certificate", default=20.0)
    guarantee_amount = fields.Monetary(string="Performance Guarantee")
    company_supplied_material = fields.Boolean(string="Company Supplies Material")

    line_ids = fields.One2many("construction.subcontract.line", "subcontract_id", string="Scope Lines", copy=True)
    contract_value = fields.Monetary(compute="_compute_contract_value", store=True, currency_field="currency_id")
    measurement_ids = fields.One2many("construction.measurement", "subcontract_id", string="Measurements")
    measurement_count = fields.Integer(compute="_compute_document_counts")
    ra_certificate_ids = fields.One2many("construction.ra.certificate", "subcontract_id", string="RA Certificates")
    ra_certificate_count = fields.Integer(compute="_compute_document_counts")

    def _compute_document_counts(self):
        for rec in self:
            rec.measurement_count = len(rec.measurement_ids)
            rec.ra_certificate_count = len(rec.ra_certificate_ids)
    certified_value = fields.Monetary(compute="_compute_certified_value", store=True, currency_field="currency_id")
    advance_recovered = fields.Monetary(compute="_compute_certified_value", store=True, currency_field="currency_id")
    retention_held = fields.Monetary(compute="_compute_certified_value", store=True, currency_field="currency_id")

    @api.depends("line_ids.value")
    def _compute_contract_value(self):
        for rec in self:
            rec.contract_value = sum(rec.line_ids.mapped("value"))

    @api.depends("ra_certificate_ids.state", "ra_certificate_ids.gross_work", "ra_certificate_ids.advance_recovery_amount", "ra_certificate_ids.retention_amount")
    def _compute_certified_value(self):
        for rec in self:
            approved = rec.ra_certificate_ids.filtered(lambda c: c.state in ("approved", "billed"))
            rec.certified_value = sum(approved.mapped("gross_work"))
            rec.advance_recovered = sum(approved.mapped("advance_recovery_amount"))
            rec.retention_held = sum(approved.mapped("retention_amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = self.env["ir.sequence"].next_by_code("construction.subcontract") or "New"
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = vals["code"]
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            if not rec.line_ids:
                raise UserError(_("Add at least one scope line before confirming."))
            rec.state = "confirmed"

    def action_close(self):
        self.filtered(lambda r: r.state == "confirmed").write({"state": "closed"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})


class ProjectProjectSubcontract(models.Model):
    _inherit = "project.project"

    subcontract_ids = fields.One2many("construction.subcontract", "project_id", string="Subcontracts")
    subcontract_count = fields.Integer(compute="_compute_subcontract_count")

    def _compute_subcontract_count(self):
        for rec in self:
            rec.subcontract_count = len(rec.subcontract_ids)


class ConstructionSubcontractLine(models.Model):
    _name = "construction.subcontract.line"
    _description = "Construction Subcontract Scope Line"
    _order = "sequence, id"

    subcontract_id = fields.Many2one("construction.subcontract", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line",
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one("product.product", string="Product / Service", required=True)
    description = fields.Char(required=True)
    uom_id = fields.Many2one("uom.uom", string="UoM")
    agreement_qty = fields.Float(string="Given Quantity", required=True)
    rate = fields.Float(string="Rate", required=True)
    value = fields.Monetary(compute="_compute_value", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="subcontract_id.currency_id", store=True)

    release_line_ids = fields.One2many("purchase.order.line", "construction_subcontract_line_id", string="Release PO Lines")
    released_qty = fields.Float(compute="_compute_released_qty", store=True)
    available_qty = fields.Float(compute="_compute_released_qty", store=True)
    measurement_line_ids = fields.One2many("construction.measurement.line", "subcontract_line_id", string="Measurement Lines")
    cumulative_certified_qty = fields.Float(compute="_compute_cumulative_certified_qty")

    @api.depends("agreement_qty", "rate")
    def _compute_value(self):
        for rec in self:
            rec.value = rec.agreement_qty * rec.rate

    @api.depends("release_line_ids.product_qty", "release_line_ids.state", "agreement_qty")
    def _compute_released_qty(self):
        for rec in self:
            confirmed = rec.release_line_ids.filtered(lambda l: l.state in ("purchase", "done"))
            rec.released_qty = sum(confirmed.mapped("product_qty"))
            rec.available_qty = rec.agreement_qty - rec.released_qty

    def _compute_cumulative_certified_qty(self):
        for rec in self:
            approved_lines = rec.measurement_line_ids.filtered(
                lambda l: l.measurement_id.state == "commercial_approved"
            )
            rec.cumulative_certified_qty = sum(approved_lines.mapped("measured_qty"))

    def action_release_po(self):
        self.ensure_one()
        if self.available_qty <= 0:
            raise UserError(_("No remaining quantity available to release on this scope line."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.subcontract.release.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_subcontract_line_id": self.id,
                "default_release_qty": self.available_qty,
            },
        }
