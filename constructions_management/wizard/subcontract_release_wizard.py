from odoo import _, fields, models
from odoo.exceptions import UserError


class ConstructionSubcontractReleaseWizard(models.TransientModel):
    _name = "construction.subcontract.release.wizard"
    _description = "Release a Purchase Order Against a Subcontract Scope Line"

    subcontract_line_id = fields.Many2one("construction.subcontract.line", required=True)
    release_qty = fields.Float(required=True)
    vendor_id = fields.Many2one(
        "res.partner", string="Vendor",
        default=lambda self: self.subcontract_line_id.subcontract_id.subcontractor_id,
    )

    def action_release(self):
        self.ensure_one()
        line = self.subcontract_line_id
        if self.release_qty <= 0 or self.release_qty > line.available_qty:
            raise UserError(_("Release quantity must be between 0 and the available quantity (%s).", line.available_qty))
        account = line.subcontract_id.project_id.account_id
        po = self.env["purchase.order"].create({
            "partner_id": self.vendor_id.id,
            "origin": line.subcontract_id.code,
            "order_line": [(0, 0, {
                "product_id": line.product_id.id,
                "name": line.description,
                "product_qty": self.release_qty,
                "product_uom_id": line.uom_id.id or line.product_id.uom_id.id,
                "price_unit": line.rate,
                "construction_project_id": line.subcontract_id.project_id.id,
                "construction_wbs_id": line.subcontract_id.wbs_id.id,
                "construction_boq_line_id": line.boq_line_id.id,
                "construction_subcontract_line_id": line.id,
                "analytic_distribution": {str(account.id): 100.0} if account else False,
            })],
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
            "target": "current",
        }
