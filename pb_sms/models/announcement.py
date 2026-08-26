# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _name = 'hr.employee'
    _inherit = ['hr.employee','pb.sms.mixin']


class Announcement(models.Model):
    _name = 'pb.sms.announcement'
    _description = 'SMS Announcement'
    _rec_name = 'message'

    READONLY_STATES = {'sent': [('readonly', True)]}

    message = fields.Text(string='Announcement')
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
    employee_ids = fields.Many2many("hr.employee", "employee_announement_rel", "employee_id", "announcement_id", "Employees")
    department_id = fields.Many2one("hr.department", "Department")
    partner_ids = fields.Many2many("res.partner", "partner_announement_rel", "partner_id", "announcement_id", "Contacts")
    template_id = fields.Many2one("pb.sms.template", "Template")
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    @api.onchange('template_id')
    def onchange_template(self):
        if self.template_id:
            self.message = self.template_id.message
            self.employee_ids = [(6, 0, self.template_id.employee_ids.ids + self.employee_ids.ids)]
            self.partner_ids = [(6, 0, self.template_id.partner_ids.ids + self.partner_ids.ids)]

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft'):
                raise UserError(_('You cannot delete an record which is not draft.'))
        return super(Announcement, self).unlink()

    def send_message(self):
        if self.announcement_type=='contacts':
            for partner in self.partner_ids:
                if partner.phone:
                    partner.create_sms(self.message, partner.phone, partner, res_model='res.partner', res_id=partner.id)
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
                    employee.create_sms(self.message, mobile, False, res_model='hr.employee', res_id=employee.id)

        self.state = 'sent'
        self.date = fields.Datetime.now()