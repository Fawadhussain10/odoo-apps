# -*- encoding: utf-8 -*-

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.tools import pycompat


class PbConsentForm(models.Model):
    _inherit = 'pb.consent.form'

    READONLYSTATES = {'tosign': [('readonly', True)], 'signed': [('readonly', True)]}

    patient_id = fields.Many2one('hms.patient', string='Patient', ondelete="restrict", 
        help="Patient whose consent form to be attached", tracking=True)
    physician_id = fields.Many2one('hms.physician',string='Doctor', ondelete="restrict", 
        help="Doctor who provided consent form to the patient", tracking=True)
    appointment_id = fields.Many2one('hms.appointment', string='Appointment', ondelete="restrict", 
        help="Patient Appointment")

    @api.onchange('patient_id')
    def onchange_patient_id(self):
        if self.patient_id:
            self.partner_id = self.patient_id.partner_id

    @api.onchange('physician_id')
    def onchange_physician_id(self):
        if self.physician_id:
            self.user_id = self.physician_id.user_id


class PBPatient(models.Model):
    _inherit = 'hms.patient' 

    def _rec_count(self):
        rec = super(PBPatient, self)._rec_count()
        for rec in self:
            rec.consent_form_count = len(rec.sudo().consent_form_ids)

    consent_form_ids = fields.One2many('pb.consent.form', 'patient_id', string='Consent Form')
    consent_form_count = fields.Integer(compute='_rec_count', string='# Consent Form')

    def action_open_consent_form(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_consent_form.action_pb_consent_form")
        action['domain'] = [('patient_id','=',self.id)]
        action['context'] = {'default_patient_id': self.id}
        return action


class HmsAppointment(models.Model):
    _inherit = 'hms.appointment' 

    def _consent_form_count(self):
        for rec in self:
            rec.consent_form_count = len(rec.sudo().consent_form_ids)

    consent_form_ids = fields.One2many('pb.consent.form', 'appointment_id', string='Consent Form', groups="pb_consent_form.group_consent_form_manager")
    consent_form_count = fields.Integer(compute='_consent_form_count', string='# Consent Form')

    def action_open_consent_form(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_consent_form.action_pb_consent_form")
        action['domain'] = [('appointment_id','=',self.id)]
        action['context'] = {
            'default_appointment_id': self.id,
            'default_patient_id': self.patient_id and self.patient_id.id or False,
            'default_physician_id': self.physician_id and self.physician_id.id or False,
        }
        return action


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for record in res:
            record.pb_create_sequence(name='Consent Form', code='pb.consent.form', prefix='CF')
        return res

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: