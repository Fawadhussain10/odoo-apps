# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError, UserError, RedirectWarning


class PbInsurancePlan(models.Model):
    _name = 'pb.insurance.plan'
    _description = "Insurance Plan"
    _order = "sequence"

    name = fields.Text(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string="Active", default=True)
    insurance_company_id = fields.Many2one('hms.insurance.company', string ="Insurance Company", required=True)

    allow_appointment_insurance = fields.Boolean(string="Insured Appointments")
    app_insurance_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fix', 'Fix-amount')], 'Appointment Insurance Type', default='percentage', required=True)
    app_insurance_amount = fields.Float(string="Appointment Co-payment", help="The patient should pay specific amount 50QR")
    app_insurance_percentage = fields.Float(string="Appointment Insured Percentage")
    app_insurance_limit = fields.Float(string="Appointment Insurance Limit")
    create_claim = fields.Boolean(string="Appointment Create Claim")
    
    allow_pharmacy_insurance = fields.Boolean(string="Insured Pharmacy", default=False)
    pha_insurance_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fix', 'Fix-amount')], 'Pharmacy Insurance Type', default='percentage', required=True)
    pha_insurance_amount = fields.Float(string="Pharmacy Co-payment", help="The patient should pay specific amount 50QR")
    pha_insurance_percentage = fields.Float(string="Pharmacy Insured Percentage")
    pha_insurance_limit = fields.Float(string="Pharmacy Insurance Limit")
    pha_create_claim = fields.Boolean(string="Pharmacy Create Claim", default=False)

    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist',
        help="If you change the pricelist, only newly added lines will be affected.")
    note = fields.Text("Notes")


class InsuranceCompany(models.Model):
    _name = 'hms.insurance.company'
    _description = "Insurance Company"
    _inherits = {
        'res.partner': 'partner_id',
    }

    description = fields.Text()
    partner_id = fields.Many2one('res.partner', 'Partner', ondelete='restrict', required=True)
    active = fields.Boolean(string="Active", default=True)

    #PB NOTE: To avoid dependcay issue this code is here. 
    #Move to related module if new one is creatd.
    @api.model
    def GetInsuranceCompany(self, args, **kwargs):
        """
        var model = 'hms.insurance.company';
        var method = 'GetInsuranceCompany';

        var args = [
            { }
        ];
        """
        insurance_companies = self.sudo().search([])
        insurance_company_data = []
        for ic in insurance_companies:
            insurance_company_data.append({
                'id': ic.id,
                'name': ic.name,
            })
        return insurance_company_data


class Insurance(models.Model):
    _name = 'hms.patient.insurance'
    _description = "Patient Insurance"
    _rec_name = 'policy_number'
    
    patient_id = fields.Many2one('hms.patient', string ='Patient', ondelete='restrict', required=True)
    insurance_company_id = fields.Many2one('hms.insurance.company', string ="Insurance Company", required=True)
    insurance_plan_id = fields.Many2one('pb.insurance.plan', string ="Insurance Plan")
    policy_number = fields.Char(string ="Policy Number", required=True)
    insured_value = fields.Float(string ="Insured Value")
    validity = fields.Date(string="Validity")
    active = fields.Boolean(string="Active", default=True)
    note = fields.Text("Notes")

    allow_appointment_insurance = fields.Boolean(string="Insured Appointments")
    app_insurance_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fix', 'Fix-amount')], 'Appointment Insurance Type', default='percentage', required=True)
    app_insurance_amount = fields.Float(string="Appointment Co-payment", help="The patient should pay specific amount 50QR")
    app_insurance_percentage = fields.Float(string="Appointment Insured Percentage")
    app_insurance_limit = fields.Float(string="Appointment Insurance Limit")
    create_claim = fields.Boolean(string="Appointment Create Claim")
    
    allow_pharmacy_insurance = fields.Boolean(string="Insured Pharmacy", default=False)
    pha_insurance_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fix', 'Fix-amount')], 'Pharmacy Insurance Type', default='percentage', required=True)
    pha_insurance_amount = fields.Float(string="Pharmacy Co-payment", help="The patient should pay specific amount 50QR")
    pha_insurance_percentage = fields.Float(string="Pharmacy Insured Percentage")
    pha_insurance_limit = fields.Float(string="Pharmacy Insurance Limit")
    pha_create_claim = fields.Boolean(string="Pharmacy Create Claim", default=False)

    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist',
        help="If you change the pricelist, only newly added lines will be affected.")
    company_id = fields.Many2one('res.company', 'Hospital', default=lambda self: self.env.company)

    @api.depends('policy_number', 'insurance_plan_id.name', 'insurance_company_id.name')
    def _compute_display_name(self):
        for rec in self:
            name = rec.policy_number
            if rec.insurance_plan_id:
                name += ' - ' + rec.insurance_plan_id.name
            elif rec.insurance_company_id:
                name += ' - ' + rec.insurance_company_id.name
            rec.display_name = name

    @api.onchange('insurance_company_id')
    def onchange_insurance_company(self):
        if self.insurance_company_id and self.insurance_company_id.property_product_pricelist:
            self.pricelist_id = self.insurance_company_id.property_product_pricelist.id

    @api.onchange('insurance_plan_id')
    def onchange_insurance_plan(self):
        if self.insurance_plan_id:
            plan_id = self.insurance_plan_id
            self.pricelist_id = plan_id.pricelist_id and plan_id.pricelist_id.id
            self.allow_appointment_insurance = self.allow_appointment_insurance
            self.app_insurance_type = self.app_insurance_type
            self.app_insurance_amount = self.app_insurance_amount
            self.app_insurance_percentage = self.app_insurance_percentage
            self.app_insurance_limit = self.app_insurance_limit
            self.create_claim = self.create_claim
            self.allow_pharmacy_insurance = self.allow_pharmacy_insurance
            self.pha_insurance_type = self.pha_insurance_type
            self.pha_insurance_amount = self.pha_insurance_amount
            self.pha_insurance_percentage = self.pha_insurance_percentage
            self.pha_insurance_limit = self.pha_insurance_limit
            self.pha_create_claim = self.pha_create_claim
            
    @api.model
    def archive_expired_policy(self):
        records = self.search([('validity','<', fields.Date.today())])
        records.write({'active': False})


