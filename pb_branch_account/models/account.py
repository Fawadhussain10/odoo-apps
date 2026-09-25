# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.onchange('company_id')
    def onchange_branch(self):
        if self.company_id and self.company_id.journal_id:
            self.journal_id = self.company_id.journal_id.id
