# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, timedelta


class PbAestheticPatientWish(models.Model):
    _name="pb.aesthetic.patient.wish"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'pb.hms.mixin', 'pb.documnt.view.mixin']
    _description = "Aesthetic Patient Wish"
    _order = "id desc"

    def _get_document_preview_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for rec in self:
            rec.document_preview_url = base_url + "/my/pb/image/%s/%s" % (self._name,rec.id)

    def _pb_attachemnt_count(self):
        AttachmentObj = self.env['ir.attachment']
        for rec in self:
            attachments = AttachmentObj.search([
                ('res_model', '=', self._name),
                ('res_id', '=', rec.id)])
            rec.attachment_ids = [(6,0,attachments.ids)]
            rec.attach_count = len(attachments.ids)

    name = fields.Char(string="Name")
    patient_id = fields.Many2one('hms.patient', string='Patient', required=True)
    physician_id = fields.Many2one('hms.physician', ondelete='restrict', string='Physician', 
        index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Canceled'),
    ], string='Status', default='draft')
    company_id = fields.Many2one('res.company', ondelete='restrict',
        string='Hospital', default=lambda self: self.env.company)
    date = fields.Datetime("Date", default=fields.Datetime.now)
    treatment_id = fields.Many2one('hms.treatment', 'Treatment')
    note = fields.Text("Notes")

    #BODY TREATMENT PLAN
    cellulitis = fields.Boolean(string="Cellulitis")
    stretch_marks = fields.Boolean(string="Stretch Marks")
    body_circumference_reduction = fields.Boolean(string="Body Circumference Reduction")
    adiposity = fields.Boolean(string="Adiposity (Rabbits, Chubby, Llanticas)")
    hair_removal = fields.Boolean(string="Hair Removal")
    definitive_hair_removal = fields.Boolean(string="Definitive Hair Removal")
    dehydrated_skin = fields.Boolean(string="Dehydrated Skin")
    overweight = fields.Boolean(string="Overweight")
    skin_faccidity = fields.Boolean(string="Skin Flaccidity")
    prepost_operative = fields.Boolean(string="Pre-post Operative")
    postpartum_treatments = fields.Boolean(string="Postpartum treatments")
    body_description = fields.Text(string="Other Body Description")
    
    body_treatment_product_ids = fields.Many2many('product.product', 'body_patient_wish_treatment_product_ids_rel', 'wish_id', 'product_id', 'Body Treatments')
    body_nutrition_product_ids = fields.Many2many('product.product', 'body_patient_wish_nutrition_product_ids_rel', 'wish_id', 'product_id', 'Body Nutrition')
    body_upkeep_product_ids = fields.Many2many('product.product', 'body_patient_wish_upkeep_product_ids_rel', 'wish_id', 'product_id', 'Body Upkeep')

    #FACIAL TREATMENT PLAN
    scars = fields.Boolean(string="Acne / Scars")
    pigmentation = fields.Boolean(string="Pigmentation")
    expression_lines = fields.Boolean(string="Expression lines")
    wrinkles = fields.Boolean(string="Wrinkles")
    spots = fields.Boolean(string="Spots")
    flaccidity = fields.Boolean(string="Flaccidity")
    facial_description = fields.Text(string="Other Facial Description")

    facial_treatment_product_ids = fields.Many2many('product.product', 'facial_patient_wish_treatment_product_ids_rel', 'wish_id', 'product_id', 'Facial Treatments')
    facial_nutrition_product_ids = fields.Many2many('product.product', 'facial_patient_wish_nutrition_product_ids_rel', 'wish_id', 'product_id', 'Facial Nutrition')
    facial_upkeep_product_ids = fields.Many2many('product.product', 'facial_patient_wish_upkeep_product_ids_rel', 'wish_id', 'product_id', 'Facial Upkeep')

    attach_count = fields.Integer(compute="_pb_attachemnt_count", readonly=True, string="Documents")
    attachment_ids = fields.Many2many('ir.attachment', 'attachment_patient_wish_rel', 'treatment_id', 'attachment_id', compute="_pb_attachemnt_count", string="Attachments")
    document_preview_url = fields.Char(compute=_get_document_preview_url, string="Document Preview Link")

    def action_draft(self):
        self.state = 'draft'

    def action_confirm(self):
        self.state = 'confirm'

    def action_done(self):
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancel'

    def unlink(self):
        for rec in self:
            if rec.state not in ['cancel']:
                raise UserError(_('Record can be deleted only in Canceled state.'))
        return super(PbAestheticPatientWish, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['name'] = self.env['ir.sequence'].next_by_code('pb.aesthetic.patient.wish') or 'New Aesthetic Patient Wish'
        return super().create(vals_list)

    def create_procedure(self, products, treatment):
        Procedure = self.env['pb.patient.procedure']
        base_date = fields.Datetime.from_string(fields.Datetime.now())
        for product in products:
            if not product.product_tmpl_id.product_procedure_line_ids:
                Procedure.create({
                    'patient_id': treatment.patient_id.id,
                    'physician_id': treatment.physician_id and treatment.physician_id.id or False,
                    'product_id': product.id,
                    'treatment_id': treatment.id,
                })
            else:
                for line in product.product_tmpl_id.product_procedure_line_ids:
                    for count in range(0,line.repeat_for):
                        Procedure.create({
                            'patient_id': treatment.patient_id.id,
                            'physician_id': treatment.physician_id and treatment.physician_id.id or False,
                            'product_id': line.product_id.id,
                            'treatment_id': treatment.id,
                            'date': (base_date + timedelta(days=line.days_to_add)),
                        })

    def action_create_treatement(self):
        department = self.env['hr.department'].search([('department_type','=','aesthetic')], limit=1)
        treatment = self.env['hms.treatment'].create({
            'patient_id': self.patient_id.id,
            'physician_id': self.physician_id.id,
            'department_id': department.id if department else False,
            'aesthetic_wish_id': self.id,
        })
        body_treatments = self.body_treatment_product_ids + self.body_nutrition_product_ids + self.body_upkeep_product_ids
        self.create_procedure(body_treatments, treatment)
        facial_treatments = self.facial_treatment_product_ids + self.facial_nutrition_product_ids + self.facial_upkeep_product_ids
        self.create_procedure(facial_treatments, treatment)

        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_aesthetic.action_pb_treatment")
        action['context'] = {'default_patient_id': self.patient_id.id, 'default_physician_id': self.physician_id.id}
        action['views'] = [(self.env.ref('pb_hms.view_hospital_hms_treatment_form').id, 'form')]
        action['res_id'] = treatment.id
        self.treatment_id = treatment.id
        return action

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: