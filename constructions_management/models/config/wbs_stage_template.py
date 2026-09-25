from odoo import fields, models


class ConstructionWbsStageTemplate(models.Model):
    _name = "construction.wbs.stage.template"
    _description = "Construction WBS Stage Template"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    default_duration = fields.Integer(string="Default Duration (days)", default=0)
    progress_weight = fields.Float(default=1.0, help="Relative weight of this stage when computing overall project schedule progress.")
    active = fields.Boolean(default=True)
    category_ids = fields.Many2many(
        "construction.project.category",
        "construction_category_stage_rel",
        "stage_id",
        "category_id",
        string="Used In Categories",
    )
