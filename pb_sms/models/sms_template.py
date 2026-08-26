# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PbSmsTemplate(models.Model):
    _name = 'pb.sms.template'
    _description = 'SMS Template'

    name = fields.Text(string='Name', required=True)
    message = fields.Text(string='Message', required=True)
    state =  fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved')
    ], string='Status', default='draft')
    templateid = fields.Char("Template ID", help="DLT Approved Template ID")
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    partner_ids = fields.Many2many("res.partner", "partner_sms_template_rel", "partner_id", "sms_template_id", "Partners")
    employee_ids = fields.Many2many("hr.employee", "employee_sms_template_rel", "employee_id", "sms_template_id", "Employees")


    def action_approve(self):
        self.state = 'approved'

    def action_draft(self):
        self.state = 'draft'

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: