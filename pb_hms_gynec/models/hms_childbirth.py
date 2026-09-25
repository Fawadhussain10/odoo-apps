# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

class PbChildBirth(models.Model):
    _name = "pb.child.birth"
    _description = "Child Birth"

    name = fields.Char('Name of Children', readonly=True, copy=False)
    hospitalizaion_id = fields.Many2one('pb.hospitalization', string='Hospitalization')
    patient_id = fields.Many2one('hms.patient', string="Mother Name")
    age = fields.Char(related='patient_id.age',string="Age", readonly=True)
    father_name = fields.Char(related='patient_id.spouse_name', string="Father's Name", readonly=True)
    father_edu = fields.Char(related='patient_id.spouse_edu',string="Father's Education", readonly=True)
    father_business = fields.Char(related='patient_id.spouse_business',string="Father's Business", readonly=True)
    patient_education = fields.Char(related='patient_id.education',string="Patient Education", readonly=True)
    mother_hb = fields.Float(related='patient_id.hb',string="Mother Hemoglobin Count", readonly=True)
    mother_blood_group = fields.Selection(related='patient_id.blood_group', string='Mother Blood Group', readonly=True)
    blood_group = fields.Selection([
        ('A+', 'A+'),('A-', 'A-'),
        ('B+', 'B+'),('B-', 'B-'),
        ('AB+', 'AB+'),('AB-', 'AB-'),
        ('O+', 'O+'),('O-', 'O-')], string='Blood Group')
    parity = fields.Integer(string="Parity")
    male = fields.Integer(string="Male")
    female = fields.Integer(string="Female")
    delivery_type = fields.Selection ([
            ('normal', 'Normal'),
            ('cesarean', 'Cesarean'),
            ], string='Type of Delivery')
    gender = fields.Selection ([
            ('male','Male'),
            ('female','Female'),
            ], string='Gender', index=True, required=True)
    birth_date = fields.Datetime(string='Date of birth', required=True)
    birth_place = fields.Char("Birth Place")
    birth_weight = fields.Float(string='Birth Weight', required=True)
    extra_info = fields.Text (string='Remarks')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')],
        string='Status', required=True, readonly=True, copy=False,default='draft')
    physician_id = fields.Many2one('hms.physician', ondelete='restrict', string='Physician', index=True)
    hb = fields.Float(string="Hemoglobin Count")
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Hospital',default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.child.birth') or 'New Birth'
        return super().create(vals_list)

    def unlink(self):
        for data in self:
            if data.state in ['done']:
                raise UserError(('You can not delete record in done state'))
        return super(PbChildBirth, self).unlink()

    def action_done(self):
        self.state = 'done'

    def action_draft(self):
        self.state = 'draft'

    @api.onchange('hospitalizaion_id')   
    def onchange_hospitalizaion(self):
        if self.hospitalizaion_id:
            self.patient_id = self.hospitalizaion_id.patient_id.id
            self.physician_id = self.hospitalizaion_id.physician_id.id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: