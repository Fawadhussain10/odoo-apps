#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PBProduct(models.Model):
    _inherit = 'product.template'

    hospital_product_type = fields.Selection(selection_add=[('vaccination','Vaccination')])
    age_for_vaccine = fields.Char("Age for Vaccine")
    vaccine_dose_number = fields.Integer("Dose")


class PBPatient(models.Model):
    _inherit = 'hms.patient'

    def _rec_count(self):
        rec = super(PBPatient, self)._rec_count()
        for rec in self:
            rec.vaccination_count = len(rec.vaccination_ids)

    vaccination_ids = fields.One2many('pb.vaccination', 'patient_id', 'Vaccination')
    vaccination_count = fields.Integer(compute='_rec_count', string='# Vaccination')

    def action_view_vaccinations(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_vaccination.action_vaccination_vac")
        action['domain'] = [('id', 'in', self.vaccination_ids.ids)]
        action['context'] = {'default_patient_id': self.id}
        return action


class Appointment(models.Model):
    _inherit = 'hms.appointment'

    def _vaccination_count(self):
        for rec in self:
            rec.vaccination_count = len(rec.vaccination_ids)

    vaccination_ids = fields.One2many('pb.vaccination', 'appointment_id', 'Vaccination')
    vaccination_count = fields.Integer(compute='_vaccination_count', string='# Vaccination')

    def action_view_vaccinations(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_vaccination.action_vaccination_vac")
        action['domain'] = [('id', 'in', self.vaccination_ids.ids)]
        action['context'] = {'default_appointment_id': self.id, 'default_patient_id': self.patient_id.id}
        return action


class StockMove(models.Model):
    _inherit = "stock.move"

    vaccination_id = fields.Many2one('pb.vaccination', string="Vaccination", ondelete="restrict")
