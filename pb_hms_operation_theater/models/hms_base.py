# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import datetime, date, timedelta

class PbHospitalization(models.Model):
    _inherit = "pb.hospitalization"

    def _rec_count(self):
        rec = super(PbHospitalization, self)._rec_count()
        for rec in self:
            rec.ot_booking_count = len(rec.ot_booking_ids.ids)

    ot_booking_ids = fields.One2many('pb.ot.booking', 'hospitalization_id', string='OT Bookings')
    ot_booking_count = fields.Integer(compute='_rec_count', string='# OT Bookings')

    def action_ot_booking(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_operation_theater.action_pb_ot_booking")
        action['domain'] = [('hospitalization_id', '=', self.id)]
        action['context'] = { 'default_patient_id': self.patient_id.id, 'default_hospitalization_id': self.id}
        return action


class HmsTreatment(models.Model):
    _inherit = 'hms.treatment'

    def action_view_ot_booking(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_operation_theater.action_pb_ot_booking")
        action['domain'] = [('treatment_id', '=', self.id)]
        action['context'] = {'default_treatment_id': self.id, 'default_patient_id': self.patient_id.id}
        return action