from odoo import _, api, fields, models
from odoo.exceptions import UserError

MR_STATE_SELECTION = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("site_approved", "Site Approved"),
    ("store_checked", "Store Checked"),
    ("procurement_approved", "Procurement Approved"),
    ("rfq_created", "RFQ/Transfer Created"),
    ("partially_fulfilled", "Partially Fulfilled"),
    ("fulfilled", "Fulfilled"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
]

OPERATION_SELECTION = [("consumption", "Consumption"), ("transfer", "Transfer")]
PRIORITY_SELECTION = [("0", "Normal"), ("1", "Urgent"), ("2", "Critical")]

# A request line counts toward the BOQ line's "requested" bucket while pending, and moves
# permanently into the "ordered" bucket once converted - so a line is always counted exactly once
# for its whole lifecycle and available-to-request never re-opens once material is committed.
_ACTIVE_MR_STATES = {s for s, _l in MR_STATE_SELECTION if s not in ("draft", "cancelled")}


class ConstructionMaterialRequest(models.Model):
    _name = "construction.material.request"
    _description = "Construction Material Requisition"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    code = fields.Char(copy=False, readonly=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    task_id = fields.Many2one("project.task", string="Task", domain="[('project_id', '=', project_id)]")
    request_by = fields.Many2one("res.users", default=lambda self: self.env.user, required=True)
    operation = fields.Selection(OPERATION_SELECTION, default="consumption", required=True, tracking=True)
    source_location_id = fields.Many2one("stock.location", string="Source Location")
    destination_location_id = fields.Many2one("stock.location", string="Destination Location")
    priority = fields.Selection(PRIORITY_SELECTION, default="0")
    required_date = fields.Date()
    state = fields.Selection(MR_STATE_SELECTION, default="draft", tracking=True, copy=False)
    line_ids = fields.One2many("construction.material.request.line", "request_id", string="Lines", copy=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = self.env["ir.sequence"].next_by_code("construction.material.request") or "New"
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = vals["code"]
        return super().create(vals_list)

    @api.constrains("operation", "destination_location_id")
    def _check_transfer_destination(self):
        for rec in self:
            if rec.operation == "transfer" and not rec.destination_location_id:
                raise UserError(_("A Destination Location is required for a Transfer request."))

    def action_submit(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            if not rec.line_ids:
                raise UserError(_("Add at least one line before submitting."))
            rec.state = "submitted"

    def action_site_approve(self):
        self.filtered(lambda r: r.state == "submitted").write({"state": "site_approved"})

    def action_store_check(self):
        self.filtered(lambda r: r.state == "site_approved").write({"state": "store_checked"})

    def action_procurement_approve(self):
        self.filtered(lambda r: r.state == "store_checked").write({"state": "procurement_approved"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_create_purchase_requisition(self):
        self.ensure_one()
        if self.state != "procurement_approved":
            raise UserError(_("Only a Procurement Approved request can generate a Purchase Requisition."))
        if self.operation != "consumption":
            raise UserError(_("Purchase Requisitions apply to Consumption requests. Use Create Transfer instead."))
        lines_to_convert = self.line_ids.filtered(lambda l: not l.purchase_line_id and not l.transfer_move_id)
        if not lines_to_convert:
            raise UserError(_("All lines are already converted."))
        requisition = self.env["purchase.requisition"].create({
            "reference": self.code,
            "requisition_type": "purchase_template",
            "company_id": (self.company_id or self.env.company).id,
            "line_ids": [(0, 0, {
                "product_id": line.product_id.id,
                "product_qty": line.requested_qty,
                "product_uom_id": line.uom_id.id,
                "construction_project_id": self.project_id.id,
                "construction_wbs_id": (line.wbs_id or self.wbs_id).id,
                "construction_boq_line_id": line.boq_line_id.id,
                "construction_material_request_line_id": line.id,
            }) for line in lines_to_convert],
        })
        lines_to_convert.write({"purchase_requisition_id": requisition.id})
        self.state = "rfq_created"
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.requisition",
            "res_id": requisition.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_transfer(self):
        self.ensure_one()
        if self.state not in ("procurement_approved", "store_checked"):
            raise UserError(_("Only a Store Checked / Procurement Approved request can generate a Transfer."))
        if self.operation != "transfer":
            raise UserError(_("Create Transfer applies to Transfer requests only."))
        if not self.source_location_id or not self.destination_location_id:
            raise UserError(_("Source and Destination Locations are required."))
        lines_to_convert = self.line_ids.filtered(lambda l: not l.purchase_line_id and not l.transfer_move_id)
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "internal"), ("warehouse_id.company_id", "=", self.company_id.id)], limit=1
        )
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id if picking_type else False,
            "location_id": self.source_location_id.id,
            "location_dest_id": self.destination_location_id.id,
            "origin": self.code,
            "move_ids": [(0, 0, {
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.requested_qty,
                "product_uom": line.uom_id.id,
                "location_id": self.source_location_id.id,
                "location_dest_id": self.destination_location_id.id,
            }) for line in lines_to_convert],
        })
        picking.action_confirm()
        for line, move in zip(lines_to_convert, picking.move_ids):
            line.transfer_move_id = move.id
        self.state = "rfq_created"
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "target": "current",
        }

    def check_fulfillment(self):
        """Re-derive state from lines' received quantities. Safe to call repeatedly (e.g. after a
        site receipt is validated in the inventory stage)."""
        for rec in self.filtered(lambda r: r.state in ("rfq_created", "partially_fulfilled")):
            if not rec.line_ids:
                continue
            fulfilled = all(l.received_qty >= l.requested_qty for l in rec.line_ids)
            any_received = any(l.received_qty > 0 for l in rec.line_ids)
            if fulfilled:
                rec.state = "fulfilled"
            elif any_received:
                rec.state = "partially_fulfilled"


class ConstructionMaterialRequestLine(models.Model):
    _name = "construction.material.request.line"
    _description = "Construction Material Requisition Line"
    _order = "sequence, id"

    request_id = fields.Many2one("construction.material.request", required=True, ondelete="cascade")
    state = fields.Selection(related="request_id.state", store=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one(related="request_id.project_id", store=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase")
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line", required=True,
        domain="[('project_id', '=', project_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one(related="boq_line_id.product_id", store=True, readonly=False)
    uom_id = fields.Many2one(related="boq_line_id.uom_id", store=True, readonly=False)
    requested_qty = fields.Float(required=True)
    available_to_request = fields.Float(related="boq_line_id.available_to_request", readonly=True)
    justification = fields.Char(help="Required when requested quantity exceeds the available allowance.")
    proposed_source = fields.Selection(
        [("internal_transfer", "Internal Transfer"), ("procurement", "New Procurement"), ("direct_delivery", "Direct Project Delivery")],
        default="procurement",
    )
    purchase_requisition_id = fields.Many2one("purchase.requisition", readonly=True, copy=False)
    purchase_line_id = fields.Many2one("purchase.order.line", readonly=True, copy=False)
    transfer_move_id = fields.Many2one("stock.move", readonly=True, copy=False)
    is_converted = fields.Boolean(compute="_compute_is_converted", store=True)
    received_qty = fields.Float(default=0.0, copy=False)

    @api.depends("purchase_line_id", "transfer_move_id")
    def _compute_is_converted(self):
        for rec in self:
            rec.is_converted = bool(rec.purchase_line_id or rec.transfer_move_id)

    @api.constrains("requested_qty", "boq_line_id", "justification")
    def _check_available_allowance(self):
        for rec in self:
            if rec.requested_qty > rec.boq_line_id.available_to_request and not rec.justification:
                raise UserError(_(
                    "Requested quantity for '%(name)s' (%(qty)s) exceeds the available allowance "
                    "(%(available)s). Provide a justification to proceed as an exception.",
                    name=rec.boq_line_id.name, qty=rec.requested_qty, available=rec.boq_line_id.available_to_request,
                ))

    @api.onchange("boq_line_id")
    def _onchange_boq_line_id(self):
        if self.boq_line_id and not self.wbs_id:
            self.wbs_id = self.boq_line_id.wbs_id


class ProjectTaskMaterialRequest(models.Model):
    _inherit = "project.task"

    material_request_ids = fields.One2many("construction.material.request", "task_id", string="Material Requests")
    material_request_count = fields.Integer(compute="_compute_material_request_count")

    def _compute_material_request_count(self):
        for rec in self:
            rec.material_request_count = len(rec.material_request_ids)

    def action_create_material_request(self):
        self.ensure_one()
        request = self.env["construction.material.request"].create({
            "project_id": self.project_id.id,
            "wbs_id": self.wbs_id.id,
            "task_id": self.id,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.material.request",
            "res_id": request.id,
            "view_mode": "form",
            "target": "current",
        }


class ConstructionBoqLineProcurement(models.Model):
    _inherit = "construction.boq.line"

    material_request_line_ids = fields.One2many("construction.material.request.line", "boq_line_id")
    requested_qty = fields.Float(compute="_compute_requested_ordered", store=True)
    ordered_qty = fields.Float(compute="_compute_requested_ordered", store=True)

    @api.depends(
        "material_request_line_ids.requested_qty",
        "material_request_line_ids.is_converted",
        "material_request_line_ids.state",
    )
    def _compute_requested_ordered(self):
        for rec in self:
            active_lines = rec.material_request_line_ids.filtered(lambda l: l.state in _ACTIVE_MR_STATES)
            rec.requested_qty = sum(active_lines.filtered(lambda l: not l.is_converted).mapped("requested_qty"))
            rec.ordered_qty = sum(active_lines.filtered(lambda l: l.is_converted).mapped("requested_qty"))
