# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class PbHmsPatient(models.Model):
    _name="hms.patient"
    _inherit = ['hms.patient', 'pb.documnt.view.mixin']


class PbHmsTreatment(models.Model):
    _name="hms.treatment"
    _inherit = ['hms.treatment', 'pb.documnt.view.mixin']


class PbPatientProcedure(models.Model):
    _name="pb.patient.procedure"
    _inherit = ['pb.patient.procedure', 'pb.documnt.view.mixin']


class PbHmsAppointment(models.Model):
    _name="hms.appointment"
    _inherit = ['hms.appointment', 'pb.documnt.view.mixin']

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: