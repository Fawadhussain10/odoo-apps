# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import AccessError, MissingError
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo import fields as odoo_fields, http, tools, _, SUPERUSER_ID
import base64


class HMSPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        ConsentForm = request.env['pb.consent.form']
        if 'consent_form_count' in counters:
            values['consent_form_count'] = ConsentForm.search_count([('state','!=','draft')]) \
                if ConsentForm.check_access_rights('read', raise_exception=False) else 0
        return values

    @http.route(['/my/consentforms', '/my/consentforms/page/<int:page>'], type='http', auth="user", website=True, sitemap=False)
    def my_consent_forms(self, page=1, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        ConsentForm = request.env['pb.consent.form']
        if not sortby:
            sortby = 'date'

        sortings = {
            'date': {'label': _('Newest'), 'order': 'date desc'},
            'name': {'label': _('Name'), 'order': 'name'},
        }

        order = sortings.get(sortby, sortings['date'])['order']
        count = ConsentForm.search_count([('state','!=','draft')])
 
        pager = portal_pager(
            url="/my/consentforms",
            url_args={},
            total=count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        consent_forms = ConsentForm.search([('state','!=','draft')],
            order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'sortings': sortings,
            'sortby': sortby,
            'consent_forms': consent_forms,
            'page_name': 'consent_form',
            'default_url': '/my/consentforms',
            'searchbar_sortings': sortings,
            'pager': pager
        })
        return request.render("pb_consent_form.my_consent_forms", values)

    @http.route(['/my/consentforms/<int:consent_form_id>'], type='http', auth="public", website=True, sitemap=False)
    def my_consent_form_data(self, consent_form_id=None, access_token=None, report_type=None, message=False, download=False, **kw):
        try:
            order_sudo = self._document_check_access('pb.consent.form', consent_form_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
           return self._show_report(model=order_sudo, report_type=report_type,report_ref='pb_consent_form.report_pb_consent_form',download=download)

        values = {
            'consent_form': order_sudo,
            'message': message,
            'action': order_sudo._get_portal_return_action(),
        }
        return request.render("pb_consent_form.my_consent_form", values)

    @http.route(['/my/consentform/<int:consent_form_id>/sign'], type='jsonrpc', auth="public", website=True, sitemap=False)
    def pb_portal_document_sign(self, consent_form_id, access_token=None, name=None, signature=None):
        # get from query string if not on json param
        access_token = access_token or request.httprequest.args.get('access_token')
        try:
            order_sudo = self._document_check_access('pb.consent.form', consent_form_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not signature:
            return {'error': _('Signature is missing.')}

        try:
            order_sudo.write({
                'pb_signed_on': fields.Datetime.now(),
                'pb_signature': signature,
                'pb_has_to_be_signed': False,
            })
            order_sudo.action_signed()
        except (TypeError, binascii.Error) as e:
            return {'error': _('Invalid signature data.')}

        order_sudo.message_post(body=_('Declaration signed by %s') % (name,))

        return {
            'force_refresh': True,
            'redirect_url': '/my/consentforms/%s?message=sign_ok&access_token=%s' %(order_sudo.id, access_token),
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: