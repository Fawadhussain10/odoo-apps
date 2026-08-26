#-*- coding: utf-8 -*-

from odoo import models, fields, api,_ 


class HmsHospitalization(models.Model):
    _inherit = 'pb.hospitalization'

    def get_round_count(self):
        for record in self:
            record.ward_round_count = len(record.ward_round_ids)

    ward_round_count = fields.Integer(compute='get_round_count', string='Ward Round Count')
    ward_round_ids = fields.One2many('pb.nurse.ward.round', 'hospitalization_id', string='Ward Rounds')

    def pb_hospitalization_nurse_round_data(self, invoice_id=False):
        product_data = []
        ward_rounds_to_invoice = self.ward_round_ids.filtered(lambda s: not s.invoice_id)
        if ward_rounds_to_invoice:
            ward_data = {}
            for ward_round in ward_rounds_to_invoice:
                if ward_round.nurse_id.ward_round_product_id:
                    if ward_round.nurse_id.ward_round_product_id in ward_data:
                        ward_data[ward_round.nurse_id.ward_round_product_id] += 1
                    else:
                        ward_data[ward_round.nurse_id.ward_round_product_id] = 1
            if ward_data:
                product_data.append({
                    'name': _("Nurse Ward Round Charges"),
                })
            for product in ward_data:
                product_data.append({
                    'product_id': product,
                    'quantity': ward_data[product],
                })

            if invoice_id:
                ward_rounds_to_invoice.invoice_id = invoice_id.id

        return product_data

    def action_view_wardrounds(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_nursing.hms_ward_round_action")
        action['domain'] = [('hospitalization_id','=',self.id)]
        action['context'] = {'default_hospitalization_id': self.id, 'default_patient_id': self.patient_id.id, 'default_physician_id': self.physician_id.id}
        return action


class HospitalDepartment(models.Model):
    _inherit = 'hr.department'

    department_type = fields.Selection(selection_add=[('nurse', 'Nurse')])


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ward_round_product_id = fields.Many2one('product.product', domain=[('type','=','service')],
        string='Warround Service',  ondelete='cascade', help='Registration Product')


class PbPatientEvaluation(models.Model):
    _inherit = 'pb.patient.evaluation'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for record in res:
            if self.env.context.get('nurse_ward_round'):
                ward_round = self.env['pb.nurse.ward.round'].browse(self.env.context.get('nurse_ward_round'))
                ward_round.write({'evaluation_id': record.id})
        return res
