from odoo import fields, models


class ConstructionBoqLoadTemplateWizard(models.TransientModel):
    _name = "construction.boq.load.template.wizard"
    _description = "Load BOQ Lines From a Template"

    boq_id = fields.Many2one("construction.boq", required=True)
    template_id = fields.Many2one(
        "construction.boq.template", required=True,
        help="Reusable predefined BOQ (e.g. 3.5 Marla, 10 Marla, 1 Kanal). Its lines are copied into this project's BOQ.",
    )

    def action_load(self):
        self.ensure_one()
        self.boq_id.action_load_from_template(self.template_id)
        return {"type": "ir.actions.act_window_close"}
