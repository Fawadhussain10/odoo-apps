# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    patient_registartion_sms_template_id = fields.Many2one("pb.sms.template", "Patient Registartion SMS")
    appointment_registartion_sms_template_id = fields.Many2one("pb.sms.template", "Appointment Registartion SMS")
    pb_reminder_sms_template_id = fields.Many2one("pb.sms.template", "Appointment Reminder SMS")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: