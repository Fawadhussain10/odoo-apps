from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ConstructionMaterialIssue(models.Model):
    _name = "construction.material.issue"
    _description = "Construction Material Issue (Accepted -> Work Area)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    issued_to = fields.Many2one("res.users", string="Issued To (Foreman)")
    date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed")], default="draft", tracking=True, copy=False)
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    line_ids = fields.One2many("construction.material.issue.line", "issue_id", string="Lines", copy=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.material.issue") or "New"
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            if not rec.project_id.accepted_location_id:
                rec.project_id.action_setup_stock_locations()
            lines = rec.line_ids.filtered(lambda l: l.issued_qty > 0)
            if not lines:
                raise UserError(_("At least one line needs a quantity to confirm."))
            picking_type = self.env["stock.picking.type"].search(
                [("code", "=", "internal"), ("warehouse_id.company_id", "=", (rec.company_id or rec.env.company).id)], limit=1
            )
            picking = self.env["stock.picking"].create({
                "picking_type_id": picking_type.id if picking_type else False,
                "location_id": rec.project_id.accepted_location_id.id,
                "location_dest_id": rec.project_id.issued_location_id.id,
                "origin": rec.name,
                "move_ids": [(0, 0, {
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.issued_qty,
                    "product_uom": line.uom_id.id or line.product_id.uom_id.id,
                    "location_id": rec.project_id.accepted_location_id.id,
                    "location_dest_id": rec.project_id.issued_location_id.id,
                }) for line in lines],
            })
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking._action_done()
            rec.write({"picking_id": picking.id, "state": "confirmed"})


class ConstructionMaterialIssueLine(models.Model):
    _name = "construction.material.issue.line"
    _description = "Construction Material Issue Line"
    _order = "sequence, id"

    issue_id = fields.Many2one("construction.material.issue", required=True, ondelete="cascade")
    state = fields.Selection(related="issue_id.state", store=True)
    sequence = fields.Integer(default=10)
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', parent.project_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one(related="boq_line_id.product_id", store=True, readonly=False)
    uom_id = fields.Many2one(related="boq_line_id.uom_id", store=True, readonly=False)
    issued_qty = fields.Float(required=True)


class ConstructionBoqLineIssued(models.Model):
    _inherit = "construction.boq.line"

    material_issue_line_ids = fields.One2many("construction.material.issue.line", "boq_line_id")
    issued_qty = fields.Float(compute="_compute_issued_qty", store=True)

    @api.depends("material_issue_line_ids.issued_qty", "material_issue_line_ids.state")
    def _compute_issued_qty(self):
        for rec in self:
            confirmed = rec.material_issue_line_ids.filtered(lambda l: l.state == "confirmed")
            rec.issued_qty = sum(confirmed.mapped("issued_qty"))
