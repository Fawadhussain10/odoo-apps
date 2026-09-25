from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ConstructionSiteReceipt(models.Model):
    _name = "construction.site.receipt"
    _description = "Construction Site Receipt"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    purchase_order_id = fields.Many2one("purchase.order", string="Purchase Order")
    date = fields.Date(default=fields.Date.context_today, required=True)
    challan_ref = fields.Char(string="Challan / Delivery Note")
    vehicle_no = fields.Char()
    inspector_id = fields.Many2one("res.users", string="Inspector")
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed")], default="draft", tracking=True, copy=False)
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    line_ids = fields.One2many("construction.site.receipt.line", "receipt_id", string="Lines", copy=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.site.receipt") or "New"
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            if not rec.project_id.accepted_location_id:
                rec.project_id.action_setup_stock_locations()
            lines_with_qty = rec.line_ids.filtered(lambda l: l.accepted_qty > 0)
            if not lines_with_qty:
                raise UserError(_("At least one line needs an accepted quantity to confirm."))
            picking = self.env["stock.picking"].create({
                "picking_type_id": self.env.ref("stock.picking_type_in").id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": rec.project_id.accepted_location_id.id,
                "origin": rec.name,
                "move_ids": [(0, 0, {
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.accepted_qty,
                    "product_uom": line.uom_id.id or line.product_id.uom_id.id,
                    "location_id": self.env.ref("stock.stock_location_suppliers").id,
                    "location_dest_id": rec.project_id.accepted_location_id.id,
                }) for line in lines_with_qty],
            })
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking._action_done()
            rec.write({"picking_id": picking.id, "state": "confirmed"})
            affected_mrlines = lines_with_qty.mapped("po_line_id.construction_material_request_line_id")
            affected_mrlines._refresh_received_qty()
            affected_mrlines.mapped("request_id").check_fulfillment()


class ConstructionSiteReceiptLine(models.Model):
    _name = "construction.site.receipt.line"
    _description = "Construction Site Receipt Line"
    _order = "sequence, id"

    receipt_id = fields.Many2one("construction.site.receipt", required=True, ondelete="cascade")
    state = fields.Selection(related="receipt_id.state", store=True)
    sequence = fields.Integer(default=10)
    po_line_id = fields.Many2one("purchase.order.line", string="PO Line")
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line",
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one("product.product", required=True)
    uom_id = fields.Many2one("uom.uom", string="UoM")
    ordered_qty = fields.Float(related="po_line_id.product_qty", readonly=True)
    accepted_qty = fields.Float(default=0.0)
    rejected_qty = fields.Float(default=0.0)
    rejection_reason = fields.Char()

    @api.onchange("po_line_id")
    def _onchange_po_line_id(self):
        if self.po_line_id:
            self.product_id = self.po_line_id.product_id
            self.uom_id = self.po_line_id.product_uom_id
            self.boq_line_id = self.po_line_id.construction_boq_line_id
            self.accepted_qty = self.po_line_id.product_qty


class ConstructionBoqLineReceived(models.Model):
    _inherit = "construction.boq.line"

    site_receipt_line_ids = fields.One2many("construction.site.receipt.line", "boq_line_id")
    received_qty = fields.Float(compute="_compute_received_qty", store=True)

    @api.depends("site_receipt_line_ids.accepted_qty", "site_receipt_line_ids.state")
    def _compute_received_qty(self):
        for rec in self:
            confirmed = rec.site_receipt_line_ids.filtered(lambda l: l.state == "confirmed")
            rec.received_qty = sum(confirmed.mapped("accepted_qty"))


class ConstructionMaterialRequestLineReceived(models.Model):
    """`received_qty` stays a plain stored field (declared in Stage 3's material_request.py) -
    it's refreshed imperatively by ConstructionSiteReceipt.action_confirm() below, since it only
    ever changes at that one triggering event and a reactive compute would need a search-based
    pseudo-relation Odoo can't track dependencies through anyway."""
    _inherit = "construction.material.request.line"

    def _refresh_received_qty(self):
        for rec in self.filtered("purchase_line_id"):
            confirmed_lines = self.env["construction.site.receipt.line"].search([
                ("po_line_id", "=", rec.purchase_line_id.id), ("state", "=", "confirmed"),
            ])
            rec.received_qty = sum(confirmed_lines.mapped("accepted_qty"))
