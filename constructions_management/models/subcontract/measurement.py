from odoo import _, api, fields, models
from odoo.exceptions import UserError

MEASUREMENT_STATE_SELECTION = [
    ("draft", "Draft Measurement"),
    ("site_engineer", "Site Engineer Verified"),
    ("qs", "Quantity Surveyor Verified"),
    ("pm", "Project Manager Verified"),
    ("commercial_approved", "Commercial Approved"),
]


class ConstructionMeasurement(models.Model):
    _name = "construction.measurement"
    _description = "Construction Subcontract Measurement Sheet"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "measurement_date desc, id desc"

    name = fields.Char(default="New", copy=False)
    subcontract_id = fields.Many2one("construction.subcontract", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="subcontract_id.project_id", store=True)
    currency_id = fields.Many2one(related="subcontract_id.currency_id", store=True)
    measurement_date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection(MEASUREMENT_STATE_SELECTION, default="draft", tracking=True, copy=False)
    line_ids = fields.One2many("construction.measurement.line", "measurement_id", string="Lines", copy=True)
    total_amount = fields.Monetary(compute="_compute_total_amount", store=True, currency_field="currency_id")
    ra_certificate_id = fields.Many2one("construction.ra.certificate", readonly=True, copy=False)

    _sql_no_duplicate_period = models.Constraint(
        "unique(subcontract_id, measurement_date)",
        "A measurement for this subcontract already exists on this date.",
    )

    @api.depends("line_ids.amount")
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped("amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.measurement") or "New"
        return super().create(vals_list)

    def action_site_engineer_verify(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "site_engineer"})

    def action_qs_verify(self):
        self.filtered(lambda r: r.state == "site_engineer").write({"state": "qs"})

    def action_pm_verify(self):
        self.filtered(lambda r: r.state == "qs").write({"state": "pm"})

    def action_commercial_approve(self):
        for rec in self.filtered(lambda r: r.state == "pm"):
            for line in rec.line_ids:
                if line.cumulative_qty_after > line.subcontract_line_id.agreement_qty:
                    raise UserError(_(
                        "Cumulative certified quantity for '%(desc)s' (%(cum)s) would exceed the agreement "
                        "quantity (%(agreed)s). Increase the subcontract scope line quantity first (amendment).",
                        desc=line.subcontract_line_id.description, cum=line.cumulative_qty_after,
                        agreed=line.subcontract_line_id.agreement_qty,
                    ))
            rec.state = "commercial_approved"

    def action_reset_to_draft(self):
        self.filtered(lambda r: not r.ra_certificate_id).write({"state": "draft"})

    def action_create_ra_certificate(self):
        self.ensure_one()
        if self.state != "commercial_approved":
            raise UserError(_("Only a commercially approved measurement can generate an RA Certificate."))
        if self.ra_certificate_id:
            raise UserError(_("An RA Certificate already exists for this measurement."))
        certificate = self.env["construction.ra.certificate"].create({
            "measurement_id": self.id,
            "subcontract_id": self.subcontract_id.id,
        })
        self.ra_certificate_id = certificate.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.ra.certificate",
            "res_id": certificate.id,
            "view_mode": "form",
            "target": "current",
        }


class ConstructionMeasurementLine(models.Model):
    _name = "construction.measurement.line"
    _description = "Construction Measurement Line"
    _order = "sequence, id"

    measurement_id = fields.Many2one("construction.measurement", required=True, ondelete="cascade")
    state = fields.Selection(related="measurement_id.state", store=True)
    sequence = fields.Integer(default=10)
    subcontract_line_id = fields.Many2one(
        "construction.subcontract.line", string="Scope Line", required=True,
        domain="[('subcontract_id', '=', parent.subcontract_id)]",
    )
    rate = fields.Float(related="subcontract_line_id.rate", readonly=True)
    measured_qty = fields.Float(string="Measured Qty (This Period)", required=True)
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="measurement_id.currency_id", store=True)
    previous_cumulative_qty = fields.Float(compute="_compute_cumulative")
    cumulative_qty_after = fields.Float(compute="_compute_cumulative")

    @api.depends("measured_qty", "rate")
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.measured_qty * rec.rate

    def _compute_cumulative(self):
        for rec in self:
            prior = rec.subcontract_line_id.measurement_line_ids.filtered(
                lambda l: l.id != rec.id and l.measurement_id.state == "commercial_approved"
                and (l.measurement_id.measurement_date, l.id) < (rec.measurement_id.measurement_date, rec.id)
            )
            rec.previous_cumulative_qty = sum(prior.mapped("measured_qty"))
            rec.cumulative_qty_after = rec.previous_cumulative_qty + rec.measured_qty

    @api.onchange("subcontract_line_id")
    def _onchange_subcontract_line_id(self):
        if self.subcontract_line_id:
            remaining = self.subcontract_line_id.agreement_qty - self.subcontract_line_id.cumulative_certified_qty
            self.measured_qty = max(remaining, 0.0)
