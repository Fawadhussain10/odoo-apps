from odoo import models, fields, api


class ProductTemplateExt(models.Model):
    _inherit = 'product.template'

    is_discount_product = fields.Boolean(string="Discount Product", default=False,
                                         help="Indicates if this product is a discount product.")
