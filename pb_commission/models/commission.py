# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError

class PbCommissionRole(models.Model):
    _name = 'pb.commission.role'
    _description = 'Commission Role'

    name = fields.Char(string='Name', required=True)
    description = fields.Text("Description")
    commission_rule_ids = fields.One2many("pb.commission.rule", "role_id", string="Commission Rules")
    commission_target_rule_ids = fields.One2many("pb.commission.target.rule", "role_id", string="Commission Target Rules")


class PbCommissionRule(models.Model):
    _name = 'pb.commission.rule'
    _description = 'Commission Rule'
    _order = "sequence"

    sequence = fields.Integer(string='Sequence', default=50)
    rule_type = fields.Selection([
        ('role', 'Role'),
        ('user', 'User'),
    ], string='Rule Type', copy=False, default='role', required=True)
    role_id = fields.Many2one('pb.commission.role', string='Role')
    user_id = fields.Many2one('res.users', string='User')
    partner_id = fields.Many2one('res.partner', string='Partner')
    rule_on = fields.Selection([
        ('product_category', 'Product Category'),
        ('product', 'Product'),
    ], string='Rule On', copy=False, default='product_category', required=True)
    product_category_id = fields.Many2one('product.category', string='Product Category')
    product_id = fields.Many2one('product.template', string='Product')
    percentage = fields.Float('Percentage')
    amount = fields.Float('Amount')
    type = fields.Selection([
        ('percentage', 'Percentage'),
        ('amount', 'Amount'), 
    ], string='Type', default='percentage')
    description = fields.Text("Description")

class PbCommissionTargetRule(models.Model):
    _name = 'pb.commission.target.rule'
    _description = 'Commission Target Rule'
    _order = "sequence"

    sequence = fields.Integer(string='Sequence', default=50)
    rule_type = fields.Selection([
        ('role', 'Role'),
        ('user', 'User'),
    ], string='Rule Type', copy=False, default='role', required=True)
    role_id = fields.Many2one('pb.commission.role', string='Role')
    user_id = fields.Many2one('res.users', string='User')
    partner_id = fields.Many2one('res.partner', string='Partner')

    target_amount = fields.Float('Target Amount', help="Sum of total Commission on Amount", required=True)
    percentage = fields.Float('Percentage to Release', required=True)
    description = fields.Text("Description")
 

class PartnerCommission(models.Model):
    _name = 'pb.commission'
    _description = 'Partner Commission'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "id desc"

    @api.depends('payment_invoice_id', 'payment_invoice_id.state', 'payment_invoice_id.payment_state', 'state')
    def _payment_status(self):
        for rec in self:
            if not rec.payment_invoice_id:
                rec.payment_status = 'not_inv'
            elif rec.payment_invoice_id.state=='draft':
                rec.payment_status = 'draft'
            elif rec.payment_invoice_id.state=='cancel':
                rec.payment_status = 'cancel'
            elif rec.payment_invoice_id.payment_state=='paid':
                rec.payment_status = 'paid'
            else:
                rec.payment_status = 'open'

    STATES = {'done': [('readonly', True)], 'cancel': [('readonly', True)]}

    name = fields.Char(string='Name',readonly=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('cancel', 'Canceled'),
    ], string='Status', copy=False, default='draft', tracking=True)
    date = fields.Date(string="Date", default=fields.Date.today)
    partner_id = fields.Many2one('res.partner', 'Partner', required=True, tracking=True)
    target_based_commission = fields.Boolean(related="partner_id.target_based_commission", store=True)
    invoice_id = fields.Many2one('account.move', 'Invoice', copy=False)
    invoice_partner_id = fields.Many2one('res.partner', related="invoice_id.partner_id", string='Customer', readonly=True, store=True)
    invoice_journal_id = fields.Many2one('account.journal', related="invoice_id.journal_id", string='Invoice Journal', readonly=True, store=True)

    commission_on = fields.Float('Commission On')
    commission_amount = fields.Float('Commission Amount')
    payable_amount = fields.Float('Payable Amount')
    invoice_line_id = fields.Many2one('account.move.line', 'Payment Invoice Line')
    payment_invoice_id = fields.Many2one('account.move', related="invoice_line_id.move_id", string='Payment Invoice', readonly=True)
    payment_status = fields.Selection([
        ('not_inv', 'Not Paid'),
        ('draft', 'Draft Payment'),
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('cancel', 'Canceled'), 
    ], string='Payment Status', copy=False, default='not_inv', readonly=True, compute="_payment_status", store=True)
    payment_invoice_journal_id = fields.Many2one('account.journal', related="invoice_line_id.move_id.journal_id", string='Payment Journal', readonly=True, store=True)
    note = fields.Text("Note")
    commission_sheet_id = fields.Many2one('pb.commission.sheet', 'Sheet')
    company_id = fields.Many2one('res.company', related="invoice_id.company_id", 
        string='Company', store=True)

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_('You cannot delete an record which is not draft or cancelled.'))
        return super(PartnerCommission, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.commission')
        res = super().create(vals_list)
        for record in res:
            record.pb_update_amount_by_rules()
        return res

    def action_done(self):
        for rec in self:
            rec.state = 'done'
            rec.pb_update_amount_by_rules()

    def action_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'cancel'

    def pb_update_amount_by_rules(self):
        Rule = self.env['pb.commission.target.rule']
        for rec in self:
            if rec.target_based_commission:
                partner = rec.partner_id
                if rec.commission_sheet_id:
                    total_commission_base_amount = rec.commission_sheet_id.total_commission_base_amount
                    matching_rule = Rule
                    if partner.commission_target_rule_ids:
                        target_rule_ids = partner.commission_target_rule_ids.ids
                        matching_rule = Rule.search([('id','in',target_rule_ids),
                            ('target_amount','<=',total_commission_base_amount)], order='sequence desc', limit=1)
                        if not matching_rule:
                            rec.payable_amount = 0

                    elif partner.commission_role_id and partner.commission_role_id.commission_target_rule_ids:
                        target_rule_ids = partner.commission_role_id.commission_target_rule_ids.ids
                        matching_rule = Rule.search([('id','in', target_rule_ids),
                            ('target_amount','<=',total_commission_base_amount)], order='sequence desc', limit=1)

                    if matching_rule:
                        rec.payable_amount = (matching_rule.percentage * rec.commission_amount)/100
            else:
                rec.payable_amount = rec.commission_amount

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: