from odoo import _, api, fields, models
from odoo.exceptions import UserError

OWNERSHIP_SELECTION = [("owned", "Owned"), ("rented", "Rented")]
RENTAL_UOM_SELECTION = [("hour", "Per Hour"), ("day", "Per Day")]
EQUIPMENT_LOG_STATE_SELECTION = [("draft", "Draft"), ("approved", "Approved")]


class ConstructionEquipment(models.Model):
    """Simple equipment master, not hierarchical (same spirit as construction.cost.code but
    flat). No sequence - name is a plain required Char, like most master-data records."""
    _name = "construction.equipment"
    _description = "Construction Equipment"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char()
    ownership = fields.Selection(OWNERSHIP_SELECTION, default="owned", required=True)
    equipment_type = fields.Char(help="e.g. Excavator, Concrete Mixer.")
    internal_rate = fields.Float(string="Internal Rate (Cost/Hour when Owned)")
    rental_cost = fields.Float(string="Rental Cost")
    rental_uom = fields.Selection(RENTAL_UOM_SELECTION, string="Rental Basis", default="hour")
    active = fields.Boolean(default=True)
    log_ids = fields.One2many("construction.equipment.log", "equipment_id", string="Usage Logs")
    log_count = fields.Integer(compute="_compute_log_count")

    @api.depends("log_ids")
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)


class ConstructionEquipmentLog(models.Model):
    """No mail.thread/chatter here (unlike the Quality/HSE/Document registers): the FDD does not
    call for photos/evidence on equipment usage logs, so there is no attachment-workflow need
    driving the chatter convention for this particular model."""
    _name = "construction.equipment.log"
    _description = "Construction Equipment Usage Log"
    _order = "date desc, id desc"

    equipment_id = fields.Many2one("construction.equipment", required=True, ondelete="restrict", index=True)
    ownership = fields.Selection(related="equipment_id.ownership")
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    operator_id = fields.Many2one("hr.employee", string="Operator")
    date = fields.Date(default=fields.Date.context_today, required=True)
    mobilization = fields.Boolean(default=False, help="Mobilization/demobilization movement rather than a productive-usage entry.")
    fuel_consumed = fields.Float()
    meter_reading = fields.Float()
    productive_hours = fields.Float()
    idle_hours = fields.Float()
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    total_cost = fields.Monetary(compute="_compute_total_cost", store=True, currency_field="currency_id")
    state = fields.Selection(EQUIPMENT_LOG_STATE_SELECTION, default="draft", copy=False)
    analytic_line_id = fields.Many2one("account.analytic.line", readonly=True, copy=False)

    @api.depends("productive_hours", "equipment_id.ownership", "equipment_id.internal_rate", "equipment_id.rental_cost")
    def _compute_total_cost(self):
        for rec in self:
            rate = rec.equipment_id.internal_rate if rec.equipment_id.ownership == "owned" else rec.equipment_id.rental_cost
            rec.total_cost = rec.productive_hours * (rate or 0.0)

    def action_approve(self):
        """Approved usage posts project analytic cost. Guarded against double-posting via
        analytic_line_id (set once, then the draft->approved filter blocks re-entry)."""
        for rec in self.filtered(lambda r: r.state == "draft"):
            if rec.analytic_line_id:
                raise UserError(_("This usage log has already posted an analytic cost line."))
            account = rec.project_id.account_id
            if account:
                analytic_line = self.env["account.analytic.line"].create({
                    "name": _(
                        "Equipment Usage: %(equipment)s - %(project)s",
                        equipment=rec.equipment_id.name, project=rec.project_id.name,
                    ),
                    "account_id": account.id,
                    "amount": -rec.total_cost,
                    "unit_amount": rec.productive_hours,
                    "date": rec.date,
                    "company_id": (rec.project_id.company_id or self.env.company).id,
                })
                rec.analytic_line_id = analytic_line.id
            rec.state = "approved"
