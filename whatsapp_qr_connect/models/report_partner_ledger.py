# -*- coding: utf-8 -*-
from odoo import api, models


class ReportPartnerLedger(models.AbstractModel):
    _name = 'report.whatsapp_qr_connect.report_partner_ledger'
    _description = 'Customer / Vendor Ledger report'

    @api.model
    def _ledger_lines(self, partner):
        """(lines, closing balance) of the receivable / payable entries of a contact.

        Positive balance: the contact owes you. Lines carry a running balance."""
        partner = partner.commercial_partner_id or partner
        lines = self.env['account.move.line'].search([
            ('partner_id', 'child_of', partner.id),
            ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
            ('parent_state', '=', 'posted'),
        ], order='date, id')
        result, balance = [], 0.0
        for line in lines:
            balance += line.balance
            result.append({
                'date': line.date,
                'move': line.move_id.name or '',
                'label': line.name or line.ref or '',
                'debit': line.debit,
                'credit': line.credit,
                'balance': balance,
            })
        return result, balance

    @api.model
    def _get_report_values(self, docids, data=None):
        partners = self.env['res.partner'].browse(docids)
        ledgers = {}
        for partner in partners:
            lines, balance = self._ledger_lines(partner)
            ledgers[partner.id] = {'lines': lines, 'balance': balance}
        return {
            'doc_ids': docids,
            'doc_model': 'res.partner',
            'docs': partners,
            'ledgers': ledgers,
            'company': self.env.company,
            'currency': self.env.company.currency_id,
        }
