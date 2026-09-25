from odoo import _, api, fields, models
from odoo.exceptions import UserError

RA_STATE_SELECTION = [("draft", "Draft"), ("approved", "Approved"), ("billed", "Billed")]


class ConstructionRaCertificate(models.Model):
    _name = "construction.ra.certificate"
    _description = "Construction Subcontract RA Certificate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "certificate_date desc, id desc"

    name = fields.Char(default="New", copy=False)
    measurement_id = fields.Many2one("construction.measurement", required=True, ondelete="restrict")
    subcontract_id = fields.Many2one("construction.subcontract", required=True, ondelete="restrict", index=True)
    project_id = fields.Many2one(related="subcontract_id.project_id", store=True)
    currency_id = fields.Many2one(related="subcontract_id.currency_id", store=True)
    certificate_date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection(RA_STATE_SELECTION, default="draft", tracking=True, copy=False)

    gross_work = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    cumulative_work = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    retention_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    advance_recovery_amount = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    material_recovery_amount = fields.Monetary(default=0.0)
    penalty_amount = fields.Monetary(default=0.0)
    net_payable = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")

    vendor_bill_id = fields.Many2one("account.move", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.ra.certificate") or "New"
        return super().create(vals_list)

    @api.depends(
        "measurement_id.total_amount", "subcontract_id.retention_pct", "subcontract_id.advance_recovery_pct",
        "subcontract_id.advance_amount", "subcontract_id.advance_recovered", "material_recovery_amount", "penalty_amount",
    )
    def _compute_amounts(self):
        for rec in self:
            rec.gross_work = rec.measurement_id.total_amount
            prior_certs = rec.subcontract_id.ra_certificate_ids.filtered(
                lambda c: c.id != rec.id and c.state in ("approved", "billed")
                and (c.certificate_date, c.id) < (rec.certificate_date, rec.id)
            )
            rec.cumulative_work = sum(prior_certs.mapped("gross_work")) + rec.gross_work
            rec.retention_amount = rec.gross_work * (rec.subcontract_id.retention_pct or 0.0) / 100.0
            remaining_advance = (rec.subcontract_id.advance_amount or 0.0) - sum(prior_certs.mapped("advance_recovery_amount"))
            proposed_recovery = rec.gross_work * (rec.subcontract_id.advance_recovery_pct or 0.0) / 100.0
            rec.advance_recovery_amount = max(min(proposed_recovery, remaining_advance), 0.0)
            rec.net_payable = (
                rec.gross_work - rec.retention_amount - rec.advance_recovery_amount
                - rec.material_recovery_amount - rec.penalty_amount
            )

    def action_approve(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "approved"})

    def action_reset_to_draft(self):
        self.filtered(lambda r: r.state == "approved").write({"state": "draft"})

    def action_create_vendor_bill(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved RA Certificate can generate a vendor bill."))
        account = self.project_id.account_id
        move = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.subcontract_id.subcontractor_id.id,
            "invoice_date": self.certificate_date,
            "invoice_origin": self.name,
            "invoice_line_ids": [(0, 0, {
                "name": _("RA Certificate %(name)s - %(subcontract)s", name=self.name, subcontract=self.subcontract_id.name),
                "quantity": 1,
                "price_unit": self.net_payable,
                "analytic_distribution": {str(account.id): 100.0} if account else False,
            })],
        })
        self.write({"vendor_bill_id": move.id, "state": "billed"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }
