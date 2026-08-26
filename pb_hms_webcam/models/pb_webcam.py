# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HmsPatient(models.Model):
    _name = 'hms.patient'
    _inherit = ['hms.patient','pb.webcam.mixin']

    def pb_webcam_retrun_action(self):
        self.ensure_one()
        return self.env.ref('pb_hms_base.action_patient').id


class HmsPhysician(models.Model):
    _name = 'hms.physician'
    _inherit = ['hms.physician','pb.webcam.mixin']

    def pb_webcam_retrun_action(self):
        self.ensure_one()
        return self.env.ref('pb_hms_base.action_physician').id

