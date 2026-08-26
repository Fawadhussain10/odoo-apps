# -*- coding: utf-8 -*-

from odoo import api, fields, models,_
from odoo.exceptions import UserError
from functools import partial
from odoo.tools.misc import formatLang


class PbInvoiceSummary(models.Model):
    _name = 'pb.invoice.summary'
    _description = "Invoice Summary"
    _inherit = ['mail.thread']

    def _compute_data_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)
            rec.payment_count = len(rec.payment_ids)

    @api.depends('payment_ids','move_ids')
    def _amount_all(self):
        """
        Compute the total amounts of the record.
        """
        for record in self:
            amount_untaxed = 0.0
            amount_tax = 0
            amount_total_signed = 0
            for inv in record.move_ids:
                amount_untaxed += inv.amount_untaxed_signed
                amount_tax += inv.amount_tax_signed
                amount_total_signed += inv.amount_total_signed

            record.amount_untaxed = amount_untaxed
            record.amount_tax = amount_tax
            record.amount_total = amount_total_signed

            payment_total = 0
            payment_due = 0
            for payment in record.payment_ids:
                payment_total += payment.amount_company_currency_signed

            record.payment_total = payment_total
            record.payment_due = (amount_untaxed + amount_tax) - payment_total

    name = fields.Char(readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', index=True, store=True)
    origin = fields.Char()
    date_from = fields.Date(required=True, default=fields.Date.today)
    date_to = fields.Date(required=True, default=fields.Date.today)
    description = fields.Text("Description")
    state = fields.Selection([
        ('draft','Draft'),
        ('done','done'),
        ], string="Status", tracking=True , copy=False, default="draft")
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user.id, required=True)
    move_ids = fields.One2many('account.move', 'pb_invoice_summary_id', 
        string='Moves')
    move_count = fields.Integer(compute='_compute_data_count', string='# Moves')
    payment_count = fields.Integer(compute='_compute_data_count', string='# Payments')
    payment_ids = fields.One2many('account.payment', 'pb_invoice_summary_id', 
        string='Payments')

    line_ids = fields.One2many('pb.invoice.summary.line', 'pb_invoice_summary_id', string='Invoice Lines')
    categ_line_ids = fields.One2many('pb.invoice.summary.line', 'pb_invoice_summary_categ_id', string='Lines', domain="[('display_type','=', 'line_section')]")

    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all',  tracking=True)
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all',  tracking=True)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", related='company_id.currency_id', string="Currency", readonly=True, required=True)

    payment_total = fields.Monetary(string='Total Payment', store=True, readonly=True, compute='_amount_all')
    payment_due = fields.Monetary(string='Due Payment', store=True, readonly=True, compute='_amount_all')
    print_date_range = fields.Boolean("Print Date Range", default=False)
    print_lines = fields.Boolean("Print Lines", default=False)

    def action_view_moves(self):
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        action['domain']= [('pb_invoice_summary_id','in',self.ids)]
        action['context'] = {
            'default_pb_invoice_summary_id': self.id,
        }
        return action

    def action_view_payments(self):
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action['domain']= [('pb_invoice_summary_id','in',self.ids)]
        action['context'] = {
            'default_pb_invoice_summary_id': self.id,
        }
        return action

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('pb.invoice.summary') or ''
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_('You cannot delete an record in Done State.'))
        return super(PbInvoiceSummary, self).unlink()

    def get_data(self):
        self.payment_ids.write({'pb_invoice_summary_id': False})
        payments = self.env['account.payment'].search([
            ('partner_id','=',self.partner_id.id),
            ('date','>=',self.date_from),
            ('date','<=',self.date_to),
            ('state','in',['sent','posted','reconciled']),
            ('pb_invoice_summary_id','=',False)])

        payments.write({'pb_invoice_summary_id': self.id})
        self.move_ids.write({'pb_invoice_summary_id': False})

        invoices = self.env['account.move'].search([
            ('partner_id','=',self.partner_id.id),
            ('invoice_date','>=',self.date_from),
            ('invoice_date','<=',self.date_to),
            ('state','in',['draft','posted']),
            ('pb_invoice_summary_id','=',False),
            ('move_type', 'in', ['out_refund','out_invoice'])])
        invoices.write({'pb_invoice_summary_id': self.id})
        self.print_date_range = True
        self.update_data()

    def update_data(self):
        SummaryLine = self.env['pb.invoice.summary.line']
        MoveLine = self.env['account.move.line']
        Payment = self.env['account.payment']

        self.line_ids.unlink()
        moves = MoveLine.search([
            ('move_id','in',self.move_ids.ids),
            ('display_type', 'in', ('product', 'line_section', 'line_note'))])

        self.origin = ', '.join(map(lambda x: x.name, self.move_ids))

        categ_group = MoveLine.read_group([('id', 'in', moves.ids)] , fields=['pb_product_category_id'], groupby=['pb_product_category_id'])
        for group in categ_group:
            SummaryLine.create({
                'display_type' : 'line_section',
                'name': group['pb_product_category_id'] and group['pb_product_category_id'][1] or _("Undefined"),
                'pb_invoice_summary_id': self.id,
                'pb_invoice_summary_categ_id': self.id,
                'pb_product_category_id': group['pb_product_category_id'] and group['pb_product_category_id'][0] or False,
            })
            pb_product_category_id = group['pb_product_category_id'] and int(group['pb_product_category_id'][0]) or False

            category_moves = MoveLine.search([
                ('id','in',moves.ids),
                ('pb_product_category_id', '=', pb_product_category_id)])

            for line in category_moves:
                sign = -1 if line.move_id.move_type=='out_refund' else 1
                SummaryLine.create({
                    'move_line_id': line.id,
                    'pb_invoice_summary_id' : self.id,
                    'name': line.name or "Undefined",
                    'tax_id': [(6, 0, line.tax_ids.ids)],
                    'product_id': line.product_id and line.product_id.id or False,
                    'pb_product_category_id': line.product_id and line.product_id.categ_id.id or False,
                    'quantity': line.quantity,
                    'product_uom_id': line.product_uom_id and line.product_uom_id.id or False,
                    'price_unit': line.price_unit * sign,
                    'discount': line.discount,
                })
        self._amount_all()

    def action_done(self):
        for rec in self:
            rec.get_data()
            rec.state = 'done'

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'

    def _get_tax_amount_by_group(self):
        self.ensure_one()
        res = {}
        for line in self.line_ids:
            base_tax = 0
            for tax in line.tax_id:
                group = tax.tax_group_id
                res.setdefault(group, {'amount': 0.0, 'base': 0.0})
                # FORWARD-PORT UP TO SAAS-17
                price_reduce = line.price_unit * (1.0 - line.discount / 100.0)
                taxes = tax.compute_all(price_reduce + base_tax, quantity=line.quantity,
                                         product=line.product_id, partner=self.create_uid.partner_id)['taxes']
                for t in taxes:
                    res[group]['amount'] += t['amount']
                    res[group]['base'] += t['base']
                if tax.include_base_amount:
                    base_tax += tax.compute_all(price_reduce + base_tax, quantity=1, product=line.product_id,
                                                partner=self.create_uid.partner_id)['taxes'][0]['amount']
        res = sorted(res.items(), key=lambda l: l[0].sequence)
        res = [(l[0].name, l[1]['amount'], l[1]['base'], len(res)) for l in res]
        return res


class PbInvoiceSummaryLine(models.Model):
    _name = 'pb.invoice.summary.line'
    _description = "Invoice Summary Lines"

    @api.depends('quantity', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        """
        Compute the amounts of the line.
        """
        for line in self:
            if not line.display_type:
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                taxes = line.tax_id.compute_all(price, line.pb_invoice_summary_id.currency_id, line.quantity, product=line.product_id, partner=line.pb_invoice_summary_id.create_uid.partner_id)
                line.update({
                    'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                    'price_total': taxes['total_included'],
                    'price_subtotal': taxes['total_excluded'],
                })
            else:
                line.price_tax = 0
                line.price_total = 0
                line.price_subtotal = 0

    def _compute_categ_total(self):
        for rec in self:
            lines = self.search([
                ('pb_invoice_summary_id','=', rec.pb_invoice_summary_id.id),
                ('pb_product_category_id','=', rec.pb_product_category_id.id)])
            categ_total = 0
            for line in lines:
                categ_total += line.price_total
            rec.categ_total = categ_total

    pb_invoice_summary_id = fields.Many2one('pb.invoice.summary', string='Invoice Summary', required=True, ondelete="cascade")
    pb_invoice_summary_categ_id = fields.Many2one('pb.invoice.summary', string='Invoice Summary For Category', ondelete="cascade")

    name = fields.Text(string='Description', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)], change_default=True, ondelete='restrict')
    quantity = fields.Float(string='Quantity', digits=('Product Unit of Measure'), default=1.0)
    product_uom_category_id = fields.Many2one('uom.uom', compute='_compute_product_uom_category_id')

    @api.depends('product_id.uom_id')
    def _compute_product_uom_category_id(self):
        for rec in self:
            uom = rec.product_id.uom_id
            rec.product_uom_category_id = uom.relative_uom_id or uom
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', domain="['|', ('id', '=', product_uom_category_id), ('relative_uom_id', '=', product_uom_category_id)]")
    price_unit = fields.Float()
    discount = fields.Float()
    tax_id = fields.Many2many('account.tax', string='Taxes', domain=['|', ('active', '=', False), ('active', '=', True)])

    company_id = fields.Many2one(related='pb_invoice_summary_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, string='Currency', readonly=True)
    price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', readonly=True, store=True, currency_field='currency_id')
    price_tax = fields.Monetary(compute='_compute_amount', string='Taxes Amount', readonly=True, store=True, currency_field='currency_id')
    price_total = fields.Monetary(compute='_compute_amount', string='Total', readonly=True, store=True, currency_field='currency_id')
    
    display_type = fields.Selection([
        ('line_section', "Section")], default=False, help="Technical field for UX purpose.")
    pb_product_category_id = fields.Many2one('product.category', string='Product Category')
    move_line_id = fields.Many2one('account.move.line', string='Move')
    categ_total = fields.Monetary(compute='_compute_categ_total', string='Category Total', readonly=True, currency_field='currency_id')

    def action_view_related_lines(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_invoice_summary.action_pb_invoice_summary_lines")
        action['domain']= [('pb_invoice_summary_id','=',self.pb_invoice_summary_id.id),('pb_product_category_id','=',self.pb_product_category_id.id),('display_type','!=','line_section')]
        return action

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: