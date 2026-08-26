# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta


class PbHmsEmergency(models.Model):
    _name = 'pb.hms.emergency'
    _description = 'Medical Emergency'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'pb.hms.mixin', 'pb.documnt.mixin'] 
    _order = "id desc"

    @api.model
    def _get_service_id(self):
        service = False
        if self.env.user.company_id.sudo().pb_emergency_service_product_id:
            service = self.env.user.company_id.sudo().pb_emergency_service_product_id.id
        return service

    def _pb_get_invoice_count(self):
        AccountMove = self.env['account.move']
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    @api.depends('patient_id', 'patient_id.birthday', 'date')
    def get_patient_age(self):
        for rec in self:
            age = ''
            if rec.patient_id.birthday:
                end_data = rec.date or fields.Datetime.now()
                delta = relativedelta(end_data, rec.patient_id.birthday)
                if delta.years <= 2:
                    age = str(delta.years) + _(" Year") + str(delta.months) + _(" Month ") + str(delta.days) + _(" Days")
                else:
                    age = str(delta.years) + _(" Year")
            rec.age = age

    @api.depends('evaluation_ids', 'evaluation_ids.state')
    def _get_evaluation(self):
        for rec in self:
            rec.evaluation_id = rec.evaluation_ids[0].id if rec.evaluation_ids else False

    READONLY_STATES = {'done': [('readonly', True)]}

    name = fields.Char(string='Name', copy=False, tracking=True)
    patient_id = fields.Many2one('hms.patient', ondelete='restrict',  string='Patient',
        required=True, index=True, help='Patient Name', tracking=True)
    image_128 = fields.Binary(related='patient_id.image_128',string='Image', readonly=True)
    physician_id = fields.Many2one('hms.physician', ondelete='restrict', string='Physician', 
        index=True, help='Physician\'s Name', tracking=True)
    department_id = fields.Many2one('hr.department', ondelete='restrict', 
        domain=[('patient_department', '=', True)], string='Department', tracking=True)
    state = fields.Selection([
            ('draft', 'Draft'),
            ('under_care', 'Under Care'),
            ('to_invoice', 'To Invoice'),
            ('done', 'Done'),
        ], string='Status',default='draft', required=True, copy=False, tracking=True)
    date = fields.Datetime(string='Admission Date', default=fields.Datetime.now, tracking=True, copy=False)
    discharge_date = fields.Datetime (string='Discharge date', states=READONLY_STATES, tracking=True)

    product_id = fields.Many2one('product.product', ondelete='restrict', 
        string='Emergency Service', help="Emergency Service Charge", 
        domain=[('hospital_product_type', '=', "emergency")], required=True, 
        default=_get_service_id)
    invoice_exempt = fields.Boolean(string='Invoice Exempt')
    ward_id = fields.Many2one('hospital.ward', ondelete="restrict", string='Ward/Room')
    bed_id = fields.Many2one ('hospital.bed', ondelete="restrict", string='Bed No.', states=READONLY_STATES)
    responsible_id = fields.Many2one('hms.physician', "Responsible Jr. Doctor")
    notes = fields.Text(string='Notes')
    age = fields.Char(compute="get_patient_age", string='Age', store=True,
        help="Computed patient age at the moment of the record creation")
    company_id = fields.Many2one('res.company', ondelete='restrict',
        string='Hospital', default=lambda self: self.env.company)
    diseases_ids = fields.Many2many('hms.diseases', 'diseases_emergency_rel', 'diseas_id', 'emergency_id', 'Diseases')
    ref_physician_id = fields.Many2one('res.partner', ondelete='restrict', string='Referring Physician', 
        index=True, help='Referring Physician')
    user_id = fields.Many2one('res.users',string='Responsible',
        ondelete='cascade', help='Responsible User for appointment validation And further Followup.')
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', check_company=True, 
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="If you change the pricelist, related invoice will be affected.")

    evaluation_ids = fields.One2many('pb.patient.evaluation', 'appointment_id', 'Evaluations')
    evaluation_id = fields.Many2one('pb.patient.evaluation', ondelete='restrict', compute=_get_evaluation,
        string='Evaluation', store=True)
    prescription_ids = fields.One2many('prescription.order', 'emergency_id', 'Prescriptions', copy=False)

    weight = fields.Float(related="evaluation_id.weight", string='Weight', help="Weight in KG")
    height = fields.Float(related="evaluation_id.height", string='Height', help="Height in cm")
    temp = fields.Float(related="evaluation_id.temp", string='Temp')
    hr = fields.Integer(related="evaluation_id.hr", string='HR', help="Heart Rate")
    rr = fields.Integer(related="evaluation_id.rr", string='RR', help='Respiratory Rate')
    systolic_bp = fields.Integer(related="evaluation_id.systolic_bp", string="Systolic BP")
    diastolic_bp = fields.Integer(related="evaluation_id.diastolic_bp", string="Diastolic BP")
    spo2 = fields.Integer(related="evaluation_id.spo2", string='SpO2', 
        help='Oxygen Saturation, percentage of oxygen bound to hemoglobin')
    rbs = fields.Integer(related="evaluation_id.rbs", string='RBS', 
        help="Random blood sugar measures blood glucose regardless of when you last ate.")
    bmi = fields.Float(related="evaluation_id.bmi", string='Body Mass Index')
    bmi_state = fields.Selection(related="evaluation_id.bmi_state", string='BMI State')
    pb_weight_name = fields.Char(related="evaluation_id.pb_weight_name", string='Patient Weight unit of measure label')
    pb_height_name = fields.Char(related="evaluation_id.pb_height_name", string='Patient Height unit of measure label')
    pb_temp_name = fields.Char(related="evaluation_id.pb_temp_name", string='Patient Temp unit of measure label')
    pb_spo2_name = fields.Char(related="evaluation_id.pb_spo2_name", string='Patient SpO2 unit of measure label')
    pb_rbs_name = fields.Char(related="evaluation_id.pb_rbs_name", string='Patient RBS unit of measure label')
    
    pain_level = fields.Selection(related="evaluation_id.pain_level", string="Pain Level")
    pain = fields.Selection(related="evaluation_id.pain", string="Pain")

    lab_report = fields.Text(string='Lab Report', help="Details of the lab report.")
    radiological_report = fields.Text(string='Radiological Report', help="Details of the Radiological Report") 
    differencial_diagnosis = fields.Text(string='Differential Diagnosis', help="The process of weighing the probability of one disease versus that of other diseases possibly accounting for a patient's illness.")
    medical_advice = fields.Text(string='Medical Advice', help="The provision of a formal professional opinion regarding what a specific individual should or should not do to restore or preserve health.")

    medical_history = fields.Text(related='patient_id.medical_history', 
        string="Past Medical History", readonly=True)
    patient_diseases_ids = fields.One2many('hms.patient.disease', readonly=True, 
        related='patient_id.patient_diseases_ids', string='Disease History')

    pb_kit_id = fields.Many2one('pb.product.kit', string='Kit')
    pb_kit_qty = fields.Integer("Kit Qty", default=1)
    consumable_line_ids = fields.One2many('hms.consumable.line', 'emergency_id',
        string='Consumable Line', copy=False)

    invoice_ids = fields.One2many("account.move", "emergency_id", string="Invoices", groups="account.group_account_invoice")
    invoice_count = fields.Integer(compute="_pb_get_invoice_count", string="#Invoices", groups="account.group_account_invoice")
    accommodation_history_ids = fields.One2many("patient.accommodation.history", "emergency_id", 
        string="Accommodation History")
    hospitalization_ids = fields.One2many('pb.hospitalization', 'emergency_id',string='Hospitalizations')

    def action_hospitalization(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_hospitalization.pb_action_form_inpatient")
        action['domain'] = [('emergency_id', '=', self.id)]
        action['context'] = {'default_patient_id': self.patient_id.id, 'default_emergency_id': self.id, 'default_physician_id': self.physician_id.id}
        return action

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('name', 'New Emergency') == 'New Emergency':
                values['name'] = self.env['ir.sequence'].next_by_code('pb.hms.emergency') or 'New Emergency'
        return super().create(vals_list)

    def unlink(self):
        for data in self:
            if data.state in ['done']:
                raise UserError(_('You can not delete record in done state'))
        return super(PbHmsEmergency, self).unlink()

    def under_care(self):
        History = self.env['patient.accommodation.history']
        for rec in self:
            rec.bed_id.sudo().write({'state': 'reserved'})
            rec.state = 'under_care'
            History.sudo().create({
                'emergency_id': rec.id,
                'patient_id': rec.patient_id.id,
                'ward_id': self.ward_id.id,
                'bed_id': self.bed_id.id,
                'start_date': datetime.now(),
            })
 
    # def action_refer_doctor(self):
    #     action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_emergency.action_hms_emergency")
    #     action['domain'] = [('patient_id','=',self.id)]
    #     action['context'] = {'default_patient_id': self.patient_id.id, 'default_physician_id': self.physician_id.id}
    #     action['views'] = [(self.env.ref('pb_hms_emergency.view_hms_emergency_form').id, 'form')]
    #     return action

    def action_prescription(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms.act_open_hms_prescription_order_view")
        action['domain'] = [('emergency_id', '=', self.id)]
        action['context'] = {
                'default_patient_id': self.patient_id.id,
                'default_physician_id': self.physician_id.id,
                'default_diseases_ids': [(6,0,self.diseases_ids.ids)],
                'default_emergency_id': self.id}
        return action

    def button_pres_req(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms.act_open_hms_prescription_order_view")        
        action['domain'] = [('emergency_id', '=', self.id)]
        action['views'] = [(self.env.ref('pb_hms.view_hms_prescription_order_form').id, 'form')]
        action['context'] = {
                'default_patient_id': self.patient_id.id,
                'default_physician_id':self.physician_id.id,
                'default_diseases_ids': [(6,0,self.diseases_ids.ids)],
                'default_emergency_id': self.id}
        return action

    def action_create_evaluation(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms.action_pb_patient_evaluation_popup")
        action['domain'] = [('patient_id','=',self.id)]
        action['context'] = {'default_patient_id': self.patient_id.id, 'default_physician_id': self.physician_id.id, 'default_appointment_id': self.id}
        return action

    def view_invoice(self):
        emergency_invoices = self.invoice_ids
        action = self.pb_action_view_invoice(emergency_invoices)
        action['context'].update({
            'default_partner_id': self.patient_id.partner_id.id,
            'default_patient_id': self.patient_id.id,
            'default_emergency_id': self.id,
            'default_ref_physician_id': self.ref_physician_id and self.ref_physician_id.id or False,
            'default_physician_id': self.physician_id and self.physician_id.id or False,
            'default_hospital_invoice_type': 'emergency',
            'default_ref': self.name,
        })
        return action

    def create_invoice(self):
        product_id = self.product_id
        if not product_id:
            raise UserError(_("Please Set Consultation Service first."))
        product_data = [{'product_id': product_id}]
        for consumable in self.consumable_line_ids:
            product_data.append({
                'product_id': consumable.product_id,
                'quantity': consumable.qty,
                'lot_id': consumable.lot_id and consumable.lot_id.id or False,
            })
        inv_data = {
            'ref_physician_id': self.ref_physician_id and self.ref_physician_id.id or False,
            'physician_id': self.physician_id and self.physician_id.id or False,
            'emergency_id': self.id,
            'hospital_invoice_type': 'emergency',
        }

        pb_context = {}
        if self.pricelist_id:
            pb_context.update({'pb_pricelist_id': self.pricelist_id.id})
        if self.physician_id:
            pb_context.update({'commission_partner_ids':self.physician_id.partner_id.id})
        invoice = self.with_context(pb_context).pb_create_invoice(partner=self.patient_id.partner_id, patient=self.patient_id, product_data=product_data, inv_data=inv_data)
        invoice.emergency_id = self.id
        self.state = 'done'

    def pb_get_consume_locations(self):
        company = self.company_id.sudo()
        if not company.emergency_usage_location_id:
            raise UserError(_('Please define a location where the consumables will be used during the emergecny.'))
        if not company.emergency_stock_location_id:
            raise UserError(_('Please define a emergecny location from where the consumables will be taken.'))

        dest_location_id  = company.emergency_usage_location_id.id
        source_location_id  = company.emergency_stock_location_id.id
        return source_location_id, dest_location_id

    def consume_emergency_material(self):
        for rec in self:
            source_location_id, dest_location_id = rec.pb_get_consume_locations()
            for line in rec.consumable_line_ids.filtered(lambda s: not s.move_id):
                if line.product_id.is_kit_product:
                    move_ids = []
                    for kit_line in line.product_id.pb_kit_line_ids:
                        if kit_line.product_id.tracking!='none':
                            raise UserError("In Consumable lines Kit product with component having lot/serial tracking is not allowed. Please remove such kit product from consumable lines.")
                        move = self.consume_material(source_location_id, dest_location_id,
                            {'product': kit_line.product_id, 'qty': kit_line.product_qty * line.qty})
                        move.emergency_id = rec.id
                        move_ids.append(move.id)
                    #Set move_id on line also to avoid issue
                    line.move_id = move.id
                    line.move_ids = [(6,0,move_ids)]
                else:
                    move = self.consume_material(source_location_id, dest_location_id,
                        {'product': line.product_id, 'qty': line.qty, 'lot_id': line.lot_id and line.lot_id.id or False,})
                    move.emergency_id = rec.id
                    line.move_id = move.id

    def action_discharge(self):
        for rec in self:
            rec.bed_id.sudo().write({'state': 'free'})
            self.consume_emergency_material()
            if self.invoice_exempt or (not self.env.user.company_id.emergency_invoicing):
                rec.state = 'done'
            else:
                rec.state = 'to_invoice'
            rec.discharge_date = datetime.now()
            for history in rec.accommodation_history_ids:
                if rec.bed_id == history.bed_id:
                    history.end_date = datetime.now()        

    def get_pb_kit_lines(self):
        if not self.pb_kit_id:
            raise UserError("Please Select Kit first.")

        lines = []
        for line in self.pb_kit_id.pb_kit_line_ids:
            lines.append((0,0,{
                'product_id': line.product_id.id,
                'product_uom_id': line.product_id.uom_id.id,
                'qty': line.product_qty * self.pb_kit_qty,
            }))
        self.consumable_line_ids = lines
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:   