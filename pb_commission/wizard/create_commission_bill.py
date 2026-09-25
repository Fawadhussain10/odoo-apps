# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PBCommissionBill(models.TransientModel):
    _name = "commission.bill"
    _description = "Create Commission Bill"

    @api.model
    def _get_default_journal(self):
        journal_domain = [
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.user.company_id.id),
        ]
        default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
        return default_journal_id.id and default_journal_id or False

    hide_groupby_partner = fields.Boolean(string='Hide Group by Partner')
    groupby_partner = fields.Boolean(string='Group by Partner',
        help='Set true if want to create single bill for Partner')
    print_commission = fields.Boolean(string='Add Commission no in Description',
        help='Set true if want to append SO in bill line Description')
    journal_id = fields.Many2one('account.journal', default=_get_default_journal, required=True)

    def create_bill(self, line):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'ref': False,
            'partner_id': line.partner_id.id,
            'journal_id': self.journal_id.id
        }) 
        return bill

    def create_bill_line(self, line, bill, product_id, print_commission=False):
        account_id = product_id.property_account_income_id or product_id.categ_id.property_account_income_categ_id
        if not account_id:
            raise UserError(
                _('There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') %
                (product_id.name,))
        name = product_id.name

        if print_commission:
            name = name + ': ' + line.name

        inv_line = self.env['account.move.line'].with_context(check_move_validity=False).create({
            'move_id': bill.id,
            'name': name,
            'price_unit': line.payable_amount,
            'quantity': 1,
            'discount': 0.0,
            'product_uom_id': product_id.uom_id.id,
            'product_id': product_id.id,
            'account_id': account_id.id,
            'tax_ids': [(6, 0, product_id.supplier_taxes_id and product_id.supplier_taxes_id.ids or [])],
            'display_type': 'product',
        })
        return inv_line

    def create_bills(self):
        Commission = self.env['pb.commission']
        groupby = False
        bills = []
        product_id = self.env.user.company_id.commission_product_id

        #PB: Check if any line is target based do not create invoice.
        lines = Commission.browse(self.env.context.get('active_ids', []))
        if any(line.target_based_commission and not line.commission_sheet_id for line in lines):
            raise UserError(_('Commision Bill Can be created form commssion sheet only for target based commissions.'))

        if not product_id:
            raise UserError(_('Please set Commission Product in company first.'))
        if self.groupby_partner:
            groupby = 'partner_id'
        if groupby:
            commission_group = Commission.read_group([('id', 'in', self.env.context.get('active_ids', [])),
                ('invoice_line_id', '=', False)] , fields=[groupby], groupby=[groupby])
            for group in commission_group:
                domain = [('id', 'in', self.env.context.get('active_ids', [])),
                    ('invoice_line_id', '=', False)]
                if group[groupby]:
                    domain += [(groupby, '=', int(group[groupby][0]))]
                lines = Commission.search(domain)
                if lines:
                    bill = self.create_bill(lines[0])
                    bills.append(bill.id)
                    for line in lines:
                        line_rec = self.create_bill_line(line, bill, product_id, self.print_commission)
                        line.invoice_line_id = line_rec.id

        else:
            for line in lines:
                if not line.invoice_line_id:
                    bill = self.create_bill(line)
                    bills.append(bill.id)
                    line_rec = self.create_bill_line(line, bill, product_id, self.print_commission)
                    line.invoice_line_id = line_rec.id

        if not bills:
            raise UserError(_('Please check there is nothing to bill in selected Commission may be you are missing partner or trying to bill already billd Commissions.'))

        #last bill from above loop will be used
        if self.env.context.get('commission_sheet_id', False):
            sheet = self.env['pb.commission.sheet'].search([('id','=',self.env.context.get('commission_sheet_id', False))])
            sheet.payment_invoice_id = bill.id


        if self.env.context.get('open_bills', False):
            action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_in_invoice_type")
            if len(bills) > 1:
                action['domain'] = [('id', 'in', bills)]
            elif len(bills) == 1:
                action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
                action['res_id'] = bills[0]
            else:
                action = {'type': 'ir.actions.act_window_close'}
            return action
        return {'type': 'ir.actions.act_window_close'}