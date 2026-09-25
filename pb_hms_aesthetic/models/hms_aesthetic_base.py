# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class PbAestheticQuestionnaireTemplate(models.Model):
    _name="pb.aesthetic.questionnaire.template"
    _description = "Aesthetic Questionnaire Template"

    name = fields.Char(string="Name", required=True)
    remark = fields.Char(string="Remarks")
    question_type = fields.Selection([('medical', 'Medical'),
        ('aesthetic', 'Aesthetic')], default="aesthetic", required=True)


class PbAestheticQuestionnaire(models.Model):
    _name="pb.aesthetic.questionnaire"
    _description = "Aesthetic Questionnaire"

    name = fields.Char(string="Name", required=True)
    is_done = fields.Boolean(string="Y/N", default=False)
    remark = fields.Char(string="Remarks")
    appointment_id = fields.Many2one("hms.appointment", ondelete="cascade", string="Appointment")


class PbmedicalQuestionnaire(models.Model):
    _name="pb.medical.questionnaire"
    _description = "Medical Questionnaire"

    name = fields.Char(string="Name", required=True)
    is_done = fields.Boolean(string="Y/N", default=False)
    remark = fields.Char(string="Remarks")
    appointment_id = fields.Many2one("hms.appointment", ondelete="cascade", string="Appointment")


class PbAestheticFaceMapping(models.Model):
    _name="pb.aesthetic.face.mapping"
    _description = "Face Mapping"

    date = fields.Date(string="Date", default=fields.Date.today)
    appointment_id = fields.Many2one("hms.appointment", ondelete="cascade", string="Appointment")
    patient_id = fields.Many2one("hms.patient", ondelete="cascade", string="Patient")
    physician_id = fields.Many2one('hms.physician', ondelete='restrict', string='Physician', index=True,)

    parameter_1 = fields.Char("1.")
    parameter_2 = fields.Char("2.")
    parameter_3 = fields.Char("3.")
    parameter_4 = fields.Char("4.")
    parameter_5 = fields.Char("5.")
    parameter_6 = fields.Char("6.")
    parameter_7 = fields.Char("7.")
    parameter_8 = fields.Char("8.")
    parameter_9 = fields.Char("9.")
    parameter_10 = fields.Char("10.")
    parameter_11 = fields.Char("11.")
    parameter_12 = fields.Char("12.")
    parameter_13 = fields.Char("13.")
    parameter_14 = fields.Char("14.")

    evolution = fields.Text(string="Evolution")
    patient_signature = fields.Binary("Patient Signature")


class PbBodyEvolution(models.Model):
    _name="pb.aesthetic.body.evolution"
    _description = "Body Evolution"
    _order = "date desc"

    date = fields.Date(string="Date", default=fields.Date.today)
    appointment_id = fields.Many2one("hms.appointment", ondelete="cascade", string="Appointment")
    patient_id = fields.Many2one("hms.patient", ondelete="cascade", string="Patient", required=True)
    physician_id = fields.Many2one('hms.physician', ondelete='restrict', string='Physician', index=True,)

    weight = fields.Char(string="Weight")
    bust = fields.Char(string="Bust")
    right_arm = fields.Char(string="Right arm")
    left_arm = fields.Char(string="Left arm")
    high_abdomen = fields.Char(string="High abdomen")
    middle_abdomen = fields.Char(string="Middle abdomen")
    low_abdomen = fields.Char(string="Low abdomen")
    hip = fields.Char(string="Hip")
    right_thigh = fields.Char(string="Right thigh")
    left_thigh = fields.Char(string="Left thigh")

    last_evolution_id = fields.Many2one("pb.aesthetic.body.evolution", compute="_get_last_evolution", ondelete="cascade", string="Last Evolution", readonly=True, store=True)
    last_weight = fields.Char(related="last_evolution_id.weight", string="Last Weight", readonly=True)
    last_bust = fields.Char(related="last_evolution_id.bust", string="Last Bust", readonly=True)
    last_right_arm = fields.Char(related="last_evolution_id.right_arm", string="Last Right arm", readonly=True)
    last_left_arm = fields.Char(related="last_evolution_id.left_arm", string="Last Left arm", readonly=True)
    last_high_abdomen = fields.Char(related="last_evolution_id.high_abdomen", string="Last High abdomen", readonly=True)
    last_middle_abdomen = fields.Char(related="last_evolution_id.middle_abdomen", string="Last Middle abdomen", readonly=True)
    last_low_abdomen = fields.Char(related="last_evolution_id.low_abdomen", string="Last Low abdomen", readonly=True)
    last_hip = fields.Char(related="last_evolution_id.hip", string="Last Hip", readonly=True)
    last_right_thigh = fields.Char(related="last_evolution_id.right_thigh", string="Last Right thigh", readonly=True)
    last_left_thigh = fields.Char(related="last_evolution_id.left_thigh", string="Last Left thigh", readonly=True)
    
    evolution = fields.Text(string="Evolution")
    patient_signature = fields.Binary("Patient Signature")

    @api.depends('date','patient_id')
    def _get_last_evolution(self):
        for rec in self:
            #Default patient id was new every time so used default value.
            patient_id = rec.patient_id.id if rec.patient_id.id else self.env.context.get('default_patient_id',False)
            last_evolution_id = self.search([('patient_id','=',patient_id),('date','<=',rec.date)], limit=1)
            rec.last_evolution_id = last_evolution_id.id if last_evolution_id else False

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: