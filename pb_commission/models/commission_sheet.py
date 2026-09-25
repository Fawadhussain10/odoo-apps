# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError


class PbCommissionSheet(models.Model):
    _name = 'pb.commission.sheet'
    _description = 'Commission Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "id desc"

    @api.depends('payment_invoice_id','payment_invoice_id.payment_state')
    def _payment_status(self):
        for rec in self:
            if not rec.payment_invoice_id:
                rec.payment_status = 'no_bill'
            else:
                rec.payment_status = rec.payment_invoice_id.payment_state

    @api.depends('commission_line_ids','commission_line_ids.commission_amount','commission_line_ids.payable_amount','commission_line_ids.commission_on')
    def _pb_amount_data(self):
        for record in self:
            amount_total = 0
            total_commission_amount = 0
            total_commission_base_amount = 0
            for line in record.commission_line_ids:
                amount_total += line.payable_amount
                total_commission_amount += line.commission_amount
                total_commission_base_amount += line.commission_on

            record.amount_total = amount_total
            record.total_commission_amount = total_commission_amount
            record.total_commission_base_amount = total_commission_base_amount

    STATES = {'done': [('readonly', True)], 'cancel': [('readonly', True)]}

    name = fields.Char(string='Name', readonly=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed','Confirmed'),
        ('done', 'done'),
        ('cancel', 'cancel')
    ], string='Status', copy=False, default='draft', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Partner', index=True, required=True, tracking=True)
    date_from = fields.Date(required=True, default=fields.Date.today)
    date_to = fields.Date(required=True, default=fields.Date.today)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user.id, required=True, tracking=True)
    commission_line_ids = fields.One2many('pb.commission', 'commission_sheet_id', 
        string='Lines')
    payment_invoice_id = fields.Many2one('account.move', string='Payment Invoice', readonly=True)
    payment_status = fields.Selection([('no_bill', 'No Bill'),
            ('not_paid', 'Not Paid'),
            ('in_payment', 'In Payment'),
            ('paid', 'Paid'),
            ('partial', 'Partially Paid'),
            ('reversed', 'Reversed'),
            ('invoicing_legacy', 'Invoicing App Legacy')], string='Payment Status', copy=False, default='no_bill', readonly=True, compute="_payment_status", store=True)    
    note = fields.Text("Note")
    company_id = fields.Many2one('res.company',
        string='Hospital', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related="company_id.currency_id", string='Currency', store=True)
    amount_total = fields.Float(compute="_pb_amount_data", string="Total Payable", store=True)
    total_commission_amount = fields.Float(compute="_pb_amount_data", string="Total Commission", store=True)
    total_commission_base_amount = fields.Float(compute="_pb_amount_data", string="Total Commission On", store=True)

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_('You cannot delete an record which is not draft or cancelled.'))
        return super(PbCommissionSheet, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.commission.sheet')
        return super().create(vals_list)

    def action_draft(self):
        self.state = 'draft'

    def action_confirm(self):
        self.state = 'confirmed'
        self._pb_amount_data()
        self.commission_line_ids.pb_update_amount_by_rules()

    def action_done(self):
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancel'

    def get_data(self):
        self.commission_line_ids.write({'commission_sheet_id': False})
        commission_lines = self.env['pb.commission'].search([
            ('partner_id','=',self.partner_id.id),
            ('date','>=',self.date_from),
            ('date','<=',self.date_to),
            ('commission_sheet_id','=',False)])
        commission_lines.write({'commission_sheet_id': self.id})
        self._pb_amount_data()
        self.commission_line_ids.pb_update_amount_by_rules()

    def create_payment_bill(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_commission.action_view_commission_bill")
        action['context'] = {
            'active_model':'pb.commission', 
            'active_ids': self.commission_line_ids.ids, 
            'commission_sheet_id': self.id,
            'default_groupby_partner': True,
            'default_hide_groupby_partner': True,
        }
        return action

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: