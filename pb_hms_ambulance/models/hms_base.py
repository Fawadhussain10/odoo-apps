# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _ambulance_drive_count(self):
        for rec in self: 
            rec.pb_ambulance_drive_count = len(rec.sudo().pb_ambulance_drive_ids.ids)

    is_driver = fields.Boolean('Is Driver')
    pb_ambulance_drive_ids = fields.One2many('pb.ambulance.service', 'driver_id', 'Ambulance Drives')
    pb_ambulance_drive_count = fields.Integer(compute="_ambulance_drive_count", string='#Ambulance Drives')

    def view_pb_ambulance_drive(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_ambulance.action_pb_ambulance_service")
        action['domain'] = [('driver_id', '=', self.id)]
        action['context'] = {'default_driver_id': self.id}
        return action


class HMSPatient(models.Model):
    _inherit = 'hms.patient'

    def _ambulance_service_count(self):
        for rec in self: 
            rec.pb_ambulance_service_count = len(rec.pb_ambulance_service_ids.ids)

    pb_ambulance_service_ids = fields.One2many('pb.ambulance.service','patient_id', 'Ambulance Services')
    pb_ambulance_service_count = fields.Integer(compute="_ambulance_service_count", string='#Ambulance Services', groups="pb_hms_ambulance.group_ambulance_service_user")

    def view_pb_ambulance_service(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_hms_ambulance.action_pb_ambulance_service")
        action['domain'] = [('patient_id', '=', self.id)]
        action['context'] = {'default_patient_id': self.id}
        return action


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hospital_product_type = fields.Selection(selection_add=[('ambulance','Ambulance')])


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    service_product_id = fields.Many2one('product.product', 
        domain=[('type','=','service')], string='Ambulance Invoicing Product', 
        ondelete='restrict', help='Ambulance Invoicing Product')
    user_id = fields.Many2one('res.users',  string='Doctor/Nurse', ondelete='restrict')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: