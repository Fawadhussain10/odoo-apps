from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    pra_hs_code = fields.Char(
        string="PRA HS/PCT Code",
        help="8-digit PCT/HS code required by the Punjab Revenue Authority (PRA) "
             "e-IMS for every item reported from the Point of Sale.",
    )
