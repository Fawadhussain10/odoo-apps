# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError, UserError, RedirectWarning


class PBPatient(models.Model):
    _inherit = 'hms.patient'

    def _rec_count(self):
        rec = super(PBPatient, self)._rec_count()
        for rec in self:
            rec.claim_count = len(rec.claim_ids)

    claim_ids = fields.One2many('hms.insurance.claim', 'patient_id',string='Claims')
    claim_count = fields.Integer(compute='_rec_count', string='# Claims')
    insurance_ids = fields.One2many('hms.patient.insurance', 'patient_id', string='Insurance')

    def action_insurance_policy(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_insurance.action_hms_patient_insurance")
        action['domain'] = [('patient_id', '=', self.id)]
        action['context'] = {
            'default_patient_id': self.id,
        }
        return action

    def action_claim_view(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_insurance.action_insurance_claim")
        action['domain'] = [('patient_id', '=', self.id)]
        action['context'] = {
            'default_patient_id': self.id,
        }
        return action


class PBAppointment(models.Model):
    _inherit = 'hms.appointment'

    READONLY_STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    insurance_id = fields.Many2one('hms.patient.insurance', string='Insurance Policy')
    claim_id = fields.Many2one('hms.insurance.claim', string='Claim')
    insurance_company_id = fields.Many2one('hms.insurance.company', related='insurance_id.insurance_company_id', string='Insurance Company', readonly=True, store=True)
    app_insurance_percentage = fields.Float(related='insurance_id.app_insurance_percentage', string="Insured Percentage", readonly=True)

    def create_invoice(self):
        res = super(PBAppointment, self).create_invoice()
        if self.invoice_id and self.insurance_id and (self.insurance_id.app_insurance_limit >= self.invoice_id.amount_total or self.insurance_id.app_insurance_limit==0):
            insurace_invoice = self.invoice_id.pb_create_insurace_invoice(self.insurance_id, self.insurance_id.app_insurance_type, 
                self.insurance_id.app_insurance_amount, self.insurance_id.app_insurance_percentage, 
                self, 'appointment', 'appointment_id', self.insurance_id.create_claim)
            if insurace_invoice and insurace_invoice.claim_id:
                self.claim_id = insurace_invoice.claim_id.id
        return res

    def create_consumed_prod_invoice(self):
        res = super(PBAppointment, self).create_consumed_prod_invoice()
        if self.consumable_invoice_id and self.insurance_id and (self.insurance_id.app_insurance_limit >= self.consumable_invoice_id.amount_total or self.insurance_id.app_insurance_limit==0):
            insurace_invoice = self.consumable_invoice_id.pb_create_insurace_invoice(self.insurance_id, self.insurance_id.app_insurance_type, 
                self.insurance_id.app_insurance_amount, self.insurance_id.app_insurance_percentage, 
                self, 'appointment', 'appointment_id', self.insurance_id.create_claim)
            if insurace_invoice and insurace_invoice.claim_id:
                self.claim_id = insurace_invoice.claim_id.id
        return res

    @api.onchange('patient_id')
    def onchange_patient_id(self):
        super(PBAppointment, self).onchange_patient_id()
        allow_appointment_insurances = self.patient_id.insurance_ids.filtered(lambda x: x.allow_appointment_insurance)
        pricelist_id = insurance_id = False
        if self.patient_id and allow_appointment_insurances:
            insurance = allow_appointment_insurances[0]
            insurance_id = insurance.id
            pricelist_id = insurance.pricelist_id and insurance.pricelist_id.id or False
    
        self.insurance_id = insurance_id
        self.pricelist_id = pricelist_id


class Invoice(models.Model):
    _inherit = 'account.move'

    insurance_id = fields.Many2one('hms.patient.insurance', string='Insurance Policy')
    claim_id = fields.Many2one('hms.insurance.claim', 'Claim')
    insurance_company_id = fields.Many2one('hms.insurance.company', related='claim_id.insurance_company_id', string='Insurance Company', readonly=True)
    claim_sheet_id = fields.Many2one('pb.claim.sheet', string='Claim Sheet')

    #PB: Hook method to avoid error of spit invocie on auto invoice.
    def pb_check_auto_spliting_possibility(self, insurance_id):
        return True

    def pb_create_insurace_invoice(self, insurance, insurance_type, insurance_amount, insurance_percentage, pb_object, inv_type, rec_field, create_claim=False):
        can_be_splited = self.pb_check_auto_spliting_possibility(insurance)
        claim_id = False
        insurance_invoice_id = False
        if can_be_splited:
            split_context = {
                'active_model':'account.move', 
                'active_id': self.id,
                'insurance_id': insurance.id,
                'insurance_type': insurance_type,
                'insurance_amount': insurance_amount,
            }
            wiz_id = self.env['split.invoice.wizard'].with_context(split_context).create({
                'split_selection': 'invoice',
                'percentage': insurance_percentage,
                'partner_id': insurance.insurance_company_id.partner_id.id if insurance.insurance_company_id.partner_id else self.partner_id.id,
            })
            insurance_invoice_id = wiz_id.split_record()
            insurance_invoice_id.write({
                'insurance_id': insurance.id,
                rec_field: pb_object.id,
                'ref': pb_object.name,
                'invoice_origin': pb_object.name,
                'hospital_invoice_type': inv_type,
            })

            if insurance_invoice_id and create_claim:
                claim_id = self.env['hms.insurance.claim'].create({
                    'patient_id': self.patient_id.id,
                    'insurance_id': insurance.id,
                    'claim_for': inv_type,
                    rec_field: pb_object.id,
                    'amount_requested': insurance_invoice_id.amount_total,
                })
                insurance_invoice_id.claim_id = claim_id.id
        return insurance_invoice_id

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    claim_id = fields.Many2one('hms.insurance.claim', 'Claim')
    insurance_company_id = fields.Many2one('hms.insurance.company', related='claim_id.insurance_company_id', string='Insurance Company', readonly=True)

class Attachments(models.Model):
    _inherit = "ir.attachment"

    patient_id = fields.Many2one('hms.patient', 'Patient')
    claim_id = fields.Many2one('hms.insurance.claim', 'Claim')


class product_template(models.Model):
    _inherit = "product.template"

    hospital_product_type = fields.Selection(selection_add=[('insurance_plan', 'Insurance Plan')])

class PBPrescriptionOrder(models.Model):
    _inherit = 'prescription.order'

    insurance_id = fields.Many2one('hms.patient.insurance', string='Insurance Policy')
    claim_id = fields.Many2one('hms.insurance.claim', string='Claim')
    insurance_company_id = fields.Many2one('hms.insurance.company', related='insurance_id.insurance_company_id', string='Insurance Company', readonly=True, store=True)
    pha_insurance_percentage = fields.Float(related='insurance_id.pha_insurance_percentage', string="Insured Percentage", readonly=True)

    @api.onchange('patient_id')
    def onchange_patient_id(self):
        allow_pharmacy_insurance = self.patient_id.insurance_ids.filtered(lambda x: x.allow_pharmacy_insurance)
        if self.patient_id and allow_pharmacy_insurance:
            insurance = allow_pharmacy_insurance[0]
            self.insurance_id = insurance.id

    def create_invoice(self):
        res = super(PBPrescriptionOrder, self).create_invoice()
        if self.invoice_id and self.insurance_id and (self.insurance_id.pha_insurance_limit >= self.invoice_id.amount_total or self.insurance_id.pha_insurance_limit==0):
            insurace_invoice = self.invoice_id.pb_create_insurace_invoice(self.insurance_id, self.insurance_id.pha_insurance_type, 
                self.insurance_id.pha_insurance_amount, self.insurance_id.pha_insurance_percentage, 
                self, 'pharmacy', 'prescription_id', self.insurance_id.pha_create_claim)
            if insurace_invoice and insurace_invoice.claim_id:
                self.claim_id = insurace_invoice.claim_id.id
