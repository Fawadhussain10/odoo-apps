# -*- encoding: utf-8 -*-

from odoo import models, api


class WizLockLot(models.TransientModel):
    _name = 'wiz.lock.lot'
    _description = "PB Lock Lot"

    def action_lock_lots(self):
        lot_obj = self.env['stock.lot']
        active_ids = self.env.context['active_ids']
        lot_obj.browse(active_ids).button_lock()

    def action_unlock_lots(self):
        lot_obj = self.env['stock.lot']
        active_ids = self.env.context['active_ids']
        lot_obj.browse(active_ids).button_unlock()