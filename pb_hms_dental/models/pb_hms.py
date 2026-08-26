#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class PBAppointment(models.Model):
    _inherit = 'hms.appointment'

    READONLY_STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    medical_questionnaire_ids = fields.One2many('pb.medical.questionnaire', 'appointment_id', 
        string='Medical Questionnaire')
    dental_questionnaire_ids = fields.One2many('pb.dental.questionnaire', 'appointment_id', 
        string='Dental Questionnaire')

    @api.onchange('department_id')
    def onchange_dentaldepartment(self):
        medical_questionnaire_ids = []
        dental_questionnaire_ids = []
        if self.department_id and self.department_id.department_type=='dental':
            questions = self.env['pb.dental.questionnaire.template'].search([])
            for question in questions:
                if question.question_type=='medical':
                    medical_questionnaire_ids.append((0,0,{
                        'name': question.name,
                        'remark': question.remark,
                    }))
                else:
                    dental_questionnaire_ids.append((0,0,{
                        'name': question.name,
                        'remark': question.remark,
                    }))

            self.medical_questionnaire_ids = medical_questionnaire_ids
            self.dental_questionnaire_ids = dental_questionnaire_ids


class PbPatientProcedure(models.Model):
    _inherit="pb.patient.procedure"

    STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    tooth_surface_ids = fields.Many2many('pb.tooth.surface', string='Surface')
    tooth_id = fields.Many2one('pb.hms.tooth', string='Tooth')


class HrDepartment(models.Model): 
    _inherit = "hr.department"

    department_type = fields.Selection(selection_add=[('dental','Odontology')])


class PBProduct(models.Model):
    _inherit = 'product.template'

    hospital_product_type = fields.Selection(selection_add=[('dental_procedure','Dental Process')])


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: