# coding: utf-8

from odoo import models, api, fields
from datetime import date, datetime, timedelta


class PbRescheduleAppointments(models.TransientModel):
    _name = 'pb.reschedule.appointments'
    _description = "Reschedule Appointments"

    pb_reschedule_time = fields.Float(string="Reschedule Selected Appointments by (Hours)", required=True)

    def pb_reschedule_appointments(self):
        appointments = self.env['hms.appointment'].search([('id','in',self.env.context.get('active_ids'))])
        #PB: do it in method only to use that method for notifications.
        appointments.pb_reschedule_appointments(self.pb_reschedule_time)
