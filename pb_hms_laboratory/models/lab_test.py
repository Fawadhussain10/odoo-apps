# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PatientLabTest(models.Model):
    _inherit = "patient.laboratory.test"

    STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    appointment_id = fields.Many2one('hms.appointment', string='Appointment', ondelete='restrict')
    treatment_id = fields.Many2one('hms.treatment', string='Treatment', ondelete='restrict')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: