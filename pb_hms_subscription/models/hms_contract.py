# -*- coding: utf-8 -*-

from odoo import _, api, models, fields
from odoo.exceptions import ValidationError, UserError
from datetime import date, datetime, timedelta


class PbHmsContract(models.Model):
    _name = 'pb.hms.contract'
    _description = "HMS Contract"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    STATES = {'active': [('readonly', True)], 'done': [('readonly', True)], 'cancel': [('readonly', True)]}

    def _subscription_count(self):
        for rec in self: 
            rec.subscription_count = len(rec.subscription_ids.ids)

    name = fields.Char(string='Name', required=True, tracking=True)
    number = fields.Char(string='Number', required=True, readonly=True, default="/")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('done', 'Closed'),
        ('cancel', 'Cancelled'),
    ], string='Status', copy=False, default='draft', tracking=True)
    note = fields.Html('Description')
    product_id = fields.Many2one("product.product", "Product", required=True)
    price = fields.Integer(string='Price')
    no_service = fields.Integer("No of Services")
    subscription_ids = fields.One2many("pb.hms.subscription", 'contract_id', string='Subscriptions', readonly=True, copy=False)
    subscription_count = fields.Integer(string='# of Subscription', compute='_subscription_count', readonly=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user.id)
    res_model_id = fields.Many2one('ir.model', string='Model', ondelete="cascade", required=True)
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Company', default=lambda self: self.env.company)
    pb_type = fields.Selection([
        ('full', 'Full In Advance'),
        ('discount', 'Price-list Based Discount'),
    ], string='Offer Type', copy=False, default='full', tracking=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', check_company=True, 
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="If you change the pricelist, only newly added lines will be affected.")

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_('You cannot delete an record which is not draft.'))
        return super(PbHmsContract, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['number'] = self.env['ir.sequence'].next_by_code('pb.hms.contract') or '/'
        return super().create(vals_list)

    def action_confirm(self):
        self.state = 'active'

    def action_done(self):
        self.state = 'done'

    def action_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'cancel'

    @api.onchange("product_id")
    def onchange_product_id(self):
        domain = {}
        if self.product_id:
            
            self.price = self.product_id.lst_price

    def action_view_subscriptions(self):
        subscriptions = self.subscription_ids
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_subscription.pb_hms_subscription_action")
        if len(subscriptions) > 1:
            action['domain'] = [('id', 'in', subscriptions.ids)]
        elif len(subscriptions) == 1:
            action['views'] = [(self.env.ref('pb_hms_subscription.pb_hms_subscription_form_view').id, 'form')]
            action['res_id'] = subscriptions.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        action.update({'context': {'default_contract_id': self.id}})
        return action

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: