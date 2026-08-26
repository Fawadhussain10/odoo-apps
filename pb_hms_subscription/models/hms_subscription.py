# -*- coding: utf-8 -*-

from odoo import _, api, models, fields
from odoo.exceptions import ValidationError, UserError
from datetime import date, datetime, timedelta

class PbHmsSubscription(models.Model):
    _name = 'pb.hms.subscription'
    _description = "HMS Subscription"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'pb.hms.mixin']
    _order = 'id desc'

    STATES = {'active': [('readonly', True)], 'done': [('readonly', True)], 'cancel': [('readonly', True)]}

    @api.depends('res_model_id')
    def _data_count(self):
        Invoice = self.env['account.move']
        record_ids = 0
        for rec in self:
            if rec.res_model_id and rec.res_model_id.model:
                record_ids = self.env[rec.res_model_id.model].search_count([('subscription_id','=',rec.id)])
            rec.record_count = record_ids
            rec.remaining_service = rec.allowed_no_service - record_ids
            rec.invoice_count = Invoice.search_count([('subscription_id', '=', rec.id)])

    number = fields.Char(string='Number', required=True, readonly=True, default="/", tracking=True)
    name = fields.Char(string='Name', related="contract_id.name", readonly=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('done', 'Closed'),
        ('cancel', 'Cancelled'),
    ], string='Status', copy=False, default='draft', tracking=True)

    note = fields.Text('Description')
    patient_id = fields.Many2one('hms.patient', string='Patient', ondelete="cascade", required=True)
    allowed_no_service = fields.Integer("Allowed No of Services")
    remaining_service = fields.Integer("Remaining No of Services", compute="_data_count")
    contract_id = fields.Many2one("pb.hms.contract", string="Contract", required=True)
    product_id = fields.Many2one("product.product", related="contract_id.product_id", string="Product",readonly=True)
    start_date = fields.Datetime("Start Date", default=fields.Datetime.now)
    end_date = fields.Datetime("End Date", required=True, default=fields.Datetime.now)
    invoice_count = fields.Integer(string='# of Invoices', compute='_data_count', readonly=True)
    invoice_ids = fields.One2many("account.move", "subscription_id", string='Invoices', copy=False)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user.id)

    res_model_id = fields.Many2one('ir.model', related="contract_id.res_model_id", string='Model', readonly=True)
    record_count = fields.Integer(string='# of Operations', compute='_data_count', readonly=True)
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Company', default=lambda self: self.env.company)
    pb_type = fields.Selection([
        ('full', 'Full In Advance'),
        ('discount', 'Price-list Based Discount'),
    ], string='Offer Type', copy=False, default='full', tracking=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', check_company=True, 
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['number'] = self.env['ir.sequence'].next_by_code('pb.hms.subscription') or '/'
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_('You cannot delete an record which is not draft or canceled.'))
        return super(PbHmsSubscription, self).unlink()

    @api.depends('name', 'number', 'remaining_service', 'allowed_no_service')
    def _compute_display_name(self):
        for record in self:
            record.display_name = " [%(number)s] %(name)s (%(count)s)" % {
                'name': record.name,
                'number': record.number,
                'count': _('%g remaining out of %g') % (record.remaining_service or 0.0, record.allowed_no_service or 0.0)
            }

    def action_confirm(self):
        self.state = 'active'

    def action_done(self):
        self.state = 'done'

    def action_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'cancel'

    @api.onchange("contract_id")
    def onchange_contract_id(self):
        if self.contract_id:
            self.allowed_no_service = self.contract_id.no_service
            self.pb_type = self.contract_id.pb_type
            self.pricelist_id = self.contract_id.pricelist_id and self.contract_id.pricelist_id.id or False

    def action_view_related_records(self):
        record_ids = self.env[self.res_model_id.model].search([('subscription_id','=',self.id)])
        return {
            'name':'Records',
            'view_type': 'form',
            'view_mode': 'list,form',
            'res_model': self.res_model_id.model,
            'target': 'current',
            'type': 'ir.actions.act_window',
            'domain': [('id','in', record_ids.ids)],
            'nodestroy': True,
        }

    def action_invoice_create(self):
        product_id = self.product_id
        if not product_id:
            raise UserError(_("Please Set proper contract first."))
        product_data = [{
            'product_id': product_id,
            'name': product_id.name + '\n' + 'Subscription No: ' + self.number,
            'price_unit': self.contract_id.price,
        }]
        inv_data = {}
        invoice = self.pb_create_invoice(partner=self.patient_id.partner_id, patient=self.patient_id, product_data=product_data, inv_data=inv_data)
        invoice.subscription_id = self.id

    def action_view_invoice(self):
        invoices = self.invoice_ids
        action = self.pb_action_view_invoice(invoices)
        return action

    #This is lazy option to close subscriptions
    @api.model
    def close_subscriptions(self):
        subscriptions = self.search([('state','=','active'),('end_date','<=',fields.Datetime.now())])
        for subscription in subscriptions:
            subscription.action_done()

        subscriptions = self.search([('state','=','active'),('end_date','>=',fields.Datetime.now())])
        for subscription in subscriptions:
            if subscription.remaining_service <= 0:
                subscription.action_done()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: