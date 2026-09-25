from odoo import fields, models


class ConstructionDocumentType(models.Model):
    _name = "construction.document.type"
    _description = "Construction Document Type"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char()
    category = fields.Selection(
        [
            ("drawing", "Drawing"),
            ("rfi", "RFI"),
            ("contract", "Contract"),
            ("submittal", "Submittal"),
            ("method_statement", "Method Statement"),
            ("inspection", "Inspection"),
            ("certificate", "Certificate"),
            ("permit", "Permit"),
            ("other", "Other"),
        ],
        default="other",
        required=True,
    )
    active = fields.Boolean(default=True)
    sequence_id = fields.Many2one(
        "ir.sequence", string="Numbering Sequence",
        help="Optional dedicated sequence for document numbers of this type.",
    )
