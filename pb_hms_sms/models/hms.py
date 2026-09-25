# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.tools.safe_eval import safe_eval
from odoo.tools import format_datetime
from odoo.exceptions import UserError


class HmsAppointment(models.Model):
    _name = 'hms.appointment'
    _inherit = ['hms.appointment','pb.sms.mixin']

    @api.model
    def send_appointment_reminder(self):
        reminder_appointments = super(HmsAppointment, self).send_appointment_reminder()
        for appointment in reminder_appointments:
            if appointment and appointment.patient_id and appointment.patient_id.phone and appointment.company_id.pb_reminder_sms_template_id:
                rendered = self.env['mail.render.mixin']._render_template(appointment.company_id.pb_reminder_sms_template_id.message, appointment._name, [appointment.id])
                msg = rendered[appointment.id]
                self.create_sms(msg, appointment.patient_id.partner_id.phone, appointment.patient_id.partner_id, res_model='hms.appointment', res_id=appointment.id)
        return reminder_appointments

    def appointment_confirm(self):
        res = super(HmsAppointment, self).appointment_confirm()
        for rec in self:
            if rec.sudo().company_id.appointment_registartion_sms_template_id and rec.patient_id and rec.patient_id.phone:
                rendered = self.env['mail.render.mixin']._render_template(rec.sudo().company_id.appointment_registartion_sms_template_id.message, rec._name, [rec.id])
                msg = rendered[rec.id]
                self.create_sms(msg, rec.patient_id.partner_id.phone, rec.patient_id.partner_id, res_model='hms.appointment', res_id=rec.id)
        return res


class HmsPatient(models.Model):
    _name = 'hms.patient'
    _inherit = ['hms.patient','pb.sms.mixin']

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for record in res:
            company_id = record.sudo().company_id or self.env.user.sudo().company_id
            if company_id.patient_registartion_sms_template_id:
                if record.phone:
                    try:
                        rendered = self.env['mail.render.mixin']._render_template(company_id.patient_registartion_sms_template_id.message, record._name, [record.id])
                        msg = rendered[record.id]
                    except:
                       raise UserError(_("Configured Patient Registartion Message fromat is wrong please contact administrator to correct it first."))
                    self.create_sms(msg, record.partner_id.phone, record.partner_id, res_model='hms.patient', res_id=record.id)
        return res

    def action_send_otp_sms(self):
        return self.partner_id.action_send_otp_sms()

    def action_verify_otp_sms(self):
        return self.partner_id.action_verify_otp_sms()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: