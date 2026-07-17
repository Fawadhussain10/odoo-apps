from odoo import api, fields, models


class PurchaseRequisitionLine(models.Model):
    _inherit = "purchase.requisition.line"

    construction_project_id = fields.Many2one("project.project", string="Project")
    construction_wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase")
    construction_boq_line_id = fields.Many2one("construction.boq.line", string="BOQ Line")
    construction_material_request_line_id = fields.Many2one("construction.material.request.line", string="Material Request Line")

    @api.onchange("construction_boq_line_id")
    def _onchange_construction_boq_line_id(self):
        if self.construction_boq_line_id:
            boq_line = self.construction_boq_line_id
            self.construction_project_id = boq_line.project_id
            self.construction_wbs_id = boq_line.wbs_id
            if not self.product_id:
                self.product_id = boq_line.product_id
            if boq_line.project_id.account_id:
                self.analytic_distribution = {str(boq_line.project_id.account_id.id): 100.0}


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    construction_project_id = fields.Many2one("project.project", string="Project")
    construction_wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', construction_project_id)]")
    construction_boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line",
        domain="[('project_id', '=', construction_project_id), ('display_type', '=', False)]",
    )
    construction_material_request_line_id = fields.Many2one("construction.material.request.line", string="Material Request Line", copy=False)
    construction_subcontract_line_id = fields.Many2one("construction.subcontract.line", string="Subcontract Scope Line", copy=False)

    @api.onchange("construction_boq_line_id")
    def _onchange_construction_boq_line_id(self):
        if self.construction_boq_line_id:
            boq_line = self.construction_boq_line_id
            self.construction_project_id = boq_line.project_id
            self.construction_wbs_id = boq_line.wbs_id
            if boq_line.project_id.account_id:
                self.analytic_distribution = {str(boq_line.project_id.account_id.id): 100.0}

    @api.onchange("product_id")
    def _onchange_product_id_construction_requisition_match(self):
        """When the PO is generated against a Purchase Requisition, mirror that requisition
        line's construction linkage onto this PO line by matching the product - the same
        matching approach purchase_requisition itself uses to copy price/description."""
        if self.product_id and self.order_id.requisition_id:
            req_line = self.order_id.requisition_id.line_ids.filtered(
                lambda l: l.product_id == self.product_id and l.construction_boq_line_id
            )[:1]
            if req_line:
                self.construction_project_id = req_line.construction_project_id
                self.construction_wbs_id = req_line.construction_wbs_id
                self.construction_boq_line_id = req_line.construction_boq_line_id
                self.construction_material_request_line_id = req_line.construction_material_request_line_id

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if not line.construction_material_request_line_id and line.order_id.requisition_id:
                req_line = line.order_id.requisition_id.line_ids.filtered(
                    lambda l: l.product_id == line.product_id and l.construction_material_request_line_id
                )[:1]
                if req_line:
                    vals = {
                        "construction_project_id": req_line.construction_project_id.id,
                        "construction_wbs_id": req_line.construction_wbs_id.id,
                        "construction_boq_line_id": req_line.construction_boq_line_id.id,
                        "construction_material_request_line_id": req_line.construction_material_request_line_id.id,
                    }
                    account = req_line.construction_project_id.account_id
                    if account and not line.analytic_distribution:
                        vals["analytic_distribution"] = {str(account.id): 100.0}
                    line.write(vals)
            if line.construction_material_request_line_id:
                line.construction_material_request_line_id.purchase_line_id = line.id
        return lines
