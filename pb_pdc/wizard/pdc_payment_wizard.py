# Copyright (C) PackBytes.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta, date, datetime

from odoo.exceptions import ValidationError


class Attachment(models.Model):
    _inherit = 'ir.attachment'

    pdc_id = fields.Many2one('pdc.wizard')


class PDC_wizard(models.Model):
    _name = "pdc.wizard"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = "PDC Wizard"

    name = fields.Char("Name", default='New', readonly=True, tracking=True)
    # check_amount_in_words = fields.Char(string="Amount in Words",compute='_compute_check_amount_in_words')
    payment_type = fields.Selection([('receive_money', 'Receive Money'), (
        'send_money', 'Send Money')], string="Payment Type", default='receive_money', tracking=True)
    partner_id = fields.Many2one('res.partner', string="Partner", tracking=True)
    payment_amount = fields.Monetary("Payment Amount", tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string="Currency", default=lambda self: self.env.company.currency_id, tracking=True)
    reference = fields.Char("Cheque Reference", tracking=True)
    journal_id = fields.Many2one('account.journal', string="Payment Journal", domain=[
        ('type', '=', 'bank')], required=True, tracking=True)
    cheque_status = fields.Selection([('draft', 'Draft'), ('deposit', 'Deposit'), ('paid', 'Paid')],
                                     string="Cheque Status", default='draft', tracking=True)
    payment_date = fields.Date(
        "Payment Date", default=fields.Date.context_today, required=True, tracking=True)
    due_date = fields.Date("Due Date", required=True, tracking=True)
    memo = fields.Char("Memo", tracking=True)
    agent = fields.Char("Agent", tracking=True)
    bank_id = fields.Many2one('res.bank', string="Bank", tracking=True)
    attachment_ids = fields.Many2many('ir.attachment', 'pdc_attachment_rel', string='Cheque Image')
    company_id = fields.Many2one('res.company', string='company', default=lambda self: self.env.company, tracking=True)
    invoice_id = fields.Many2one('account.move', string="Invoice/Bill", tracking=True)
    state = fields.Selection([('draft', 'Draft'), ('registered', 'Registered'), ('returned', 'Returned'),
                              ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'),
                              ('cancel', 'Cancelled')], string="State", default='draft', tracking=True,
                             group_expand='_group_expand_states')

    deposited_debit = fields.Many2one('account.move.line')
    deposited_credit = fields.Many2one('account.move.line')

    invoice_ids = fields.Many2many('account.move')
    account_move_ids = fields.Many2many('account.move', compute="compute_account_moves", )
    draft_move_count = fields.Integer(string='Draft Invoices/Bills', compute="compute_account_moves")
    done_date = fields.Date(string="Done Date", readonly=True, tracking=True)
    wizard_line_ids = fields.One2many('pdc.wizard.line', 'wizard_id', string='Wizard Lines')
    is_partial = fields.Boolean(string='Partial?')

    # kanban card edge colour (Odoo colour index), used by highlight_color
    state_color = fields.Integer(compute='_compute_state_color')

    # smart button counters
    invoice_count = fields.Integer(string='Invoice Count', compute='_compute_smart_counts')
    journal_entry_count = fields.Integer(string='Journal Entry Count', compute='_compute_smart_counts')
    journal_item_count = fields.Integer(string='Journal Item Count', compute='_compute_smart_counts')
    attachment_count = fields.Integer(string='Cheque Image Count', compute='_compute_smart_counts')

    _unique_name = models.Constraint(
        'UNIQUE(reference)',
        'The Cheque Reference must be unique.',
    )

    # pdc only be allowed to delete in draft state
    def unlink(self):

        for rec in self:
            if rec.state != 'draft':
                raise UserError("You can only delete draft state pdc")

        return super(PDC_wizard, self).unlink()

    def action_register_check(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        account_move_model = self.env[active_model].browse(active_id)

        if account_move_model.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError("Only Customer invoice and vendor bills are considered!")

        move_listt = []
        payment_amount = 0.0
        payment_type = ''
        if len(active_ids) > 0:
            account_moves = self.env[active_model].browse(active_ids)
            partners = account_moves.mapped('partner_id')
            if len(set(partners)) != 1:
                raise UserError('Partners must be same')

            states = account_moves.mapped('state')
            if len(set(states)) != 1 or states[0] != 'posted':
                raise UserError('Only posted invoices/bills are considered for PDC payment!!')

            for account_move in account_moves:
                if account_move.payment_state != 'paid' and account_move.amount_residual != 0.0:
                    payment_amount = payment_amount + account_move.amount_residual
                    move_listt.append(account_move.id)
        if not move_listt:
            raise UserError("Selected invoices/bills are already paid!!")

        if account_moves[0].move_type in ('in_invoice'):
            payment_type = 'send_money'

        if account_moves[0].move_type in ('out_invoice'):
            payment_type = 'receive_money'

        return {
            'name': 'PDC Payment',
            'res_model': 'pdc.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('pb_pdc.pb_pdc_wizard_form_wizard').id,
            'context': {
                'default_invoice_ids': [(6, 0, move_listt)],
                'default_partner_id': account_move_model.partner_id.id,
                'default_payment_amount': payment_amount,
                'default_payment_type': payment_type
            },
            'target': 'new',
            'type': 'ir.actions.act_window'
        }

    @api.model
    def _group_expand_states(self, states, domain, order=None):  # order: not passed from Odoo 19 on
        # kanban columns follow the cheque lifecycle instead of alphabetical order
        return [key for key, _label in self._fields['state'].selection]

    @api.depends('state')
    def _compute_state_color(self):
        colors = {'registered': 4, 'deposited': 4, 'returned': 2, 'bounced': 1, 'done': 10}
        for rec in self:
            rec.state_color = colors.get(rec.state, 0)

    def _compute_smart_counts(self):
        move_data = self.env['account.move']._read_group(
            [('pdc_id', 'in', self.ids)], ['pdc_id'], ['__count'])
        move_counts = {pdc.id: count for pdc, count in move_data}
        line_data = self.env['account.move.line']._read_group(
            [('pdc_id', 'in', self.ids)], ['pdc_id'], ['__count'])
        line_counts = {pdc.id: count for pdc, count in line_data}
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids | rec.invoice_id)
            rec.journal_entry_count = move_counts.get(rec.id, 0)
            rec.journal_item_count = line_counts.get(rec.id, 0)
            rec.attachment_count = len(rec.attachment_ids)

    def open_invoices(self):
        self.ensure_one()
        invoices = self.invoice_ids | self.invoice_id
        action = {
            'name': 'Invoices' if self.payment_type == 'receive_money' else 'Bills',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'context': {'create': False},
        }
        if len(invoices) == 1:
            action.update({'view_mode': 'form', 'res_id': invoices.id})
        else:
            action.update({'view_mode': 'tree,form', 'domain': [('id', 'in', invoices.ids)]})
        return action

    def open_attachments(self):
        [action] = self.env.ref('base.action_attachment').read()

        action['domain'] = [('id', 'in', self.attachment_ids.ids)]
        return action

    def open_journal_items(self):
        [action] = self.env.ref('account.action_account_moves_all').read()
        ids = self.env['account.move.line'].search([('pdc_id', '=', self.id)])
        id_list = []
        for pdc_id in ids:
            id_list.append(pdc_id.id)
        if id_list:
            action['domain'] = [('id', 'in', id_list)]
        else:
            action['domain'] = [('id', '=', False)]
        return action

    def open_journal_entry(self):
        [action] = self.env.ref(
            'pb_pdc.pb_pdc_action_move_journal_line').read()
        ids = self.env['account.move'].search([('pdc_id', '=', self.id)])
        id_list = []
        for pdc_id in ids:
            id_list.append(pdc_id.id)
        action['domain'] = [('id', 'in', id_list)]
        return action

    @api.model
    def default_get(self, fields):
        rec = super(PDC_wizard, self).default_get(fields)
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        # Check for selected invoices ids
        if not active_ids or active_model != 'account.move':
            return rec
        invoices = self.env['account.move'].browse(active_ids)
        if invoices and len(invoices) == 1:
            invoice = invoices[0]
            if invoice.move_type in ('out_invoice', 'out_refund'):
                rec.update({'payment_type': 'receive_money'})
            elif invoice.move_type in ('in_invoice', 'in_refund'):
                rec.update({'payment_type': 'send_money'})

            rec.update({'partner_id': invoice.partner_id.id,
                        'payment_amount': invoice.amount_residual,
                        'invoice_id': invoice.id,
                        'due_date': invoice.invoice_date_due,
                        'memo': invoice.name})

        return rec

    @api.constrains('is_partial', 'invoice_ids')
    def _constrains_is_partial(self):
        """
        If partial is selected, create wizard lines for each invoice.
        """
        if self.is_partial and self.invoice_ids:
            self.wizard_line_ids = [(5, 0, 0)]
            lines = []
            for inv in self.invoice_ids:
                lines.append((0, 0, {
                    'invoice_id': inv.id,
                    'custom_amount': inv.amount_residual,
                }))
            self.wizard_line_ids = lines
        else:
            self.wizard_line_ids = [(5, 0, 0)]

    def _get_partner_moves_domain(self, states=('posted',)):
        """Invoices (customer cheque) or bills (vendor cheque) of the cheque's
        partner that can still be paid. Matching on the commercial partner, like
        Odoo payments do, so documents addressed to a contact of the company (or
        to the company when the cheque names a contact) are included too."""
        self.ensure_one()
        return [
            ('commercial_partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('move_type', '=', 'out_invoice' if self.payment_type == 'receive_money' else 'in_invoice'),
            ('state', 'in', list(states)),
            ('payment_state', 'not in', ('paid', 'in_payment', 'reversed')),
            ('amount_residual', '!=', 0.0),
            ('company_id', '=', (self.company_id or self.env.company).id),
        ]

    @api.depends('payment_type', 'partner_id', 'company_id')
    def compute_account_moves(self):
        Move = self.env['account.move']
        for rec in self:
            if not rec.partner_id:
                rec.account_move_ids = False
                rec.draft_move_count = 0
                continue
            rec.account_move_ids = Move.search(rec._get_partner_moves_domain())
            # draft documents cannot be paid yet; counted only to explain an
            # empty Invoices/Bills picker on the form
            draft_domain = [d for d in rec._get_partner_moves_domain(states=('draft',))
                            if d[0] not in ('payment_state', 'amount_residual')]
            rec.draft_move_count = Move.search_count(draft_domain)

    @api.onchange('partner_id')
    def _onchange_partner(self):

        if self.env.company.auto_fill_open_invoice and self.partner_id:
            moves = self.env['account.move'].search(self._get_partner_moves_domain())
            self.invoice_ids = [(6, 0, moves.ids)]

    # Register pdc payment
    def button_register(self):
        listt = []
        if self:

            if self.invoice_id:
                listt.append(self.invoice_id.id)
            if self.invoice_ids:
                listt.extend(self.invoice_ids.ids)

            self.write({
                'invoice_ids': [(6, 0, list(set(listt)))]
            })

            if self.cheque_status == 'draft':
                self.write({'state': 'draft'})

            if self.cheque_status == 'deposit':
                self.action_register()
                self.action_deposited()
                self.write({'state': 'deposited'})

            if self.cheque_status == 'paid':
                self.action_register()
                self.action_deposited()
                self.action_done()
                self.write({'state': 'done'})

    def action_register(self):
        self.check_payment_amount()

        if self.is_partial:
            if self.wizard_line_ids:
                inv_list_amount_residuals = self.invoice_ids.mapped('amount_residual')
                list_amount_residuals = self.wizard_line_ids.mapped('custom_amount')
                amount = (self.currency_id.round(sum(list_amount_residuals)) if self.currency_id else round(
                    sum(list_amount_residuals), 3))
                inv_amount = (self.currency_id.round(sum(inv_list_amount_residuals)) if self.currency_id else round(
                    sum(inv_list_amount_residuals), 3))
                if amount > inv_amount and amount != 0:
                    raise UserError(_(
                        f"Allocated amount {round(amount, 3)} cannot exceed total invoice/bill remaining {round(inv_amount, 3)}!!!"
                    ))
                if self.payment_amount < round(amount, 3) or round(amount, 3) <= 0:
                    raise ValidationError(
                        _(f"Please make check amount {self.payment_amount} greater than total partial amount {round(amount, 3)} or atleast equal to partial amount"))
        else:
            if self.invoice_ids:
                list_amount_residuals = self.invoice_ids.mapped('amount_residual')
                amount = (self.currency_id.round(sum(list_amount_residuals)) if self.currency_id else round(
                    sum(list_amount_residuals), 3))
                if self.payment_amount < round(amount, 3) and amount != 0:
                    raise UserError(_(
                        f"Payment amount {self.payment_amount} is less than total invoice/bill amount which is {round(amount, 3)}!!!"))
        self.write({'state': 'registered'})

    def check_payment_amount(self):
        if self.payment_amount <= 0.0:
            raise UserError("Amount must be greater than zero!")

    def check_pdc_account(self):
        if self.payment_type == 'receive_money':
            if not self.env.company.pdc_customer:
                raise UserError(
                    "Please Set PDC payment account for Customer !")
            else:
                return self.env.company.pdc_customer.id

        else:
            if not self.env.company.pdc_vendor:
                raise UserError(
                    "Please Set PDC payment account for Supplier !")
            else:
                return self.env.company.pdc_vendor.id

    def get_partner_account(self):
        if self.payment_type == 'receive_money':
            return self.partner_id.property_account_receivable_id.id
        else:
            return self.partner_id.property_account_payable_id.id

    def action_returned(self):
        self.check_payment_amount()
        self.write({'state': 'returned'})

    def get_credit_move_line(self, account):
        return {
            'pdc_id': self.id,
            'partner_id': self.partner_id.id,
            'account_id': account,
            'credit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
        }

    def get_debit_move_line(self, account):
        return {
            'pdc_id': self.id,
            'partner_id': self.partner_id.id,
            'account_id': account,
            'debit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
        }

    def get_move_vals(self, debit_line, credit_line, c=False):
        return {
            'pdc_id': self.id,
            'date': date.today() if c else self.payment_date,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'ref': self.memo,
            'move_type': 'entry',
            'line_ids': [(0, 0, debit_line),
                         (0, 0, credit_line)]
        }

    def action_deposited(self):
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit, False)

        self.write({
            'state': 'deposited',
        })

        total_amount_residuals = sum(self.invoice_ids.mapped('amount_residual'))
        partial_total_amount_residuals = sum(self.wizard_line_ids.mapped('custom_amount'))
        if self.wizard_line_ids and partial_total_amount_residuals != 0 and self.is_partial:
            move_id = move.create(move_vals)
            move_id.action_post()

            self.write({'deposited_debit': move_id.line_ids.filtered(lambda x: x.debit > 0),
                        'deposited_credit': move_id.line_ids.filtered(lambda x: x.credit > 0)})

        if self.invoice_ids and total_amount_residuals != 0 and not self.is_partial:
            move_id = move.create(move_vals)
            move_id.action_post()

            self.write({'deposited_debit': move_id.line_ids.filtered(lambda x: x.debit > 0),
                        'deposited_credit': move_id.line_ids.filtered(lambda x: x.credit > 0)})

    def action_bounced(self):
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}

        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)

        if self.memo:
            move_line_vals_debit.update({'name': 'PDC Payment :' + self.memo})
            move_line_vals_credit.update({'name': 'PDC Payment :' + self.memo})
        else:
            move_line_vals_debit.update({'name': 'PDC Payment'})
            move_line_vals_credit.update({'name': 'PDC Payment'})
        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit, False)
        total_amount_residuals = sum(self.invoice_ids.mapped('amount_residual'))
        partial_total_amount_residuals = sum(self.wizard_line_ids.mapped('custom_amount'))
        if self.wizard_line_ids and partial_total_amount_residuals != 0 and self.is_partial:
            move_id = move.create(move_vals)
            move_id.action_post()

        if self.invoice_ids and total_amount_residuals != 0 and not self.is_partial:
            move_id = move.create(move_vals)
            move_id.action_post()

        self.write({'state': 'bounced'})

    def action_done(self):
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        #         bank_account = self.journal_id.payment_debit_account_id.id or self.journal_id.payment_credit_account_id.id
        bank_account = self.journal_id._get_journal_inbound_outstanding_payment_accounts()
        bank_account = bank_account[0].id if bank_account else False

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(self.journal_id.default_account_id.id)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(self.journal_id.default_account_id.id)

        if self.memo:
            move_line_vals_debit.update({'name': 'PDC Payment :' + self.memo, 'partner_id': self.partner_id.id})
            move_line_vals_credit.update({'name': 'PDC Payment :' + self.memo, 'partner_id': self.partner_id.id})
        else:
            move_line_vals_debit.update({'name': 'PDC Payment', 'partner_id': self.partner_id.id})
            move_line_vals_credit.update({'name': 'PDC Payment', 'partner_id': self.partner_id.id})

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit, True)

        # invoice = self.env['account.move'].sudo().search([('name','=',self.memo)])
        # if invoice:
        if not self.is_partial:
            total_amount_residuals = sum(self.invoice_ids.mapped('amount_residual'))
            if self.invoice_ids and total_amount_residuals != 0:
                move_id = move.create(move_vals)
                move_id.action_post()

                payment_amount = self.payment_amount
                for invoice in self.invoice_ids:

                    if self.payment_type == 'receive_money':
                        # reconcilation Entry for Invoice
                        debit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', invoice.id),
                                                                                     ('debit', '>', 0.0)], limit=1)

                        credit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', move_id.id),
                                                                                      ('credit', '>', 0.0)], limit=1)

                        if debit_move_id and credit_move_id and payment_amount > 0:
                            # full_reconcile_id = self.env['account.full.reconcile'].sudo().create({})
                            if payment_amount > invoice.amount_residual:
                                amount = invoice.amount_residual

                            else:
                                amount = payment_amount

                            payment_amount -= invoice.amount_residual
                            partial_reconcile_id_1 = self.env['account.partial.reconcile'].sudo().create(
                                {'debit_move_id': debit_move_id.id,
                                 'credit_move_id': credit_move_id.id,
                                 'amount': amount,
                                 'debit_amount_currency': amount,
                                 'credit_amount_currency': 0
                                 })

                            partial_reconcile_id_2 = self.env['account.partial.reconcile'].sudo().create(
                                {'debit_move_id': self.deposited_debit.id,
                                 'credit_move_id': self.deposited_credit.id,
                                 'amount': amount,
                                 'debit_amount_currency': amount,
                                 'credit_amount_currency': 0
                                 })

                            if invoice.amount_residual == 0:
                                involved_lines = []

                                debit_invoice_line_id = self.env['account.move.line'].search(
                                    [('move_id', '=', invoice.id), ('debit', '>', 0)], limit=1)
                                partial_reconcile_ids = self.env['account.partial.reconcile'].sudo().search(
                                    [('debit_move_id', '=', debit_invoice_line_id.id)])

                                for partial_reconcile_id in partial_reconcile_ids:
                                    involved_lines.append(partial_reconcile_id.credit_move_id.id)
                                    involved_lines.append(partial_reconcile_id.debit_move_id.id)
                                self.env['account.full.reconcile'].create({
                                    'partial_reconcile_ids': [(6, 0, partial_reconcile_ids.ids)],
                                    'reconciled_line_ids': [(6, 0, involved_lines)],
                                })

                            involved_lines = [self.deposited_debit.id, self.deposited_credit.id]

                            self.env['account.full.reconcile'].create({
                                'partial_reconcile_ids': [(6, 0, [partial_reconcile_id_2.id])],
                                'reconciled_line_ids': [(6, 0, involved_lines)],
                            })


                    else:
                        # reconcilation Entry for Invoice
                        credit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', invoice.id),
                                                                                      ('credit', '>', 0.0)], limit=1)

                        debit_move_id = self.env['account.move.line'].sudo().search([('move_id', '=', move_id.id),
                                                                                     ('debit', '>', 0.0)], limit=1)

                        if debit_move_id and credit_move_id and payment_amount > 0:
                            if payment_amount > invoice.amount_residual:
                                amount = invoice.amount_residual

                            else:
                                amount = payment_amount

                            payment_amount -= invoice.amount_residual

                            partial_reconcile_id_1 = self.env['account.partial.reconcile'].sudo().create(
                                {'debit_move_id': debit_move_id.id,
                                 'credit_move_id': credit_move_id.id,
                                 'amount': amount,
                                 'credit_amount_currency': amount,
                                 'debit_amount_currency': 0
                                 })
                            partial_reconcile_id_2 = self.env['account.partial.reconcile'].sudo().create(
                                {'debit_move_id': self.deposited_debit.id,
                                 'credit_move_id': self.deposited_credit.id,
                                 'amount': amount,
                                 'debit_amount_currency': amount,
                                 'credit_amount_currency': 0
                                 })

                            if invoice.amount_residual == 0:
                                involved_lines = []

                                credit_invoice_line_id = self.env['account.move.line'].search(
                                    [('move_id', '=', invoice.id), ('credit', '>', 0)], limit=1)
                                partial_reconcile_ids = self.env['account.partial.reconcile'].sudo().search(
                                    [('credit_move_id', '=', credit_invoice_line_id.id)])

                                for partial_reconcile_id in partial_reconcile_ids:
                                    involved_lines.append(partial_reconcile_id.credit_move_id.id)
                                    involved_lines.append(partial_reconcile_id.debit_move_id.id)
                                self.env['account.full.reconcile'].create({
                                    'partial_reconcile_ids': [(6, 0, partial_reconcile_ids.ids)],
                                    'reconciled_line_ids': [(6, 0, involved_lines)],
                                })

                            involved_lines = [self.deposited_debit.id, self.deposited_credit.id]

                            self.env['account.full.reconcile'].create({
                                'partial_reconcile_ids': [(6, 0, [partial_reconcile_id_2.id])],
                                'reconciled_line_ids': [(6, 0, involved_lines)],
                            })

            else:
                bank_account = self.journal_id._get_journal_inbound_outstanding_payment_accounts()
                bank_account = bank_account[0].id if bank_account else False

                partner_account = self.get_partner_account()

                debit_move_line = {
                    'pdc_id': self.id,
                    'partner_id': self.partner_id.id,
                    'account_id': bank_account if self.payment_type == 'receive_money' else partner_account,
                    'debit': self.payment_amount,
                    'ref': self.memo,
                    'date': self.due_date,
                    'date_maturity': self.due_date,
                }

                credit_move_line = {
                    'pdc_id': self.id,
                    'partner_id': self.partner_id.id,
                    'account_id': partner_account if self.payment_type == 'receive_money' else bank_account,
                    'credit': self.payment_amount,
                    'ref': self.memo,
                    'date': self.due_date,
                    'date_maturity': self.due_date,
                }

                move_vals = {
                    'pdc_id': self.id,
                    'date': self.due_date,
                    'journal_id': self.journal_id.id,
                    'ref': self.memo,
                    'line_ids': [(0, 0, debit_move_line),
                                 (0, 0, credit_move_line)]
                }

                move = self.env['account.move'].create(move_vals)
                move.action_post()
        else:
            partial_total_amount_residuals = sum(self.wizard_line_ids.mapped('custom_amount'))
            if self.wizard_line_ids and partial_total_amount_residuals != 0:
                move_id = move.create(move_vals)
                move_id.action_post()

                for line in self.wizard_line_ids:
                    invoice = line.invoice_id
                    custom_amount = line.custom_amount

                    if self.payment_type == 'receive_money':
                        # Reconciliation entry for Invoice
                        debit_move_id = self.env['account.move.line'].sudo().search([
                            ('move_id', '=', invoice.id),
                            ('debit', '>', 0.0)
                        ], limit=1)

                        credit_move_id = self.env['account.move.line'].sudo().search([
                            ('move_id', '=', move_id.id),
                            ('credit', '>', 0.0)
                        ], limit=1)

                        if debit_move_id and credit_move_id and custom_amount > 0:
                            # Partial reconcile between invoice debit and payment credit
                            partial_reconcile_id_1 = self.env['account.partial.reconcile'].sudo().create({
                                'debit_move_id': debit_move_id.id,
                                'credit_move_id': credit_move_id.id,
                                'amount': custom_amount,
                                'debit_amount_currency': custom_amount,
                                'credit_amount_currency': 0,
                            })

                            # Partial reconcile between deposited debit/credit
                            partial_reconcile_id_2 = self.env['account.partial.reconcile'].sudo().create({
                                'debit_move_id': self.deposited_debit.id,
                                'credit_move_id': self.deposited_credit.id,
                                'amount': custom_amount,
                                'debit_amount_currency': custom_amount,
                                'credit_amount_currency': 0,
                            })

                            # If invoice is fully paid now, do a full reconcile
                            if invoice.amount_residual == 0:
                                involved_lines = []
                                debit_invoice_line_id = self.env['account.move.line'].search(
                                    [('move_id', '=', invoice.id), ('debit', '>', 0)], limit=1
                                )
                                partial_reconcile_ids = self.env['account.partial.reconcile'].sudo().search(
                                    [('debit_move_id', '=', debit_invoice_line_id.id)]
                                )
                                for partial_reconcile_id in partial_reconcile_ids:
                                    involved_lines.append(partial_reconcile_id.credit_move_id.id)
                                    involved_lines.append(partial_reconcile_id.debit_move_id.id)

                                self.env['account.full.reconcile'].create({
                                    'partial_reconcile_ids': [(6, 0, partial_reconcile_ids.ids)],
                                    'reconciled_line_ids': [(6, 0, involved_lines)],
                                })

                            involved_lines = [self.deposited_debit.id, self.deposited_credit.id]

                            self.env['account.full.reconcile'].create({
                                'partial_reconcile_ids': [(6, 0, [partial_reconcile_id_2.id])],
                                'reconciled_line_ids': [(6, 0, involved_lines)],
                            })
        self.write({
            'state': 'done',
            'done_date': date.today(),
        })

    # form view cancel button
    def action_cancel(self):
        self.action_delete_related_moves()
        if self.company_id.pdc_operation_type == 'cancel':
            self.write({'state': 'cancel'})

        elif self.company_id.pdc_operation_type == 'cancel_draft':
            self.write({'state': 'draft'})

        elif self.company_id.pdc_operation_type == 'cancel_delete':
            self.write({'state': 'draft'})
            self.unlink()

    # multi action methods
    def action_pdc_cancel(self):
        self.action_delete_related_moves()
        self.write({'state': 'cancel'})

    def action_pdc_cancel_draft(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})

    def action_pdc_cancel_delete(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})
        self.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        default_type = None
        for vals in vals_list:
            payment_type = vals.get('payment_type')
            if not payment_type:
                # a read-only payment type is not sent by the form: fall back to
                # the menu's default_payment_type, then to the field default
                if default_type is None:
                    default_type = self.default_get(['payment_type']).get('payment_type') or 'receive_money'
                payment_type = vals['payment_type'] = default_type
            if not vals.get('name') or vals.get('name') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pdc.payment.customer' if payment_type == 'receive_money' else 'pdc.payment.vendor')

        records = super(PDC_wizard, self).create(vals_list)
        for res in records:
            res.attachment_ids.write({
                'res_id': res.id
            })

        return records

    # ==============================
    #    CRON SCHEDULER CUSTOMER
    # ==============================
    @api.model
    def notify_customer_due_date(self):
        emails = []
        if self.env.company.is_cust_due_notify:
            notify_day_1 = self.env.company.notify_on_1
            notify_day_2 = self.env.company.notify_on_2
            notify_day_3 = self.env.company.notify_on_3
            notify_day_4 = self.env.company.notify_on_4
            notify_day_5 = self.env.company.notify_on_5
            notify_date_1 = False
            notify_date_2 = False
            notify_date_3 = False
            notify_date_4 = False
            notify_date_5 = False
            if notify_day_1:
                notify_date_1 = fields.Date.today() + timedelta(days=int(notify_day_1) * -1)
            if notify_day_2:
                notify_date_2 = fields.Date.today() + timedelta(days=int(notify_day_2) * -1)
            if notify_day_3:
                notify_date_3 = fields.Date.today() + timedelta(days=int(notify_day_3) * -1)
            if notify_day_4:
                notify_date_4 = fields.Date.today() + timedelta(days=int(notify_day_4) * -1)
            if notify_day_5:
                notify_date_5 = fields.Date.today() + timedelta(days=int(notify_day_5) * -1)

            records = self.search([('payment_type', '=', 'receive_money')])
            for user in self.env.company.pb_user_ids:
                if user.partner_id and user.partner_id.email:
                    emails.append(user.partner_id.email)
            email_values = {
                'email_to': ','.join(emails),
            }
            view = self.env.ref("pb_pdc.pb_pdc_payment_form_view", raise_if_not_found=False).sudo()
            view_id = view.id if view else 0
            for record in records:
                if (record.due_date == notify_date_1
                        or record.due_date == notify_date_2
                        or record.due_date == notify_date_3
                        or record.due_date == notify_date_4
                        or record.due_date == notify_date_5):

                    if self.env.company.is_notify_to_customer:
                        # template_download_id = record.env['ir.model.data'].get_object(
                        #     'pb_pdc', 'pb_pdc_company_to_customer_notification_1'
                        #     )
                        template_download_id = self.env.ref('pb_pdc.pb_pdc_company_to_customer_notification_1')
                        record.env['mail.template'].browse(
                            template_download_id.id
                        ).send_mail(record.id, email_layout_xmlid='mail.mail_notification_light', force_send=True)
                    if self.env.company.is_notify_to_user and self.env.company.pb_user_ids:
                        url = ''
                        base_url = record.get_base_url()
                        url = base_url + "/web#id=" + \
                              str(record.id) + \
                              "&&model=pdc.wizard&view_type=form&view_id=" + str(view_id)
                        ctx = {
                            "customer_url": url,
                        }
                        # template_download_id = record.env['ir.model.data'].get_object(
                        #     'pb_pdc', 'pb_pdc_company_to_int_user_notification_1'
                        #     )
                        template_download_id = self.env.ref('pb_pdc.pb_pdc_company_to_int_user_notification_1')
                        self.env['mail.template'].sudo().browse(template_download_id.id).with_context(
                            ctx).send_mail(
                            record.id, email_values=email_values, email_layout_xmlid='mail.mail_notification_light',
                            force_send=True)

    # ==============================
    #    CRON SCHEDULER VENDOR
    # ==============================
    @api.model
    def notify_vendor_due_date(self):
        emails = []
        if self.env.company.is_vendor_due_notify:
            notify_day_1_ven = self.env.company.notify_on_1_vendor
            notify_day_2_ven = self.env.company.notify_on_2_vendor
            notify_day_3_ven = self.env.company.notify_on_3_vendor
            notify_day_4_ven = self.env.company.notify_on_4_vendor
            notify_day_5_ven = self.env.company.notify_on_5_vendor
            notify_date_1_ven = False
            notify_date_2_ven = False
            notify_date_3_ven = False
            notify_date_4_ven = False
            notify_date_5_ven = False
            if notify_day_1_ven:
                notify_date_1_ven = fields.Date.today() + timedelta(days=int(notify_day_1_ven) * -1)
            if notify_day_2_ven:
                notify_date_2_ven = fields.Date.today() + timedelta(days=int(notify_day_2_ven) * -1)
            if notify_day_3_ven:
                notify_date_3_ven = fields.Date.today() + timedelta(days=int(notify_day_3_ven) * -1)
            if notify_day_4_ven:
                notify_date_4_ven = fields.Date.today() + timedelta(days=int(notify_day_4_ven) * -1)
            if notify_day_5_ven:
                notify_date_5_ven = fields.Date.today() + timedelta(days=int(notify_day_5_ven) * -1)

            records = self.search([('payment_type', '=', 'send_money')])
            for user in self.env.company.pb_user_ids_vendor:
                if user.partner_id and user.partner_id.email:
                    emails.append(user.partner_id.email)
            email_values = {
                'email_to': ','.join(emails),
            }
            view = self.env.ref("pb_pdc.pb_pdc_payment_form_view", raise_if_not_found=False)
            view_id = view.id if view else 0
            for record in records:
                if (record.due_date == notify_date_1_ven
                        or record.due_date == notify_date_2_ven
                        or record.due_date == notify_date_3_ven
                        or record.due_date == notify_date_4_ven
                        or record.due_date == notify_date_5_ven):

                    if self.env.company.is_notify_to_vendor:
                        # template_download_id = record.env['ir.model.data'].get_object(
                        #     'pb_pdc', 'pb_pdc_company_to_customer_notification_1'
                        #     )
                        template_download_id = self.env.ref('pb_pdc.pb_pdc_company_to_customer_notification_1')
                        record.env['mail.template'].browse(
                            template_download_id.id
                        ).send_mail(record.id, email_layout_xmlid='mail.mail_notification_light', force_send=True)
                    if self.env.company.is_notify_to_user_vendor and self.env.company.pb_user_ids_vendor:
                        url = ''
                        base_url = record.get_base_url()
                        url = base_url + "/web#id=" + \
                              str(record.id) + \
                              "&&model=pdc.wizard&view_type=form&view_id=" + str(view_id)
                        ctx = {
                            "customer_url": url,
                        }
                        # template_download_id = record.env['ir.model.data'].get_object(
                        #     'pb_pdc', 'pb_pdc_company_to_int_user_notification_1'
                        #     )
                        template_download_id = self.env.ref('pb_pdc.pb_pdc_company_to_int_user_notification_1')
                        self.env['mail.template'].sudo().browse(template_download_id.id).with_context(
                            ctx).send_mail(
                            record.id, email_values=email_values, email_layout_xmlid='mail.mail_notification_light',
                            force_send=True)

    # Multi Action Starts for change the state of PDC check
    def action_set_draft(self):
        self.sudo().write({
            'state': 'draft',
        })

    def action_delete_related_moves(self):

        for model in self:
            move_ids = self.env['account.move'].search([('pdc_id', '=', model.id)])
            for move in move_ids:
                move.button_draft()
                lines = self.env['account.move.line'].search([('move_id', '=', move.id)])
                lines.unlink()

            model.sudo().write({
                'done_date': False
            })

            for move in move_ids:
                self.env.cr.execute(""" delete from account_move where id =%s""" % (move.id,))

    def action_state_register(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'draft':
                    for active_model in active_models:
                        active_model.action_register()
                else:
                    raise UserError(
                        "Only Draft state PDC check can switch to Register state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_return(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'registered':
                    for active_model in active_models:
                        active_model.action_returned()
                else:
                    raise UserError(
                        "Only Register state PDC check can switch to return state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_deposit(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_deposited()
                else:
                    raise UserError(
                        "Only Register,Return and Bounce state PDC check can switch to Deposit state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_bounce(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_bounced()
                else:
                    raise UserError(
                        "Only Deposit state PDC check can switch to Bounce state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_done(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_done()
                else:
                    raise UserError(
                        "Only Deposit state PDC check can switch to Done state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_cancel(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_cancel()
                else:
                    raise UserError(
                        "Only Register,Return and Bounce state PDC check can switch to Cancel state!!")
            else:
                raise UserError(
                    "States must be same!!")


class PDCWizardLine(models.Model):
    _name = 'pdc.wizard.line'
    _description = 'PDC Wizard Per-Invoice Allocation'

    wizard_id = fields.Many2one('pdc.wizard', required=True, ondelete='cascade')
    invoice_id = fields.Many2one('account.move', required=True)
    custom_amount = fields.Monetary(string='Allocated Amount', required=True, default=0.0)
    currency_id = fields.Many2one(related='wizard_id.currency_id', store=True, readonly=True)
