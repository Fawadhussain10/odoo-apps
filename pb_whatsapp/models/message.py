# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype
from odoo.tools import format_datetime
import mimetypes


class PbWhatsAppMessage(models.Model):
    _name = 'pb.whatsapp.message'
    _description = 'whatsapp'
    _order = 'id desc'

    READONLY_STATES = {'sent': [('readonly', True)], 'error': [('readonly', True)]}

    @api.depends('file_name','message','message_type')
    def _get_name(self):
        for rec in self:
            if rec.message and rec.message_type=='message':
                if len(rec.message)>100:
                    rec.name = rec.message[:100]
                else:
                    rec.name = rec.message or 'Message'
            elif rec.message_type in ['file','file_url']:
                name = "File"
            elif rec.message_type=='link':
                name = "Link"
            else:
                name = rec.file_name or 'Message'

    name = fields.Char(string="Name", compute="_get_name", store=True)
    partner_id = fields.Many2one('res.partner', 'Contact', ondelete="cascade")
    file =  fields.Binary(string='File', attachment=True)
    file_name =  fields.Char(string='File Name')
    file_url =  fields.Char(string='File URL')
    message =  fields.Text(string='WhatsApp Text')
    mobile =  fields.Char(string='Destination Number', required=True)
    state =  fields.Selection([
        ('draft', 'Queued'),
        ('sent', 'Sent'),
        ('error', 'Error'),
    ], string='Message Status', index=True, default='draft')
    message_type =  fields.Selection([
        ('message', 'Message'),
        ('file', 'File'),
        ('file_url', 'File URL'),
        ('link', 'Link'),
    ], string='Message Type', default='message')
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    error_message = fields.Char("Error Message")
    template_id = fields.Many2one("pb.whatsapp.template", string="Template")
    whatsapp_announcement_id = fields.Many2one("pb.whatsapp.announcement", string="Announcement")
    reply_data = fields.Text(copy=False)
    mimetype = fields.Char('Mime Type')
    link = fields.Char('Link')
    res_model = fields.Char('Resource Model', readonly=True, help="The database object this sms will be attached to.")
    res_id = fields.Many2oneReference('Resource ID', model_field='res_model',
                                      readonly=True, help="The record id this is attached to.")

    def _check_contents(self, values):
        values['mimetype'] = self.env['ir.attachment']._compute_mimetype(values)
        return values

    def pb_sanatize_mobile_number(self, values):
        if values.get('mobile'):
            values['mobile'] = values['mobile'].replace(' ', '').replace('+', '').replace('-', '')
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values = self._check_contents(values)
            values = self.pb_sanatize_mobile_number(values)
        return super().create(vals_list)

    def write(self, vals):
        if 'mimetype' in vals or 'file' in vals:
            vals = self._check_contents(vals)
        if 'mobile' in vals:
            vals = self.pb_sanatize_mobile_number(vals)
        res = super(PbWhatsAppMessage, self).write(vals)
        return res

    @api.onchange('template_id')
    def onchange_template(self):
        if self.template_id:
            message_type = 'message'
            if self.template_id.body_message_type=='DOCUMENT' or self.template_id.body_message_type=='IMAGE':
                message_type = 'file'
            self.message_type = message_type
            rendered = self.env['mail.render.mixin']._render_template(self.template_id.body_message, self._name, [self.id])
            self.message = rendered[self.id]
            self.file_name = self.template_id.body_file_name

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'views': [(False, 'form')],
            'view_id': False,
        }

    def send_whatsapp_message(self):
        """Hook method to add logic in relatd module"""
        pass

    def action_draft(self):
        self.state = 'draft'

    @api.model
    def complete_queue(self):
        records = self.search([('state', '=', 'draft')], limit=100)
        records.send_whatsapp_message()

    @api.onchange('partner_id')
    def onchange_partner(self):
        if self.partner_id and self.partner_id.phone:
            self.mobile = self.partner_id.phone


class PBwhatsappMixin(models.AbstractModel):
    _name = "pb.whatsapp.mixin"
    _description = "WhatsApp Mixin"

    @api.model
    def pb_eval_message(self, object, message_exp):
        message = ''
        try:
            message = eval(message_exp, {'object': object, 
                'format_datetime': lambda dt, tz=False, dt_format=False, lang_code=False: format_datetime(self.env, dt, tz, dt_format, lang_code)
            })
        except:
            raise UserError(_("Configured Message fromat is wrong please contact administrator correct it first."))
        return message

    @api.model
    def send_whatsapp(self, message, mobile, partner=False, template=False, res_model=False, res_id=False):
        company_id = self.env.context.get('force_company')
        if not company_id:
            company_id = self.env.user.sudo().company_id.id
        record = self.env['pb.whatsapp.message'].create({
            'message': message,
            'partner_id': partner and partner.id or False,
            'mobile': mobile,
            'message_type': 'message',
            'company_id': company_id,
            'template_id': template and template.id or False,
            'res_model':res_model,
            'res_id':res_id,
        })
        if self.env.context.get('force_send'):
            record.send_whatsapp_message()
        return record

    @api.model
    def send_whatsapp_file_url(self, file_url, mobile, partner=False, template=False, res_model=False, res_id=False):
        company_id = self.env.context.get('force_company')
        if not company_id:
            company_id = self.env.user.sudo().company_id.id
        record = self.env['pb.whatsapp.message'].create({
            'file_url': file_url,
            'partner_id': partner and partner.id or False,
            'mobile': mobile,
            'message_type': 'file_url',
            'company_id': company_id,
            'template_id': template and template.id or False,
            'res_model':res_model,
            'res_id':res_id,
        })
        if self.env.context.get('force_send'):
            record.send_whatsapp_message()
        return record

    @api.model
    def send_whatsapp_file(self, filedata, file_name, mobile, partner=False, template=False, res_model=False, res_id=False):
        company_id = self.env.context.get('force_company')
        if not company_id:
            company_id = self.env.user.sudo().company_id.id
        record = self.env['pb.whatsapp.message'].create({
            'file': filedata,
            'file_name': file_name,
            'message_type': 'file',
            'partner_id': partner and partner.id or False,
            'mobile': mobile,
            'company_id': company_id,
            'template_id': template and template.id or False,
            'res_model':res_model,
            'res_id':res_id,
        })
        if self.env.context.get('force_send'):
            record.send_whatsapp_message()
        return record

    def pb_whatsapp_chat_history(self, partner, mobile):
        """Hook method to add logic in relatd module"""
        pass

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: