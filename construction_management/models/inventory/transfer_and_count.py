from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ConstructionInterProjectTransfer(models.Model):
    _name = "construction.inter.project.transfer"
    _description = "Construction Inter-Project Stock Transfer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    source_project_id = fields.Many2one("project.project", string="Sending Project", required=True)
    destination_project_id = fields.Many2one("project.project", string="Receiving Project", required=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("source_approved", "Source Approved"), ("destination_approved", "Destination Approved"), ("confirmed", "Confirmed")],
        default="draft", tracking=True, copy=False,
    )
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    line_ids = fields.One2many("construction.inter.project.transfer.line", "transfer_id", string="Lines", copy=True)
    company_id = fields.Many2one(related="source_project_id.company_id", store=True)

    @api.constrains("source_project_id", "destination_project_id")
    def _check_different_projects(self):
        for rec in self:
            if rec.source_project_id == rec.destination_project_id:
                raise UserError(_("Source and destination projects must be different."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.inter.project.transfer") or "New"
        return super().create(vals_list)

    def action_source_approve(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "source_approved"})

    def action_destination_approve(self):
        for rec in self.filtered(lambda r: r.state == "source_approved"):
            rec.state = "destination_approved"
            rec._do_transfer()

    def _do_transfer(self):
        self.ensure_one()
        for project in (self.source_project_id, self.destination_project_id):
            if not project.accepted_location_id:
                project.action_setup_stock_locations()
        lines = self.line_ids.filtered(lambda l: l.qty > 0)
        if not lines:
            raise UserError(_("At least one line needs a quantity."))
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "internal"), ("warehouse_id.company_id", "=", (self.company_id or self.env.company).id)], limit=1
        )
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id if picking_type else False,
            "location_id": self.source_project_id.accepted_location_id.id,
            "location_dest_id": self.destination_project_id.accepted_location_id.id,
            "origin": self.name,
            "move_ids": [(0, 0, {
                "product_id": line.product_id.id,
                "product_uom_qty": line.qty,
                "product_uom": line.uom_id.id or line.product_id.uom_id.id,
                "location_id": self.source_project_id.accepted_location_id.id,
                "location_dest_id": self.destination_project_id.accepted_location_id.id,
            }) for line in lines],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking._action_done()
        self.write({"picking_id": picking.id, "state": "confirmed"})


class ConstructionInterProjectTransferLine(models.Model):
    _name = "construction.inter.project.transfer.line"
    _description = "Construction Inter-Project Transfer Line"
    _order = "sequence, id"

    transfer_id = fields.Many2one("construction.inter.project.transfer", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", required=True)
    uom_id = fields.Many2one("uom.uom", string="UoM")
    qty = fields.Float(required=True)


# -------------------------------------------------------------------------------------------


class ConstructionCycleCount(models.Model):
    _name = "construction.cycle.count"
    _description = "Construction Site Cycle Count"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    location_id = fields.Many2one(
        "stock.location", required=True,
        domain="[('id', 'in', (project_accepted_location_id, project_issued_location_id))]",
    )
    project_accepted_location_id = fields.Many2one(related="project_id.accepted_location_id")
    project_issued_location_id = fields.Many2one(related="project_id.issued_location_id")
    date = fields.Date(default=fields.Date.context_today, required=True)
    counted_by = fields.Many2one("res.users", default=lambda self: self.env.user)
    approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    state = fields.Selection([("draft", "Draft"), ("approved", "Approved")], default="draft", tracking=True, copy=False)
    line_ids = fields.One2many("construction.cycle.count.line", "count_id", string="Lines", copy=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.cycle.count") or "New"
        return super().create(vals_list)

    def action_approve(self):
        """Independent-approver control: the user approving a count must not be the one who
        counted it."""
        for rec in self.filtered(lambda r: r.state == "draft"):
            if rec.counted_by == self.env.user:
                raise UserError(_("The counter cannot also approve their own cycle count."))
            for line in rec.line_ids:
                quant = self.env["stock.quant"].search([
                    ("product_id", "=", line.product_id.id), ("location_id", "=", rec.location_id.id),
                ], limit=1)
                if quant:
                    quant.inventory_quantity = line.counted_qty
                    quant.action_apply_inventory()
                elif line.counted_qty:
                    new_quant = self.env["stock.quant"].create({
                        "product_id": line.product_id.id, "location_id": rec.location_id.id,
                        "inventory_quantity": line.counted_qty,
                    })
                    new_quant.action_apply_inventory()
            rec.write({"state": "approved", "approved_by": self.env.user.id})


class ConstructionCycleCountLine(models.Model):
    _name = "construction.cycle.count.line"
    _description = "Construction Cycle Count Line"
    _order = "sequence, id"

    count_id = fields.Many2one("construction.cycle.count", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", required=True)
    system_qty = fields.Float(compute="_compute_system_qty")
    counted_qty = fields.Float(required=True)
    variance = fields.Float(compute="_compute_variance")
    reason = fields.Char()

    def _compute_system_qty(self):
        for rec in self:
            quant = self.env["stock.quant"].search([
                ("product_id", "=", rec.product_id.id), ("location_id", "=", rec.count_id.location_id.id),
            ], limit=1)
            rec.system_qty = quant.quantity if quant else 0.0

    @api.depends("counted_qty", "product_id")
    def _compute_variance(self):
        for rec in self:
            rec.variance = rec.counted_qty - rec.system_qty

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.counted_qty = self.system_qty
