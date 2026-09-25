from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ConstructionMaterialReturn(models.Model):
    _name = "construction.material.return"
    _description = "Construction Material Return (Work Area -> Return)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    date = fields.Date(default=fields.Date.context_today, required=True)
    reason = fields.Char()
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed")], default="draft", tracking=True, copy=False)
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    line_ids = fields.One2many("construction.material.return.line", "return_id", string="Lines", copy=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.material.return") or "New"
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            lines = rec.line_ids.filtered(lambda l: l.returned_qty > 0)
            if not lines:
                raise UserError(_("At least one line needs a quantity to confirm."))
            picking_type = self.env["stock.picking.type"].search(
                [("code", "=", "internal"), ("warehouse_id.company_id", "=", (rec.company_id or rec.env.company).id)], limit=1
            )
            picking = self.env["stock.picking"].create({
                "picking_type_id": picking_type.id if picking_type else False,
                "location_id": rec.project_id.issued_location_id.id,
                "location_dest_id": rec.project_id.return_location_id.id,
                "origin": rec.name,
                "move_ids": [(0, 0, {
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.returned_qty,
                    "product_uom": line.uom_id.id or line.product_id.uom_id.id,
                    "location_id": rec.project_id.issued_location_id.id,
                    "location_dest_id": rec.project_id.return_location_id.id,
                }) for line in lines],
            })
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking._action_done()
            rec.write({"picking_id": picking.id, "state": "confirmed"})


class ConstructionMaterialReturnLine(models.Model):
    _name = "construction.material.return.line"
    _description = "Construction Material Return Line"
    _order = "sequence, id"

    return_id = fields.Many2one("construction.material.return", required=True, ondelete="cascade")
    state = fields.Selection(related="return_id.state", store=True)
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one(related="boq_line_id.product_id", store=True, readonly=False)
    uom_id = fields.Many2one(related="boq_line_id.uom_id", store=True, readonly=False)
    returned_qty = fields.Float(required=True)


# -------------------------------------------------------------------------------------------

WASTAGE_APPROVAL_THRESHOLD_PCT = 5.0  # wastage beyond the BOQ line's own budgeted waste % needs approval


class ConstructionMaterialWastage(models.Model):
    _name = "construction.material.wastage"
    _description = "Construction Material Wastage / Scrap"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("pending_approval", "Pending Approval"), ("approved", "Approved")],
        default="draft", tracking=True, copy=False,
    )
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    line_ids = fields.One2many("construction.material.wastage.line", "wastage_id", string="Lines", copy=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    requires_approval = fields.Boolean(compute="_compute_requires_approval")

    @api.depends("line_ids.wasted_qty", "line_ids.boq_line_id")
    def _compute_requires_approval(self):
        for rec in self:
            rec.requires_approval = any(
                line.boq_line_id.net_qty
                and (line.wasted_qty / line.boq_line_id.net_qty * 100.0) > (line.boq_line_id.waste_pct + WASTAGE_APPROVAL_THRESHOLD_PCT)
                for line in rec.line_ids
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.material.wastage") or "New"
        return super().create(vals_list)

    def action_submit(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            rec.state = "pending_approval" if rec.requires_approval else "approved"
            if rec.state == "approved":
                rec._do_scrap_move()

    def action_approve(self):
        for rec in self.filtered(lambda r: r.state == "pending_approval"):
            rec.state = "approved"
            rec._do_scrap_move()

    def _do_scrap_move(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.wasted_qty > 0)
        if not lines:
            raise UserError(_("At least one line needs a quantity."))
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "internal"), ("warehouse_id.company_id", "=", (self.company_id or self.env.company).id)], limit=1
        )
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id if picking_type else False,
            "location_id": self.project_id.issued_location_id.id,
            "location_dest_id": self.project_id.scrap_location_id.id,
            "origin": self.name,
            "move_ids": [(0, 0, {
                "product_id": line.product_id.id,
                "product_uom_qty": line.wasted_qty,
                "product_uom": line.uom_id.id or line.product_id.uom_id.id,
                "location_id": self.project_id.issued_location_id.id,
                "location_dest_id": self.project_id.scrap_location_id.id,
            }) for line in lines],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking._action_done()
        self.picking_id = picking.id


class ConstructionMaterialWastageLine(models.Model):
    _name = "construction.material.wastage.line"
    _description = "Construction Material Wastage Line"
    _order = "sequence, id"

    wastage_id = fields.Many2one("construction.material.wastage", required=True, ondelete="cascade")
    state = fields.Selection(related="wastage_id.state", store=True)
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one(related="boq_line_id.product_id", store=True, readonly=False)
    uom_id = fields.Many2one(related="boq_line_id.uom_id", store=True, readonly=False)
    wasted_qty = fields.Float(required=True)
    reason = fields.Char(required=True)
