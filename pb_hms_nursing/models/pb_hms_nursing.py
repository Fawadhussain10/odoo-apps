#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PbNurseWardRound(models.Model):
    _name = 'pb.nurse.ward.round'
    _description = "Nurse Ward round"

    READONLY_STATES = {'done': [('readonly', True)]}

    name = fields.Char(string='Round Number')
    nurse_id = fields.Many2one('hr.employee', string='Nurse', default=lambda self: self.env.user.employee_id.id, required=True)
    hospitalization_id = fields.Many2one('pb.hospitalization', string='Hospitalization')
    patient_id = fields.Many2one('hms.patient', string='Patient', related='hospitalization_id.patient_id', store=True)
    date = fields.Datetime('Date', default=fields.Datetime.now, required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')], default='draft', string='Status')    

    evaluation_id = fields.Many2one('pb.patient.evaluation', string='Evaluation')
    weight = fields.Float(related="evaluation_id.weight", string='Weight', help="Weight in KG")
    height = fields.Float(related="evaluation_id.height", string='Height', help="Height in cm")
    temp = fields.Float(related="evaluation_id.temp", string='Temp')
    hr = fields.Integer(related="evaluation_id.hr", string='HR', help="Heart Rate")
    rr = fields.Integer(related="evaluation_id.rr", string='RR', help='Respiratory Rate')
    systolic_bp = fields.Integer(related="evaluation_id.systolic_bp", string="Systolic BP")
    diastolic_bp = fields.Integer(related="evaluation_id.diastolic_bp", string="Diastolic BP")
    spo2 = fields.Integer(related="evaluation_id.spo2", string='SpO2', 
        help='Oxygen Saturation, percentage of oxygen bound to hemoglobin')
    pain_level = fields.Selection(related="evaluation_id.pain_level", string="Pain Level")
    pain = fields.Selection(related="evaluation_id.pain", string="Pain")
    bmi = fields.Float(related="evaluation_id.bmi", string='Body Mass Index', store=True)
    bmi_state = fields.Selection(related="evaluation_id.bmi_state", string='BMI State', store=True)

    # The Patients of rounding
    position = fields.Boolean(string='Position', 
        help="Check if the patient needs to be repositioned or is unconfortable")
    potty = fields.Boolean(string='Potty', 
        help="Check if the patient needs to urinate / defecate")
    proximity = fields.Boolean(string='Proximity', 
        help="Check if personal items, water, alarm, ... are not in easy reach")
    pump = fields.Boolean(string='Pump', 
        help="Check if there is any issues with the pumps - IVs ... ")
    personal_needs = fields.Boolean(string='Personal Needs', 
        help="Check if the patient requests anything")

    # Diuresis
    diuresis = fields.Integer(string='Diuresis', help="volume in ml")
    urinary_catheter = fields.Boolean(string='Urinary Catheter')

    #Glycemia
    glycemia = fields.Integer(string='Glycemia', help="Blood Glucose level")
    depression = fields.Boolean(string='Depression', help="Check this if the "
        "patient shows signs of depression")
    evolution = fields.Selection([
        ('improving', 'Improving'),
        ('worsening', 'Worsening')], string='Evolution', help="Check your judgement of current"
        "patient condition", default='improving', required=True)
    round_summary = fields.Text(string='Round Summary')
    warning = fields.Boolean(string='Warning', help="Check this box to alert the "
        "supervisor about this patient rounding. A warning icon will be shown in the rounding list")
    invoice_id = fields.Many2one('account.move', string='Invoice', copy=False)

    @api.model
    def default_get(self, fields):
        res = super(PbNurseWardRound, self).default_get(fields)
        if self.env.context.get('default_hospitalization_id'):
            res['hospitalization_id'] = self.env.context.get('default_hospitalization_id')
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.nurse.ward.round') or 'New'
        return super().create(vals_list)

    def action_done(self):
        self.state = "done"

    def action_create_evaluation(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms.action_pb_patient_evaluation_popup")
        action['domain'] = [('patient_id','=',self.patient_id.id)]
        action['context'] = {'default_patient_id': self.patient_id.id, 'default_hospitalization_id': self.hospitalization_id.id, 'nurse_ward_round': self.id}
        return action

    @api.onchange('evaluation_id')
    def onchange_evalutaion(self):
        if self.evaluation_id:
            self.date = self.evaluation_id.date