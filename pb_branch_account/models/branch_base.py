# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def _get_default_journal(self):
        journal_domain = [
            ('type', '=', 'sale'),
            ('company_id', '=', self.env.user.company_id.id),
        ]
        default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
        return default_journal_id.id and default_journal_id or False

    journal_id = fields.Many2one('account.journal', string="Branch Sales Journal", default=_get_default_journal)
