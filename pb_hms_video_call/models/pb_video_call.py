# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class PbJitsiMeet(models.Model):
    _inherit = 'pb.video.call'

    appointment_id = fields.Many2one('hms.appointment', string='Appointment')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: