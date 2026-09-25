# -*- coding: utf-8 -*-

from odoo import api, fields, models,_
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    pb_invoice_summary_id = fields.Many2one('pb.invoice.summary', string='Invoice Summary')


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    pb_invoice_summary_id = fields.Many2one('pb.invoice.summary', string='Invoice Summary')
    pb_product_category_id = fields.Many2one('product.category', related="product_id.categ_id", store=True, string='Product Category')

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    pb_invoice_summary_id = fields.Many2one('pb.invoice.summary', string='Invoice Summary')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: