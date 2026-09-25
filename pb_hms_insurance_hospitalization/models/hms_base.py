# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError, UserError, RedirectWarning


class Attachments(models.Model):
    _inherit = "ir.attachment"

    hospitalization_id = fields.Many2one('pb.hospitalization', 'Hospitalization')


class PbHmsPackage(models.Model):
    _inherit = "pb.hms.package"

    def _claim_count(self):
        for rec in self:
            rec.claim_count = self.env['hms.insurance.claim'].search_count([('package_id', '=', rec.id)])

    claim_count = fields.Integer(string='# of Claims', compute='_claim_count', readonly=True)
    claim_ids = fields.One2many("hms.insurance.claim", "package_id", string='Claims', copy=False)

    def action_view_claims(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_insurance.action_insurance_claim")
        action['domain'] = [('id','in',self.claim_ids.ids)]
        return action


class Hospitalization(models.Model):
    _inherit = 'pb.hospitalization'

    def _rec_count(self):
        super(Hospitalization, self)._rec_count()
        for rec in self:
            rec.claim_count = len(rec.claim_ids)

    STATES={'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    cashless = fields.Boolean(string="Cashless")
    package_id = fields.Many2one('hms.insurance.claim', string='Package')
    package_invoice_id = fields.Many2one('account.move', string="Package Invoice")
    claim_ids = fields.One2many('hms.insurance.claim','hospitalization_id', "Claims")
    claim_count = fields.Integer(compute='_rec_count', string='# Claims')

    def action_patient_doc_view(self):
        action = self.env["ir.actions.actions"]._for_xml_id("base.action_attachment")
        action['domain'] = [('res_id', '=', self.patient_id.id), ('res_model', '=', 'hms.patient')]
        action['context'] = {
            'default_res_id': self.patient_id.id,
            'default_res_model': 'hms.patient',
            'default_patient_id': self.patient_id.id,
            'default_hospitalization_id': self.id,
            'default_is_document': True}
        return action

    def action_claim_view(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_insurance.action_insurance_claim")
        action['domain'] = [('patient_id', '=', self.patient_id.id),('hospitalization_id','=',self.id)]
        action['context'] = {
            'default_patient_id': self.patient_id.id,
            'default_hospitalization_id': self.id
        }
        return action

    def action_create_invoice(self):
        invoice_id = super(Hospitalization, self).action_create_invoice()
        return invoice_id

    def create_package_invoice(self):
        if not self.package_id:
            raise UserError(('Please select package first.'))

        product_data = []
        for line in self.package_id.order_line:
            if line.display_type:
                product_data.append({
                    'name': line.name,
                })
            else:
                product_data.append({
                    'product_id': line.product_id,
                    'name': line.name,
                    'price_unit': line.price_unit,
                    'quantity': line.product_uom_qty,
                    'discount': line.discount,
                })

        invoice = self.pb_create_invoice(partner=self.patient_id.partner_id, patient=self.patient_id, product_data=product_data, inv_data={})
        invoice.write({
            'claim_id': self.claim_ids and self.claim_ids[0].id or False,
            'hospitalization_id': self.id
        })
        self.package_invoice_id = invoice.id

