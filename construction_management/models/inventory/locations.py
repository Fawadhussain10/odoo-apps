from odoo import _, fields, models
from odoo.exceptions import UserError


class ProjectProjectLocations(models.Model):
    _inherit = "project.project"

    receiving_location_id = fields.Many2one("stock.location", string="Receiving Location", readonly=True)
    quality_hold_location_id = fields.Many2one("stock.location", string="Quality Hold Location", readonly=True)
    accepted_location_id = fields.Many2one("stock.location", string="Accepted Stock Location", readonly=True)
    issued_location_id = fields.Many2one("stock.location", string="Issued (Work Area) Location", readonly=True)
    consumed_location_id = fields.Many2one("stock.location", string="Consumed Location", readonly=True)
    return_location_id = fields.Many2one("stock.location", string="Return Location", readonly=True)
    scrap_location_id = fields.Many2one("stock.location", string="Scrap Location", readonly=True)

    def action_setup_stock_locations(self):
        """Create this project's site-inventory location tree, idempotently."""
        Location = self.env["stock.location"]
        parent = self.env.ref("construction_management.stock_location_construction_sites")
        for rec in self:
            if rec.accepted_location_id:
                continue
            if not rec.is_construction:
                raise UserError(_("Only construction projects need site inventory locations."))
            project_root = Location.create({
                "name": rec.name,
                "usage": "view",
                "location_id": parent.id,
            })
            rec.write({
                "receiving_location_id": Location.create({
                    "name": "Receiving", "usage": "internal", "location_id": project_root.id,
                }).id,
                "quality_hold_location_id": Location.create({
                    "name": "Quality Hold", "usage": "internal", "location_id": project_root.id,
                }).id,
                "accepted_location_id": Location.create({
                    "name": "Accepted", "usage": "internal", "location_id": project_root.id,
                }).id,
                "issued_location_id": Location.create({
                    "name": "Issued (Work Area)", "usage": "internal", "location_id": project_root.id,
                }).id,
                "consumed_location_id": Location.create({
                    # usage='production' is the standard Odoo trick (same one MRP uses for raw
                    # material consumption) to get an automatic stock_account valuation journal
                    # entry (Dr WIP / Cr Inventory) on the move into it, with no hand-written
                    # accounting code.
                    "name": "Consumed", "usage": "production", "location_id": project_root.id,
                }).id,
                "return_location_id": Location.create({
                    "name": "Return", "usage": "internal", "location_id": project_root.id,
                }).id,
                "scrap_location_id": Location.create({
                    "name": "Scrap", "usage": "inventory", "location_id": project_root.id,
                }).id,
            })
