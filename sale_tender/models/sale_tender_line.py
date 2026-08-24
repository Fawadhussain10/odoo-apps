# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleTenderLine(models.Model):
    _name = 'sale.tender.line'
    _description = 'Tender Line'
    _order = 'tender_id, sequence, id'

    tender_id = fields.Many2one(
        'sale.tender', string='Tender', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one(
        'product.product', string='Product',
        domain="[('sale_ok', '=', True)]")
    name = fields.Text(string='Description', required=True)
    product_uom_qty = fields.Float(string='Quantity', default=1.0, required=True)
    product_uom = fields.Many2one('uom.uom', string='UoM')
    price_unit = fields.Float(string='Unit Price', default=0.0)
    tax_id = fields.Many2many('account.tax', string='Taxes')
    currency_id = fields.Many2one(related='tender_id.currency_id', store=True)
    price_subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_amount', store=True)
    price_total = fields.Monetary(
        string='Total', compute='_compute_amount', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('product_id') and not vals.get('product_uom'):
                vals['product_uom'] = self.env['product.product'].browse(
                    vals['product_id']).uom_id.id
        return super().create(vals_list)

    @api.depends('product_uom_qty', 'price_unit', 'tax_id')
    def _compute_amount(self):
        for line in self:
            tax_results = line.tax_id.compute_all(
                line.price_unit,
                currency=line.currency_id,
                quantity=line.product_uom_qty,
                product=line.product_id,
                partner=line.tender_id.partner_id,
            )
            line.price_subtotal = tax_results['total_excluded']
            line.price_total = tax_results['total_included']

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return
        product = self.product_id.with_context(
            lang=self.tender_id.partner_id.lang,
            partner=self.tender_id.partner_id.id,
        )
        self.name = product.get_product_multiline_description_sale()
        self.price_unit = product.lst_price
        self.product_uom = product.uom_id
        self.tax_id = product.taxes_id.filtered(
            lambda t: t.company_id == self.tender_id.company_id)