class InsuranceTPA(models.Model):
    _name = 'insurance.tpa'
    _description = "Insurance TPA"
    _inherits = {
        'res.partner': 'partner_id',
    }

    partner_id = fields.Many2one('res.partner', 'Partner', required=True, ondelete='restrict')
    active = fields.Boolean('Active', default=True)


class InsuranceChecklistTemp(models.Model):
    _name = 'hms.insurance.checklist.template'
    _description = "Insurance Checklist Template"

    name = fields.Char('Name')
    active = fields.Boolean('Active', default=True)


class RequiredDocuments(models.Model):
    _name = 'hms.insurance.req.doc'
    _description = "Insurance Req Doc"
    
    name = fields.Char('Name')
    active = fields.Boolean('Active', default=True)


class InsuCheckList(models.Model):
    _name="hms.insurance.checklist"
    _description = "Insurance Checklist"

    name = fields.Char(string="Name")
    is_done = fields.Boolean(string="Y/N")
    remark = fields.Char(string="Remarks")
    claim_id = fields.Many2one("hms.insurance.claim", string="Claim")


class SplitInvoiceWizard(models.TransientModel):
    _inherit = 'split.invoice.wizard'

    @api.model_create_multi
    def create(self, vals_list):
        insurance_id = self.env.context.get('insurance_id')
        insurance_type = self.env.context.get('insurance_type')
        insurance_amount = self.env.context.get('insurance_amount')
        values = {}

        if insurance_id and insurance_type=='fix':
            for values in vals_list:
                insurance_id = self.env['hms.patient.insurance'].browse(insurance_id)
                active_record = self.env['account.move'].browse(self.env.context.get('active_id'))
                lines = []
                app_insurance_amount = insurance_amount
                rem_insurance_amount = insurance_amount
                invoice_line = active_record.invoice_line_ids[0]
                for line in active_record.invoice_line_ids:
                    if app_insurance_amount and rem_insurance_amount:
                        if rem_insurance_amount<=line.price_unit:
                            price_unit = line.price_unit - rem_insurance_amount
                            rem_insurance_amount = 0
                        else:
                            price_unit = line.price_unit
                            rem_insurance_amount -= price_unit
                    else:
                        price_unit = line.price_unit

                    lines.append((0,0,{
                        'name': line.name,
                        'product_id': line.product_id and line.product_id.id or False,
                        'line_id': line.id,
                        'quantity': line.quantity,
                        'price': line.price_unit,
                        'qty_to_split': 1,
                        'price_to_split': price_unit,
                        'display_type': line.display_type,
                    }))
                values.update({
                    'split_selection': 'lines', 
                    'line_split_selection': 'price', 
                    'line_ids': lines,
                    'partner_id': insurance_id.insurance_company_id.partner_id.id if insurance_id.insurance_company_id.partner_id else self.partner_id.id
                })

        return super().create(vals_list)
