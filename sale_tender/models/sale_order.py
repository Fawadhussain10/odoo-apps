# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tender_id = fields.Many2one(
        'sale.tender', string='Source Tender', readonly=True, copy=False)

    def action_view_tender(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tender',
            'res_model': 'sale.tender',
            'view_mode': 'form',
            'res_id': self.tender_id.id,
        }

    def unlink(self):
        tenders = self.env['sale.tender'].sudo().search(
            [('sale_order_id', 'in', self.ids)])
        res = super().unlink()
        if tenders:
            tenders.write({'sale_order_id': False, 'state': 'accepted'})
        return res
