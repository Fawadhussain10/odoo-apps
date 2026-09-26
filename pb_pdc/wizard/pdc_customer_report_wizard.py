# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PdcCustomerReportWizard(models.TransientModel):
    _name = 'pdc.customer.report.wizard'
    _description = 'PDC Cheque Report Wizard'

    partner_ids = fields.Many2many(
        'res.partner', string='Partners',
        help='Leave empty to include the cheques of all partners.')
    state = fields.Selection(
        lambda self: self.env['pdc.wizard']._fields['state'].selection,
        string='Status',
        help='Leave empty to include cheques in every status.')

    def _get_pdc_domain(self):
        self.ensure_one()
        domain = [('company_id', 'in', self.env.companies.ids)]
        if self.partner_ids:
            domain.append(('partner_id', 'child_of', self.partner_ids.ids))
        if self.state:
            domain.append(('state', '=', self.state))
        return domain

    def _get_report_lines(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        cheques = self.env['pdc.wizard'].search(
            self._get_pdc_domain(), order='partner_id, due_date, id')
        moves = self.env['account.move'].search(
            [('pdc_id', 'in', cheques.ids)], order='date, id')
        state_labels = dict(cheques._fields['state'].selection)
        move_state_labels = dict(moves._fields['state'].selection)
        lines = []
        for cheque in cheques:
            cheque_moves = moves.filtered(lambda m: m.pdc_id == cheque)
            invoices = cheque.invoice_ids | cheque.invoice_id
            lines.append({
                'cheque': cheque,
                'label': cheque.memo or ', '.join(invoices.mapped('name')),
                'remaining_days': (cheque.due_date - today).days if cheque.due_date else False,
                'state_label': state_labels.get(cheque.state),
                'jvs': [(move.name, move.state, move_state_labels.get(move.state)) for move in cheque_moves],
            })
        return lines

    def _get_report_sections(self):
        """Report data in print order: all Receive Money cheques, then all Send
        Money cheques (each list in partner / due date order), then one total
        row per partner, then the overall totals. Amounts are cheque amounts;
        net = receive - send."""
        self.ensure_one()
        lines = self._get_report_lines()
        receive_lines = [l for l in lines if l['cheque'].payment_type == 'receive_money']
        send_lines = [l for l in lines if l['cheque'].payment_type != 'receive_money']
        partner_totals = []
        by_partner = {}
        for line in lines:
            partner = line['cheque'].partner_id
            row = by_partner.get(partner.id)
            if row is None:
                row = by_partner[partner.id] = {'partner': partner, 'receive_total': 0.0,
                                                'send_total': 0.0, 'total': 0.0}
                partner_totals.append(row)
            amount = line['cheque'].payment_amount
            row['receive_total' if line['cheque'].payment_type == 'receive_money' else 'send_total'] += amount
            row['total'] += amount
        for row in partner_totals:
            row['net'] = row['receive_total'] - row['send_total']
        totals = {
            'receive_total': sum(r['receive_total'] for r in partner_totals),
            'send_total': sum(r['send_total'] for r in partner_totals),
            'total': sum(r['total'] for r in partner_totals),
            'net': sum(r['net'] for r in partner_totals),
            'receive_count': len(receive_lines),
            'send_count': len(send_lines),
            'count': len(lines),
        }
        return {'receive_lines': receive_lines, 'send_lines': send_lines,
                'partner_totals': partner_totals, 'totals': totals}

    def action_print(self):
        self.ensure_one()
        return self.env.ref('pb_pdc.action_report_pdc_customer').report_action(self)
