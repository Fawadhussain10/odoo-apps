#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class PBAppointment(models.Model):
    _inherit = 'hms.appointment'

    READONLY_STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    medical_questionnaire_ids = fields.One2many('pb.medical.questionnaire', 'appointment_id', 
        string='Medical Questionnaire')
    aesthetic_questionnaire_ids = fields.One2many('pb.aesthetic.questionnaire', 'appointment_id', 
        string='Aesthetic Questionnaire')

    skin_score = fields.Integer(related="patient_id.skin_score", string="Skin Score", store=True)
    skin_phototype = fields.Selection(string="Skin Phototype", related="patient_id.skin_phototype", store=True)

    face_mapping_ids = fields.One2many('pb.aesthetic.face.mapping', 'appointment_id', string="Face Mapping")
    body_evolution_ids = fields.One2many('pb.aesthetic.body.evolution', 'appointment_id', string="Body Evolution")
    aesthetic_wish_id = fields.Many2one('pb.aesthetic.patient.wish', string='Patient Wish')

    @api.onchange('department_id')
    def onchange_aestetic_department(self):
        medical_questionnaire_ids = []
        aesthetic_questionnaire_ids = []
        if self.department_id and self.department_id.department_type=='aesthetic':
            questions = self.env['pb.aesthetic.questionnaire.template'].search([])
            for question in questions:
                if question.question_type=='medical':
                    medical_questionnaire_ids.append((0,0,{
                        'name': question.name,
                        'remark': question.remark,
                    }))
                else:
                    aesthetic_questionnaire_ids.append((0,0,{
                        'name': question.name,
                        'remark': question.remark,
                    }))

            self.medical_questionnaire_ids = medical_questionnaire_ids
            self.aesthetic_questionnaire_ids = aesthetic_questionnaire_ids


class HmsTreatment(models.Model):
    _inherit = 'hms.treatment'

    aesthetic_wish_id = fields.Many2one('pb.aesthetic.patient.wish', string='Patient Wish')


class HrDepartment(models.Model):
    _inherit = "hr.department"

    department_type = fields.Selection(selection_add=[('aesthetic','Aesthetic')])
    

class PBProduct(models.Model):
    _inherit = 'product.template'

    hospital_product_type = fields.Selection(selection_add=[('aesthetic_procedure','Aesthetic Process')])

    is_body_treatment = fields.Boolean("Is Body Treatment")
    is_body_nutrition = fields.Boolean("Is Body Nutrition")
    is_body_upkeep = fields.Boolean("Is Body Upkeep")

    is_facial_treatment = fields.Boolean("Is Facial Treatment")
    is_facial_nutrition = fields.Boolean("Is Facial Nutrition")
    is_facial_upkeep = fields.Boolean("Is Facial Upkeep")

    product_procedure_line_ids = fields.One2many('aesthetic.product.procedure', 'product_tmpl_id', string='Aesthetic Procedures')


class AestheticProductProcedure(models.Model):
    _name = 'aesthetic.product.procedure'
    _description = "Aesthetic Product Procedure"

    product_tmpl_id = fields.Many2one('product.template', 'Product Tempalte', required=True)
    product_id = fields.Many2one('product.product', 'Product', required=True)
    repeat_for = fields.Integer('Repetition for',help="Repetition Count", default=1, required=True)
    days_to_add = fields.Integer('Days to add',help="Days to add for next date")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: