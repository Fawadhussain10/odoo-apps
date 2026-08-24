# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class SaleTender(models.Model):
    _name = 'sale.tender'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Tender'
    _order = 'id desc'

    name = fields.Char(
        string='Tender', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Salesperson', tracking=True,
        default=lambda self: self.env.user)
    purpose = fields.Selection([
        ('bid_earnest_money', 'Bid Money/Earnest Money'),
        ('performance_security', 'Performance Security'),
        ('advance_payment_security', 'Advance Payment Security'),
    ], string='Purpose', required=True, tracking=True)
    tender_number = fields.Char(string='Tender Number', tracking=True)
    tender_date = fields.Date(
        string='Tender Date', default=fields.Date.context_today, tracking=True)
    mode_of_instrument = fields.Selection([
        ('cash', 'Cash'),
        ('pay_order_cdr', 'Pay Order/CDR'),
        ('bank_guarantee', 'Bank Guarantee'),
        ('insurance_guarantee', 'Insurance Guarantee'),
        ('online_payment', 'Online Payment'),
    ], string='Mode of Instrument', tracking=True)
    attachment_ids = fields.One2many(
        'sale.tender.attachment', 'tender_id', string='Attachments')
    order_line_ids = fields.One2many(
        'sale.tender.line', 'tender_id', string='Order Lines')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'Manager Approval'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('converted', 'Converted to Quotation'),
    ], string='Status', default='draft', copy=False, tracking=True)
    sale_order_id = fields.Many2one(
        'sale.order', string='Quotation', readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', store=True)
    amount_untaxed = fields.Monetary(
        string='Untaxed Amount', compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(
        string='Taxes', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(
        string='Total', compute='_compute_amounts', store=True, tracking=True)

    @api.depends('order_line_ids.price_subtotal', 'order_line_ids.price_total')
    def _compute_amounts(self):
        for tender in self:
            tender.amount_untaxed = sum(tender.order_line_ids.mapped('price_subtotal'))
            tender.amount_total = sum(tender.order_line_ids.mapped('price_total'))
            tender.amount_tax = tender.amount_total - tender.amount_untaxed

    _EDITABLE_ONLY_IN_DRAFT = {
        'partner_id', 'user_id', 'purpose', 'mode_of_instrument', 'tender_number',
        'tender_date', 'order_line_ids', 'attachment_ids',
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.tender') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if self._EDITABLE_ONLY_IN_DRAFT & set(vals.keys()):
            for tender in self:
                if tender.state != 'draft':
                    raise UserError(_(
                        'This tender is no longer in Draft and cannot be edited. '
                        'Reset it to Draft first.'))
        return super().write(vals)

    def _check_is_approver(self):
        if not self.env.user.has_group('sales_tender.sale_tender_group_approver'):
            raise AccessError(_('Only a Tender Approver can accept or reject tenders.'))

    def action_submit_for_approval(self):
        for tender in self:
            if tender.state != 'draft':
                raise UserError(_('Only draft tenders can be submitted for manager approval.'))
        self.write({'state': 'to_approve'})

    def action_accept(self):
        self._check_is_approver()
        for tender in self:
            if tender.state != 'to_approve':
                raise UserError(_('Only tenders awaiting manager approval can be accepted.'))
        self.write({'state': 'accepted'})

    def action_reject(self):
        self._check_is_approver()
        for tender in self:
            if tender.state != 'to_approve':
                raise UserError(_('Only tenders awaiting manager approval can be rejected.'))
        self.write({'state': 'rejected'})

    def action_reset_to_draft(self):
        for tender in self:
            if tender.state == 'converted':
                raise UserError(
                    _('A tender that has been converted to a quotation cannot be reset to draft.'))
        self.write({'state': 'draft'})

    def action_convert_to_quotation(self):
        self.ensure_one()
        if self.state != 'accepted':
            raise UserError(_('Only an accepted tender can be converted to a quotation.'))
        if self.sale_order_id:
            raise UserError(_('This tender has already been converted to a quotation.'))

        order_line_vals = [(0, 0, {
            'product_id': line.product_id.id,
            'name': line.name,
            'product_uom_qty': line.product_uom_qty,
            'product_uom_id': line.product_uom.id or line.product_id.uom_id.id,
            'price_unit': line.price_unit,
            'tax_ids': [(6, 0, line.tax_id.ids)],
        }) for line in self.order_line_ids]

        order = self.env['sale.order'].sudo().create({
            'partner_id': self.partner_id.id,
            'client_order_ref': self.tender_number,
            'origin': self.name,
            'company_id': self.company_id.id,
            'user_id': self.user_id.id,
            'order_line': order_line_vals,
            'tender_id': self.id,
            'date_order': fields.Datetime.to_datetime(self.tender_date),
        })

        attachment_vals = []
        for line in self.attachment_ids.filtered('datas'):
            attachment_vals.append({
                'name': line.filename or line.name or line.attachment_type,
                'datas': line.datas,
                'res_model': 'sale.order',
                'res_id': order.id,
            })
        if attachment_vals:
            attachments = self.env['ir.attachment'].create(attachment_vals)
            order.sudo().message_post(
                body=_('Attachments carried over from tender %s.', self.name),
                attachment_ids=attachments.ids,
            )

        self.write({'sale_order_id': order.id, 'state': 'converted'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Quotation'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': order.id,
        }

    def action_view_quotation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quotation'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }
