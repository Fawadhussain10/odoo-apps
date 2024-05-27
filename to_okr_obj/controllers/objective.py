from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request
from odoo import http
from datetime import date, datetime
import base64
from dateutil.relativedelta import relativedelta
import pytz


class OkrObjective(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        rec = super(OkrObjective, self)._prepare_home_portal_values(counters)
        rec['okr_objective'] = http.request.env['okr.objective'].sudo().search_count([])
        if rec['okr_objective'] == 0:
            rec['okr_objective'] = 'No Record Found'
        return rec

    @http.route(['/my/okr/obj/list'], type='http',
                auth='user', website=True, )
    def okr_objective_list_view(self, **kw):
        i = request.env['okr.objective'].sudo().search([])
        rate_mapping = []
        result_mapping = []
        for rec in i:
            rate_mapping.append(rec.fields_get(allfields=['rate'])['rate']['selection'])
            result_mapping.append(rec.fields_get(allfields=['result'])['result']['selection'])

        co = request.env['okr.comp'].sudo().search([])
        rate_mapping1 = []
        result_mapping1 = []
        for res in co:
            rate_mapping1.append(res.fields_get(allfields=['rate1'])['rate1']['selection'])
            result_mapping1.append(res.fields_get(allfields=['result1'])['result1']['selection'])
        vals = {'z': i, 'page_name': 'okr_list_view', 'rate': rate_mapping, 'result': result_mapping, 'x': co,
                'rate1': rate_mapping1, 'result1': result_mapping1, }
        return request.render('to_okr_obj.okr_obj_list_view', vals)

    @http.route(['/my/okr/obj/create'], type='http', auth='user', website=True)
    def okr_objective_create_view(self, **kw):

        vals = {'page_name': 'okr_createee_view'}
        return http.request.render('to_okr_obj.abd_create', vals)

    @http.route(['/my/okr/obj/create/rec'], type='http', auth='user', website=True,
                methods=['POST'], )
    def okr_objective_write_view(self, **kw):

        new_format = "%Y-%m-%d"

        dodo = kw.get('dodate1')
        name = kw.get('namee')
        bench = kw.get('benchh')
        note1 = kw.get('note1')
        attachment = kw.get('attach')

        if kw.get('dodate1'):
            dodo = datetime.strptime(dodo, "%Y-%m-%d")
            dodo = dodo.astimezone(pytz.timezone('Asia/Karachi'))
            dodo = dodo.strftime(new_format)

        if kw.get('rate') == '1':
            ra = 'one'
            pro = 25
            ress = 'fail'
        elif kw.get('rate') == '2':
            ra = 'two'
            pro = 50
            ress = 'fail'
        elif kw.get('rate') == '3':
            ra = 'three'
            pro = 75
            ress = 'pas'
        else:
            ra = 'four'
            pro = 100
            ress = 'pas'

        if kw.get('quarters') in ['q1', 'q2', 'q3']:
            val = {
                'date': dodo,
                'name': name,
                'bench': bench,
                'rate': ra,
                'note': note1,
                'result': ress,
                'percentage': pro,
                'attach': base64.b64encode(attachment.read()),
            }
            http.request.env['okr.objective'].sudo().sudo().create(val)

        if kw.get('quarters') in ['q4']:
            vals = {
                'date1': dodo,
                'name': name,
                'bench1': bench,
                'rate1': ra,
                'note1': note1,
                'result1': ress,
                'percentage1': pro,
                'attach1': base64.b64encode(attachment.read()),
            }
            http.request.env['okr.comp'].sudo().sudo().create(vals)

        return request.redirect('/my/okr/obj/list')
