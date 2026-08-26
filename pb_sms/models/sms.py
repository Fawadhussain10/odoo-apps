# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

import urllib
from urllib.request import Request, urlopen
import ssl

class PbSms(models.Model):
    _name = 'pb.sms'
    _description = 'SMS'
    _rec_name = 'msg'

    def _get_url(self):
        for rec in self:
            prms = {
                rec.company_id.sms_sms_user_name_param: rec.company_id.sms_user_name,
                rec.company_id.sms_password_param: rec.company_id.sms_password,
                rec.company_id.sms_sender_param: rec.company_id.sms_sender_id,
                rec.company_id.sms_receiver_param: rec.mobile,
                rec.company_id.sms_message_param: rec.msg
            }
            if rec.company_id.sms_templateid_param:
                prms[rec.company_id.sms_templateid_param] = rec.templateid

            params = urllib.parse.urlencode(prms)
            rec.name = rec.company_id.sms_url + "?" + params + (rec.company_id.sms_extra_param or '')

    partner_id = fields.Many2one('res.partner', 'Partner', ondelete="cascade")
    name = fields.Text(string='SMS Request URl', compute="_get_url")
    msg =  fields.Text(string='SMS Text',required=True)
    mobile =  fields.Char(string='Destination Number', required=True)
    state =  fields.Selection([
        ('draft', 'Queued'),
        ('sent', 'Sent'),
        ('error', 'Error'),
    ], string='Message Status', default='draft')
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    error_msg = fields.Char("Error Message/MSG ID")
    template_id = fields.Many2one("pb.sms.template", "Template")
    templateid = fields.Char("Template ID", help="DLT Approved Template ID")
    res_model = fields.Char('Resource Model', readonly=True, help="The database object this sms will be attached to.")
    res_id = fields.Many2oneReference('Resource ID', model_field='res_model',
                                      readonly=True, help="The record id this is attached to.")
        
    @api.onchange('template_id')
    def onchange_template(self):
        if self.template_id:
            self.msg = self.template_id.message

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('You cannot delete an record which is not draft.'))
        return super(PbSms, self).unlink()

    def send_sms(self):
        for rec in self:
            try:
                ssl._create_default_https_context = ssl._create_unverified_context
                rep = urlopen(Request(rec.name, headers={'User-Agent': 'Mozilla/5.0'})).read()
                rec.state = 'sent'
                rec.error_msg = rep.decode('utf-8', errors='replace')
            except Exception as e:
                rec.state = 'error'
                rec.error_msg = str(e)

    def action_draft(self):
        self.state = 'draft'

    @api.model
    def _check_queue(self):
        records = self.search([('state', '=', 'draft')], limit=100)
        records.send_sms()

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'views': [(False, 'form')],
            'view_id': False,
        }
 

class PBSmsMixin(models.AbstractModel):
    _name = "pb.sms.mixin"
    _description = "SMS Mixin"

    @api.model
    def create_sms(self, msg, mobile, partner=False, res_model=False, res_id=False):
        company_id = self.env.context.get('force_company')
        if not company_id:
            company_id = self.env.user.sudo().company_id.id
        record = self.env['pb.sms'].create({
            'msg': msg,
            'partner_id': partner and partner.id or False,
            'mobile': mobile,
            'company_id': company_id,
            'res_model':res_model,
            'res_id':res_id,
        })
        if self.env.context.get('force_send'):
            record.send_sms()
        return record

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: