from odoo import _, api, fields, models
from odoo.exceptions import UserError

PROGRESS_CERT_STATE_SELECTION = [
    ("draft", "Draft"),
    ("approved", "Approved"),
    ("invoiced", "Invoiced"),
]


class ProjectProjectWip(models.Model):
    """Lightweight project.project rollups needed for correct @api.depends tracking on
    construction.progress.certificate (Odoo cannot depend on a raw search()/unrelated model
    directly - the standard workaround, also used by construction.ra.certificate against
    construction.subcontract, is to expose the aggregate as a stored compute on the parent and
    depend on that). Added here rather than in models/project_ext.py - which this build does not
    own - mirroring the existing convention of models/subcontract/subcontract.py adding its own
    project.project rollups (subcontract_ids/subcontract_count) from its own file."""

    _inherit = "project.project"

    variation_ids = fields.One2many("construction.variation", "project_id", string="Variations")
    total_approved_variation_revenue = fields.Monetary(
        compute="_compute_total_approved_variation_revenue", store=True, currency_field="currency_id")

    progress_certificate_ids = fields.One2many("construction.progress.certificate", "project_id", string="Progress Certificates")
    progress_certificate_count = fields.Integer(compute="_compute_progress_certificate_count")
    total_advance_recovered = fields.Monetary(
        compute="_compute_progress_certificate_rollup", store=True, currency_field="currency_id",
        help="Aggregate of all Approved/Invoiced certificates' advance_recovery; exists purely so "
             "each certificate's own advance_recovery compute can depend on its siblings' state "
             "changing (see construction.progress.certificate._compute_amounts).")

    wip_period_ids = fields.One2many("construction.wip.period", "project_id", string="WIP Periods")
    wip_period_count = fields.Integer(compute="_compute_wip_period_count")

    @api.depends("variation_ids.state", "variation_ids.total_revenue_effect")
    def _compute_total_approved_variation_revenue(self):
        for rec in self:
            approved = rec.variation_ids.filtered(lambda v: v.state == "approved")
            rec.total_approved_variation_revenue = sum(approved.mapped("total_revenue_effect"))

    def _compute_progress_certificate_count(self):
        for rec in self:
            rec.progress_certificate_count = len(rec.progress_certificate_ids)

    @api.depends("progress_certificate_ids.state", "progress_certificate_ids.advance_recovery")
    def _compute_progress_certificate_rollup(self):
        for rec in self:
            approved = rec.progress_certificate_ids.filtered(lambda c: c.state in ("approved", "invoiced"))
            rec.total_advance_recovered = sum(approved.mapped("advance_recovery"))

    def _compute_wip_period_count(self):
        for rec in self:
            rec.wip_period_count = len(rec.wip_period_ids)


class ConstructionProgressCertificate(models.Model):
    _name = "construction.progress.certificate"
    _description = "Construction Customer Progress Certificate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "certificate_date desc, id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)
    certificate_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    state = fields.Selection(PROGRESS_CERT_STATE_SELECTION, default="draft", tracking=True, copy=False)

    original_contract = fields.Monetary(related="project_id.original_contract_value", store=True, currency_field="currency_id")
    approved_variations = fields.Monetary(related="project_id.total_approved_variation_revenue", store=True, currency_field="currency_id")
    revised_contract = fields.Monetary(compute="_compute_revised_contract", store=True, currency_field="currency_id")

    line_ids = fields.One2many("construction.progress.certificate.line", "certificate_id", string="Lines", copy=True)
    current_work = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id",
                                    help="This certificate's certified quantity x customer rate, summed from lines.")
    stored_material = fields.Monetary(string="Stored / On-Site Material", default=0.0,
                                       help="Approved on-site material eligible for billing but not yet incorporated into measured work.")
    retention_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    # project.project has no advance-recovery rate (only advance_amount); mirroring
    # construction.subcontract.advance_recovery_pct, added here as a per-certificate override
    # rather than duplicating a company/project-wide setting.
    advance_recovery_pct = fields.Float(string="Advance Recovery % per Certificate", default=20.0)
    advance_recovery = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    deductions = fields.Monetary(string="Other Deductions", default=0.0)
    net_certificate = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")

    customer_invoice_id = fields.Many2one("account.move", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.progress.certificate") or "New"
        return super().create(vals_list)

    @api.depends("original_contract", "approved_variations")
    def _compute_revised_contract(self):
        for rec in self:
            rec.revised_contract = (rec.original_contract or 0.0) + (rec.approved_variations or 0.0)

    @api.depends(
        "line_ids.amount", "stored_material", "project_id.retention_pct", "project_id.advance_amount",
        "advance_recovery_pct", "deductions", "certificate_date",
        "project_id.total_advance_recovered",
    )
    def _compute_amounts(self):
        for rec in self:
            rec.current_work = sum(rec.line_ids.mapped("amount"))
            gross = rec.current_work
            rec.retention_amount = gross * (rec.project_id.retention_pct or 0.0) / 100.0
            prior_certs = rec.project_id.progress_certificate_ids.filtered(
                lambda c: c.id != rec.id and c.state in ("approved", "invoiced")
                and (c.certificate_date, c.id) < (rec.certificate_date, rec.id)
            )
            remaining_advance = (rec.project_id.advance_amount or 0.0) - sum(prior_certs.mapped("advance_recovery"))
            proposed_recovery = gross * (rec.advance_recovery_pct or 0.0) / 100.0
            rec.advance_recovery = max(min(proposed_recovery, remaining_advance), 0.0)
            rec.net_certificate = (
                gross + rec.stored_material - rec.retention_amount - rec.advance_recovery - rec.deductions
            )

    def action_approve(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            rec.state = "approved"
            rec.line_ids.mapped("boq_line_id.wbs_id").recompute_physical_progress_from_boq()

    def action_reset_to_draft(self):
        self.filtered(lambda r: r.state == "approved").write({"state": "draft"})

    def action_create_invoice(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved Progress Certificate can generate a customer invoice."))
        company = self.project_id.company_id or self.env.company
        account = self.project_id.account_id
        billing_account = company.construction_progress_billing_account_id
        line_vals = {
            "name": _("Progress Certificate %(name)s - %(project)s", name=self.name, project=self.project_id.name),
            "quantity": 1,
            "price_unit": self.net_certificate,
            "analytic_distribution": {str(account.id): 100.0} if account else False,
        }
        # Route to the Progress Billing (contract liability/asset) control account, when
        # configured, instead of the product/company default income account: the WIP period's
        # own revenue-recognition journal entry (models/wip/wip_period.py action_post) already
        # credits Contract Revenue against this same account, so posting the customer invoice
        # straight to a P&L revenue account would double-recognize revenue. This is a deliberate
        # departure from a literal mirror of construction.ra.certificate.action_create_vendor_bill
        # (which has no equivalent account to redirect to) - see build report point 7.
        if billing_account:
            line_vals["account_id"] = billing_account.id
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.project_id.partner_id.id,
            "invoice_date": self.certificate_date,
            "invoice_origin": self.name,
            "invoice_line_ids": [(0, 0, line_vals)],
        })
        self.write({"customer_invoice_id": move.id, "state": "invoiced"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }


class ConstructionProgressCertificateLine(models.Model):
    _name = "construction.progress.certificate.line"
    _description = "Construction Progress Certificate Line"
    _order = "sequence, id"

    certificate_id = fields.Many2one("construction.progress.certificate", required=True, ondelete="cascade")
    state = fields.Selection(related="certificate_id.state", store=True)
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    certified_qty = fields.Float(string="Certified Qty (this certificate)", required=True)
    rate = fields.Float(related="boq_line_id.customer_rate", string="Customer Rate")
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="certificate_id.currency_id", store=True)

    @api.depends("certified_qty", "rate")
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.certified_qty * rec.rate

    @api.onchange("boq_line_id")
    def _onchange_boq_line_id(self):
        if self.boq_line_id:
            remaining = self.boq_line_id.revised_net_qty - self.boq_line_id.certified_qty
            self.certified_qty = max(remaining, 0.0)


class ConstructionBoqLineCertified(models.Model):
    """certified_qty was a plain Float 'control quantity' on construction.boq.line (Stage 2/3)
    with no owner yet (grep confirmed no other model computes/writes it) - turned into a stored
    compute here, summing this project's own Approved/Invoiced Progress Certificate lines, using
    the exact same pattern as consumed_qty in models/inventory/material_consumption.py."""

    _inherit = "construction.boq.line"

    progress_certificate_line_ids = fields.One2many("construction.progress.certificate.line", "boq_line_id")
    certified_qty = fields.Float(compute="_compute_certified_qty", store=True)

    @api.depends("progress_certificate_line_ids.certified_qty", "progress_certificate_line_ids.state")
    def _compute_certified_qty(self):
        for rec in self:
            approved = rec.progress_certificate_line_ids.filtered(lambda l: l.state in ("approved", "invoiced"))
            rec.certified_qty = sum(approved.mapped("certified_qty"))
