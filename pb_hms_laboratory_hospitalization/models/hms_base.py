# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class Hospitalization(models.Model):
    _inherit = "pb.hospitalization"

    def _rec_count(self):
        rec = super(Hospitalization, self)._rec_count()
        for rec in self:
            rec.request_count = len(rec.request_ids)
            rec.test_count = len(rec.test_ids)

    request_ids = fields.One2many('pb.laboratory.request', 'hospitalization_id', string='Lab Requests')
    request_count = fields.Integer(compute='_rec_count', string='# Pathology Requests')
    test_ids = fields.One2many('patient.laboratory.test', 'hospitalization_id', string='Lab Tests')
    test_count = fields.Integer(compute='_rec_count', string='#Pathology Lab Tests')

    def action_lab_request(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_laboratory.hms_action_lab_test_request")
        action['domain'] = [('id','in',self.request_ids.ids)]
        action['context'] = {'default_patient_id': self.patient_id.id, 'default_hospitalization_id': self.id}
        action['views'] = [(self.env.ref('pb_laboratory.patient_laboratory_test_request_form').id, 'form')]
        return action

    def action_lab_requests(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_laboratory.hms_action_lab_test_request")
        action['domain'] = [('id','in',self.request_ids.ids)]
        action['context'] = {'default_patient_id': self.patient_id.id, 'default_hospitalization_id': self.id}
        return action

    def action_view_test_results(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_laboratory.action_lab_result")
        action['domain'] = [('id','in',self.test_ids.ids)]
        action['context'] = {'default_patient_id': self.patient_id.id, 'default_hospitalization_id': self.id}
        return action

    def pb_hospitalization_lab_data(self, invoice_id=False):
        lab_data = []
        request_ids = self.mapped('request_ids').filtered(lambda req: req.state=='to_invoice' and not req.invoice_id)
        if request_ids:
            lab_data.append({'name': _("Laboratory Charges")})
            for record in request_ids:
                pricelist_id = record.pricelist_id and record.pricelist_id.id or False
                for line in record.line_ids:
                    lab_data.append({
                        'product_id': line.test_id.product_id,
                        'price_unit': line.sale_price,
                        'quantity': line.quantity,
                        'pricelist_id': pricelist_id,
                    })
                if invoice_id:
                    record.invoice_id = invoice_id.id
                    #PB: it is possible that on hospitalization done we can mark record as done or we can do it on invoice validation also.
                    record.button_done()
        return lab_data

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: