# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PbRadiologyRequest(models.Model):
    _inherit = 'pb.radiology.request'
    
    STATES = {'requested': [('readonly', True)], 'accepted': [('readonly', True)], 'in_progress': [('readonly', True)], 'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    hospitalization_id = fields.Many2one('pb.hospitalization', string='Hospitalization', ondelete='restrict')

    def prepare_test_result_data(self, line, patient):
        res = super(PbRadiologyRequest, self).prepare_test_result_data(line, patient)
        res['hospitalization_id'] = self.hospitalization_id and self.hospitalization_id.id or False
        return res

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: