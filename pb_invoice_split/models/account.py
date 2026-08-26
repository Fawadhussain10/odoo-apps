# -*- coding: utf-8 -*-

from odoo import api,fields,models,_
from odoo.exceptions import ValidationError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    qty_to_split = fields.Float(string='Split Qty')
    price_to_split = fields.Float(string='Split Price')
    copied_line_id = fields.Many2one('account.move.line', 'Copied Invoice Line')

    def copy_data(self, default=None):
        if default is None:
            default = {}
        if self.env.context.get('from_split_invoice'):
            default['copied_line_id'] = self.id
        return super(AccountMoveLine, self).copy_data(default)

    @api.model_create_multi
    def create(self, vals_list):
        res = super(AccountMoveLine, self).create(vals_list)
        for line in res:
            sale_management_installed = bool(self.env['ir.module.module'].sudo().search_count(
                [('name', '=', 'sale_management'), ('state', '=', 'installed')]))
            if sale_management_installed and line.copied_line_id:
                sale_lines = self.env['sale.order.line'].search([('invoice_lines','in',line.copied_line_id.id)])
                for order_line in sale_lines:
                    order_line.with_context(check_move_validity=False).invoice_lines = [(4,line.id)]
        return res
