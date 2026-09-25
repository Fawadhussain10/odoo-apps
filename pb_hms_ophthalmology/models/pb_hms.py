#-*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PBAppointment(models.Model):
    _inherit = 'hms.appointment'

    def action_view_ophthalmology(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_ophthalmology.action_pb_ophthalmology_evaluation")
        action['domain'] = [('appointment_id', '=', self.id)]
        action['context'] = {
            'default_appointment_id': self.id,
            'default_patient_id': self.patient_id.id
        }
        return action

class PBPatient(models.Model):
    _inherit = "hms.patient"

    def _rec_count(self):
        rec = super(PBPatient, self)._rec_count()
        for rec in self:
            rec.ophthalmology_count = len(rec.ophthalmology_ids)

    ophthalmology_ids = fields.One2many('pb.ophthalmology.evaluation', 'patient_id', string='Ophthalmology')
    ophthalmology_count = fields.Integer(compute='_rec_count', string='# Ophthalmology')

    def action_view_ophthalmology(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_ophthalmology.action_pb_ophthalmology_evaluation")
        action['domain'] = [('patient_id', '=', self.id)]
        action['context'] = {
            'default_patient_id': self.id
        }
        return action


class HrDepartment(models.Model): 
    _inherit = "hr.department"

    department_type = fields.Selection(selection_add=[('ophthalmology','Ophthalmology')])


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: