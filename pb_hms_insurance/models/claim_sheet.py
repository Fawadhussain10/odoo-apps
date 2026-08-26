# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import base64
from lxml import etree


class PbClaimSheet(models.Model):
    _name = 'pb.claim.sheet'
    _description = 'Claim Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.depends('claim_line_ids','claim_line_ids.amount_total')
    def _amount_all(self):
        for record in self:
            amount_total = 0
            for line in record.claim_line_ids:
                amount_total += line.amount_total
            record.amount_total = amount_total

    STATES = {'done': [('readonly', True)], 'cancel': [('readonly', True)]}

    name = fields.Char(string='Name', readonly=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('cancel', 'Cancel'),
    ], string='Status', copy=False, default='draft', tracking=True)
    insurance_company_id = fields.Many2one('hms.insurance.company', string='Insurance Company', index=True, required=True, tracking=True)
    date = fields.Date(string="Clam Date", required=True, default=fields.Date.today)
    date_from = fields.Date(required=True, default=fields.Date.today)
    date_to = fields.Date(required=True, default=fields.Date.today)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user.id, required=True, tracking=True)
    claim_line_ids = fields.One2many('account.move', 'claim_sheet_id', string='Lines')
    note = fields.Text("Note")
    company_id = fields.Many2one('res.company',
        string='Hospital', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related="company_id.currency_id",
        string='Currency')
    amount_total = fields.Float(compute="_amount_all", string="Total")

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_('You cannot delete an record which is not draft or cancelled.'))
        return super(PbClaimSheet, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.claim.sheet')
        return super().create(vals_list)

    def action_done(self):
        self.state = 'done'

    def action_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'cancel'

    def get_data(self):
        self.claim_line_ids.write({'claim_sheet_id': False})
        claim_lines = self.env['account.move'].search([
            ('insurance_company_id','=',self.insurance_company_id.id),
            ('invoice_date','>=',self.date_from),
            ('invoice_date','<=',self.date_to),
            ('claim_sheet_id','=',False),
            ('move_type','=', 'out_invoice'),
            ('state','=','posted')])
        claim_lines.write({'claim_sheet_id': self.id})