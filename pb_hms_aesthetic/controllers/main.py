# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo.exceptions import AccessError, MissingError
from odoo.addons.website.controllers.form import WebsiteForm
from odoo.exceptions import ValidationError
import json


class HMSPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        AestheticWish = request.env['pb.aesthetic.patient.wish']
        if 'aestheticwish_count' in counters:
            values['aestheticwish_count'] = AestheticWish.search_count([]) \
                if AestheticWish.check_access_rights('read', raise_exception=False) else 0
        return values

    @http.route(['/my/aestheticwish', '/my/aestheticwish/page/<int:page>'], type='http', auth="user", website=True, sitemap=False)
    def my_aestheticwishes(self, page=1, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        AestheticWish = request.env['pb.aesthetic.patient.wish']
        if not sortby:
            sortby = 'date'

        sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc'},
            'name': {'label': _('Name'), 'order': 'name'},
        }

        order = sortings.get(sortby, sortings['date'])['order']
        count = AestheticWish.search_count([('state','!=','draft')])

        pager = portal_pager(
            url="/my/aestheticwish",
            url_args={},
            total=count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        aestheticwishs = AestheticWish.search([],
            order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'sortings': sortings,
            'sortby': sortby,
            'aestheticwishs': aestheticwishs,
            'page_name': 'aestheticwish',
            'default_url': '/my/aestheticwish',
            'searchbar_sortings': sortings,
            'pager': pager
        })
        return request.render("pb_hms_aesthetic.my_aestheticwishes", values)

    @http.route(['/my/aestheticwish/<int:aestheticwish_id>'], type='http', auth="user", website=True, sitemap=False)
    def my_aestheticwish(self, aestheticwish_id=None, access_token=None, **kw):
        try:
            record_sudo = self._document_check_access('pb.aesthetic.patient.wish', aestheticwish_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return request.render("pb_hms_aesthetic.my_aestheticwish", {'aestheticwish': record_sudo})

    @http.route(['/my/aestheticwish/create'], type='http', auth="user", website=True, sitemap=False)
    def my_aestheticwish_create(self, **kw):
        values = {
            'patient_id': request.env.user.pb_patient_id,
            'body_treatment_product_ids': request.env['product.product'].sudo().search([('is_body_treatment','=',True)]),
            'body_nutrition_product_ids': request.env['product.product'].sudo().search([('is_body_nutrition','=',True)]),
            'body_upkeep_product_ids': request.env['product.product'].sudo().search([('is_body_upkeep','=',True)]),
            'facial_treatment_product_ids': request.env['product.product'].sudo().search([('is_facial_treatment','=',True)]),
            'facial_nutrition_product_ids': request.env['product.product'].sudo().search([('is_facial_nutrition','=',True)]),
            'facial_upkeep_product_ids': request.env['product.product'].sudo().search([('is_facial_upkeep','=',True)]),
        }
        return request.render("pb_hms_aesthetic.my_aestheticwish_create", values)

    @http.route(['/my/aesthetic/history'], type='http', auth="user", website=True, sitemap=False)
    def aesthetic_history(self, **kw):
        patient_id = request.env.user.pb_patient_id
        values = {
            'patient_id': patient_id,
            'record': patient_id,
        }
        return request.render("pb_hms_aesthetic.my_aesthetic_history", values)

    @http.route(['/my/aesthetic/history/sign'], type='http', auth="user", website=True, sitemap=False)
    def aesthetic_history_sign(self, report_type=None, message=False, download=False, **kw):
        patient_id = request.env.user.pb_patient_id
        try:
            order_sudo = self._document_check_access('hms.patient', patient_id.id, access_token=False)
        except:
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
           return self._show_report(model=order_sudo, report_type=report_type,report_ref='pb_hms_aesthetic.action_aesthetic_hisotry_report',download=download)
        
        values = {
            'patient': patient_id,
            'record': patient_id,
            'message': message,
        }
        return request.render("pb_hms_aesthetic.my_aesthetic_history_sign", values)

    @http.route(['/my/aesthetic/<int:patient_id>/accept'], type='jsonrpc', auth="public", website=True, sitemap=False)
    def portal_patient_accept(self, patient_id, access_token=None, name=None, signature=None):
        # get from query string if not on json param
        access_token = access_token or request.httprequest.args.get('access_token')
        
        partner = request.env.user.partner_id.commercial_partner_id
        order_sudo = request.env['hms.patient'].sudo().search([('partner_id','=', partner.id)], limit=1)

        if not order_sudo.ach_has_to_be_signed:
            return {'error': _('The order is not in a state requiring customer signature.')}
        if not signature:
            return {'error': _('Signature is missing.')}

        try:
            order_sudo.write({
                'ach_signed_on': fields.Datetime.now(),
                'ach_signature': signature,
                'ach_has_to_be_signed': False,
            })
        except (TypeError, binascii.Error) as e:
            return {'error': _('Invalid signature data.')}

        # _message_post_helper(
        #     'hms.patient', order_sudo.id, _('Declaration signed by %s') % (name,),
        #     **({'token': access_token} if access_token else {}))

        return {
            'force_refresh': True,
            'redirect_url': '/my/aesthetic/history/sign?message=sign_ok',
        }

    @http.route(['/my/aesthetic/phototype'], type='http', auth="user", website=True, sitemap=False)
    def aesthetic_phototype_skin(self, **kw):
        patient_id = request.env.user.pb_patient_id
        values = {
            'patient_id': patient_id,
            'record': patient_id,
        }
        return request.render("pb_hms_aesthetic.my_aesthetic_phototype", values)

    @http.route(['/my/aesthetic/phototype/view'], type='http', auth="user", website=True, sitemap=False)
    def aesthetic_phototype_skin_view(self, report_type=None, message=False, download=False, **kw):
        patient_id = request.env.user.pb_patient_id
        try:
            order_sudo = self._document_check_access('hms.patient', patient_id.id, access_token=False)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
           return self._show_report(model=order_sudo, report_type=report_type,report_ref='pb_hms_aesthetic.action_aesthetic_phototype_report',download=download)
        
        values = {
            'patient': patient_id,
            'record': patient_id,
            'message': message,
        }
        return request.render("pb_hms_aesthetic.my_aesthetic_phototype_view", values)


class PbWebsiteForm(WebsiteForm):

    @http.route()
    def website_form(self, model_name, **kwargs):
        if kwargs.get('edit_record'):
            record_id = kwargs.get('record_id')
            kwargs.pop('edit_record')
            kwargs.pop('record_id')

            model_record = request.env['ir.model'].sudo().search([('model', '=', model_name), ('website_form_access', '=', True)])
            if not model_record:
                return json.dumps(False)

            try:
                data = self.extract_data(model_record, request.params)
            # If we encounter an issue while extracting data
            except ValidationError as e:
                # I couldn't find a cleaner way to pass data to an exception
                return json.dumps({'error_fields' : e.args[0]})
            
            record = request.env[model_name].sudo().search([('id','=',record_id)])
            record.sudo().write(data['record'])
            request.session['form_builder_model_model'] = model_record.model
            request.session['form_builder_model'] = model_record.name
            request.session['form_builder_id'] = record_id
            return json.dumps({'id': record_id})
        else:
            return super(PbWebsiteForm, self).website_form(model_name, **kwargs)