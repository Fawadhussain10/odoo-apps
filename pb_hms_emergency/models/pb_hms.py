#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HrDepartment(models.Model): 
    _inherit = "hr.department"

    department_type = fields.Selection(selection_add=[('emergency_department','Emergency Department')])


class PBConsumableLine(models.Model):
    _inherit = "hms.consumable.line"

    emergency_id = fields.Many2one('pb.hms.emergency',  string='Emergency', ondelete="cascade")


class PBPrescriptionOrder(models.Model):
    _inherit = "prescription.order"

    emergency_id = fields.Many2one('pb.hms.emergency',  string='Emergency', ondelete="cascade")


class PatientAccommodationHistory(models.Model):
    _inherit = "patient.accommodation.history"

    emergency_id = fields.Many2one('pb.hms.emergency',  string='Emergency', ondelete="cascade")


class StockMove(models.Model):
    _inherit = "stock.move"
    
    emergency_id = fields.Many2one('pb.hms.emergency',  string='Emergency', ondelete="cascade")


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hospital_product_type = fields.Selection(selection_add=[('emergency','Emergency')])


class PBPatient (models.Model):
    _inherit = "hms.patient"

    def _pb_emergency_count(self):
        for rec in self: 
            rec.emergency_count = len(rec.emergency_ids)

    emergency_ids = fields.One2many("pb.hms.emergency", "patient_id", "Emergency")
    emergency_count = fields.Integer(string='# of Emergency', compute='_pb_emergency_count', readonly=True)

    def action_view_pb_emergency(self):
        emergency_ids = self.emergency_ids
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_emergency.action_hms_emergency")
        if len(emergency_ids) > 1:
            action['domain'] = [('id', 'in', emergency_ids.ids)]
        elif len(emergency_ids) == 1:
            action['views'] = [(self.env.ref('pb_hms_emergency.view_hms_emergency_form').id, 'form')]
            action['res_id'] = emergency_ids.ids[0]
        action.update({'context': {'default_patient_id': self.id}})
        return action


class PbHospitalization(models.Model): 
    _inherit = "pb.hospitalization"

    emergency_id = fields.Many2one('pb.hms.emergency',  string='Emergency', ondelete="cascade")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: