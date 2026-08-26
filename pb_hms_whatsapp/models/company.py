# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    pb_patient_reg_template_id = fields.Many2one('pb.whatsapp.template', 'Patient Registration Template')
    pb_appointment_confirmation_template_id = fields.Many2one('pb.whatsapp.template', 'Appointment Registration Template')
    pb_appointment_reminder_template_id = fields.Many2one('pb.whatsapp.template', 'Appointment Reminder Template')
    pb_appointment_reschedule_template_id = fields.Many2one('pb.whatsapp.template', 'Appointment Reschedule Template')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: