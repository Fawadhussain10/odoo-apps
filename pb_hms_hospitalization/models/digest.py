# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import AccessError


class Digest(models.Model):
    _inherit = 'digest.digest'

    kpi_pb_hospitalization_total = fields.Boolean('New Hospitalizations')
    kpi_pb_hospitalization_total_value = fields.Integer(compute='_compute_kpi_pb_hospitalization_total_value')

    def _compute_kpi_pb_hospitalization_total_value(self):
        if not self.env.user.has_group('pb_hms_base.group_hms_user'):
            raise AccessError(_("Do not have access, skip this data for user's digest email"))
        for record in self:
            start, end, company = record._get_kpi_compute_parameters()
            hospitalization = self.env['pb.hospitalization'].search_count([('company_id', '=', company.id), ('hospitalization_date', '>=', start), ('hospitalization_date', '<', end), ('state', 'not in', ['cancel'])])
            record.kpi_pb_hospitalization_total_value = hospitalization

    def _compute_kpis_actions(self, company, user):
        res = super(Digest, self)._compute_kpis_actions(company, user)
        res['kpi_pb_hospitalization_total'] = 'pb_hms_hospitalization.pb_action_form_inpatient&menu_id=%s' % self.env.ref('pb_hms_hospitalization.main_menu_hospitalization').id
        return res