# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.tools.translate import _


class PbNextPatientScreen(http.Controller):

    @http.route(['/pb/waitingscreen/<int:screen>'], type='http', auth="user", website=True, sitemap=False)
    def pb_waiting_screen(self, screen=False, **kw):
        screen = request.env['pb.hms.waiting.screen'].sudo().search([('id','=',screen)])
        ResModel = request.env[screen.res_model_id.model]
        domain = [('company_id','=',screen.company_id.id)]
        if screen and screen.physician_ids and screen.pb_physician_field_id:
            domain += [(screen.pb_physician_field_id.name,'in',screen.physician_ids.ids)]
        
        if screen.pb_states_to_include and screen.pb_state_field_id:
            domain += [(screen.pb_state_field_id.name, 'in', eval(screen.pb_states_to_include))]
        limit = screen.pb_number_of_records or 5
        records = ResModel.sudo().search(domain, order="id asc", limit=limit)
        return request.render("pb_hms_next_patient_screen.next_patient_view",{'pb_ws': screen, 'records': records, 'ResModel': ResModel})

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: