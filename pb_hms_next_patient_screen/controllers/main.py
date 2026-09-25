# -*- coding: utf-8 -*-

import ast

from odoo import http
from odoo.http import request
from odoo.tools.translate import _


class PbNextPatientScreen(http.Controller):

    def _get_screen_records(self, screen_id):
        screen = request.env['pb.hms.waiting.screen'].sudo().search([('id', '=', screen_id)])
        ResModel = request.env[screen.res_model_id.model]
        domain = [('company_id', '=', screen.company_id.id)]
        if screen and screen.physician_ids and screen.pb_physician_field_id:
            domain += [(screen.pb_physician_field_id.name, 'in', screen.physician_ids.ids)]

        if screen.pb_states_to_include and screen.pb_state_field_id:
            domain += [(screen.pb_state_field_id.name, 'in', ast.literal_eval(screen.pb_states_to_include))]
        limit = screen.pb_number_of_records or 5
        records = ResModel.sudo().search(domain, order="id asc", limit=limit)
        return screen, records, ResModel

    @http.route(['/pb/waitingscreen/<int:screen>'], type='http', auth="user", website=True, sitemap=False)
    def pb_waiting_screen(self, screen=False, **kw):
        screen_rec, records, ResModel = self._get_screen_records(screen)
        return request.render("pb_hms_next_patient_screen.next_patient_view",
            {'pb_ws': screen_rec, 'records': records, 'ResModel': ResModel})

    @http.route(['/pb/waitingscreen/<int:screen>/rows'], type='http', auth="user", website=True, sitemap=False)
    def pb_waiting_screen_rows(self, screen=False, **kw):
        # Polled by the screen's own JS every pb_refresh_time seconds so the
        # display updates smoothly (swap just the rows) instead of a full
        # location.reload() flashing the whole kiosk screen each cycle.
        screen_rec, records, ResModel = self._get_screen_records(screen)
        return request.render("pb_hms_next_patient_screen.next_patient_rows",
            {'pb_ws': screen_rec, 'records': records, 'ResModel': ResModel})

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: