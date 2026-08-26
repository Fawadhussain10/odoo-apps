# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _name = 'hr.employee'
    _inherit = ['hr.employee','pb.whatsapp.mixin']


class WhatsappAnnouncement(models.Model):
    _name = 'pb.whatsapp.announcement'
    _inherit = ['pb.whatsapp.mixin']
    _description = 'whatsapp Announcement'
    _rec_name = 'message'

    READONLY_STATES = {'sent': [('readonly', True)]}

    name = fields.Char("Name")
    message = fields.Text(string='Announcement')
    message_type =  fields.Selection([
        ('message', 'Message'),
        ('file', 'File'),
        ('file_url', 'File URL'),
        ('link', 'Link'),
    ], string='Message Type', default='message')
    file =  fields.Binary(string='File')
    file_name =  fields.Char(string='File Name')
    file_url =  fields.Char(string='File URL')
    link = fields.Char('Link')
    date = fields.Date(string='Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'), 
    ], string='Status', copy=False, default='draft')
    announcement_type = fields.Selection([
        ('contacts', 'Contacts'),
        ('employees', 'Employees'),
    ], string='Announcement Type', copy=False, default='contacts', required=True)
    employee_selection_type = fields.Selection([
        ('all', 'All'),
        ('department', 'Department'),
        ('employees', 'Employees'),
    ], string='Type', copy=False, default='all', required=True)
    employee_ids = fields.Many2many("hr.employee", "whatsapp_employee_announement_rel", "employee_id", "announcement_id", "Employees")
    department_id = fields.Many2one("hr.department", "Department")
    partner_ids = fields.Many2many("res.partner", "whatsapp_partner_announement_rel", "partner_id", "announcement_id", "Contacts")
    template_id = fields.Many2one("pb.whatsapp.template", "Template")
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    @api.onchange('template_id')
    def onchange_template(self):
        if self.template_id:
            message_type = 'message'
            if self.template_id.body_message_type=='DOCUMENT' or self.template_id.body_message_type=='IMAGE':
                message_type = 'file'
            self.message_type = message_type
            rendered = self.env['mail.render.mixin']._render_template(self.template_id.body_message, self._name, [self.id])
            self.message = rendered[self.id]

            self.employee_ids = [(6, 0, self.template_id.employee_ids.ids + self.employee_ids.ids)]
            self.partner_ids = [(6, 0, self.template_id.partner_ids.ids + self.partner_ids.ids)]

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft'):
                raise UserError(_('You cannot delete an record which is not draft.'))
        return super(WhatsappAnnouncement, self).unlink()

    def pb_create_message(self, mobile, partner=False, res_model=False, res_id=False):
        if self.message_type=='message':
            self.send_whatsapp(self.message, mobile, partner, res_model=res_model, res_id=res_id)
        elif self.message_type=='file_url':
            self.send_whatsapp_file_url(self.file_url, mobile, partner, res_model=res_model, res_id=res_id)
        elif self.message_type=='file':
            self.send_whatsapp_file(self.file, self.file_name, mobile, partner, res_model=res_model, res_id=res_id)

    def send_message(self):
        if self.announcement_type=='contacts':
            for partner in self.partner_ids:
                if partner.phone:
                    self.pb_create_message(partner.phone, partner,res_model='res.partner', res_id=partner.id)
        else:
            if self.employee_selection_type=='employees':
                employees = self.employee_ids
            elif self.employee_selection_type=='department':
                employees = self.env['hr.employee'].search([('department_id','=',self.department_id.id)])
            else:
                employees = self.env['hr.employee'].search([])
            for employee in employees:
                partner = employee.user_id and employee.user_id.partner_id
                mobile = partner.phone or employee.mobile_phone
                if mobile:
                    self.pb_create_message(mobile, False, res_model='hr.employee', res_id=employee.id)

        self.state = 'sent'
        self.date = fields.Datetime.now()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: