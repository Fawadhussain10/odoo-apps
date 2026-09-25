#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import json


class HmsPatient(models.Model):
    _inherit = 'hms.patient'

    def pb_get_action(self):
        pb_action_id = self.env.ref('pb_hms_base.action_patient')
        for rec in self:
            rec.pb_action_id = pb_action_id

    pb_action_id = fields.Integer(compute="pb_get_action")

    def pb_hms_image_chart(self, param=''):
        self.ensure_one()
        Attachment = self.env['ir.attachment']
        image, image_name = Attachment.get_default_chart_image(False, self.company_id)
        attachment = Attachment.pb_create_chart_image(image, image_name, self._name, self.id)
        pb_action_id = self.env.context.get('params', {}).get('action') or self.env.context.get('pb_action_id')
        param = '?pb_model=%s&pb_rec_id=%s&pb_action_id=%s' % (self._name, self.id, pb_action_id)
        action = attachment.pb_hms_image_chart(param=param)
        return action

class HmsTreatment(models.Model):
    _inherit = 'hms.treatment'

    def pb_get_action(self):
        pb_action_id = self.env.ref('pb_hms.pb_action_form_hospital_treatment')
        for rec in self:
            rec.pb_action_id = pb_action_id

    pb_action_id = fields.Integer(compute="pb_get_action")

    def pb_hms_image_chart(self):
        self.ensure_one()
        Attachment = self.env['ir.attachment']
        image, image_name = Attachment.get_default_chart_image(self.department_id, self.company_id)
        attachment = Attachment.pb_create_chart_image(image, image_name, self._name, self.id)
        pb_action_id = self.env.context.get('params', {}).get('action') or self.env.context.get('pb_action_id')
        param = '?pb_model=%s&pb_rec_id=%s&pb_action_id=%s' % (self._name, self.id, pb_action_id)
        action = attachment.pb_hms_image_chart(param=param)
        return action


class HmsPatientProcedure(models.Model):
    _inherit = 'pb.patient.procedure'

    def pb_get_action(self):
        pb_action_id = self.env.ref('pb_hms.action_pb_patient_procedure')
        for rec in self:
            rec.pb_action_id = pb_action_id

    pb_action_id = fields.Integer(compute="pb_get_action")

    def pb_hms_image_chart(self):
        self.ensure_one()
        Attachment = self.env['ir.attachment']
        image, image_name = Attachment.get_default_chart_image(self.department_id, self.company_id)
        attachment = Attachment.pb_create_chart_image(image, image_name, self._name, self.id)
        pb_action_id = self.env.context.get('params', {}).get('action') or self.env.context.get('pb_action_id')
        param = '?pb_model=%s&pb_rec_id=%s&pb_action_id=%s' % (self._name, self.id, pb_action_id)
        action = attachment.pb_hms_image_chart(param=param)
        return action


class HmsAppointment(models.Model):
    _inherit = 'hms.appointment'

    def pb_get_action(self):
        pb_action_id = self.env.ref('pb_hms.action_appointment')
        for rec in self:
            rec.pb_action_id = pb_action_id

    pb_action_id = fields.Integer(compute="pb_get_action")

    def pb_hms_image_chart(self):
        self.ensure_one()
        Attachment = self.env['ir.attachment']
        image, image_name = Attachment.get_default_chart_image(self.department_id, self.company_id)
        attachment = Attachment.pb_create_chart_image(image, image_name, self._name, self.id)
        pb_action_id = self.env.context.get('params', {}).get('action') or self.env.context.get('pb_action_id')
        param = '?pb_model=%s&pb_rec_id=%s&pb_action_id=%s' % (self._name, self.id, pb_action_id)
        action = attachment.pb_hms_image_chart(param=param)
        return action


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    pb_default_chart_image = fields.Binary('Default Chart Image', help="Image to use in chart by default.")
    pb_default_chart_image_name = fields.Char('Default Chart Image name')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: