# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import AccessError, MissingError
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo import fields as odoo_fields, http, tools, _, SUPERUSER_ID
import base64

class PBHms(http.Controller):

    @http.route(['/validate/certificatemanagement/<certificate_unique_code>'], type='http', auth="public", website=True, sitemap=False)
    def certificate_details(self, certificate_unique_code, **post):
        if certificate_unique_code:
            certificate = request.env['certificate.management'].sudo().search([('unique_code','=',certificate_unique_code)], limit=1)
            if certificate:
                return request.render("pb_hms_certification.pb_certificate_details", {'certificate': certificate})
        return request.render("pb_hms.pb_no_details")


class HMSPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        Certificate = request.env['certificate.management']
        if 'certificate_count' in counters:
            partner = request.env.user.partner_id.commercial_partner_id
            values['certificate_count'] = Certificate.search_count([('partner_id', 'child_of', partner.id)]) \
                if Certificate.check_access_rights('read', raise_exception=False) else 0
        return values

    @http.route(['/my/certificates', '/my/certificates/page/<int:page>'], type='http', auth="user", website=True, sitemap=False)
    def my_certificates(self, page=1, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        Certificate = request.env['certificate.management']

        if not sortby:
            sortby = 'date'

        sortings = {
            'date': {'label': _('Newest'), 'order': 'date desc'},
            'name': {'label': _('Name'), 'order': 'name'},
        }
        order = sortings.get(sortby, sortings['date'])['order']
        partner = request.env.user.partner_id.commercial_partner_id
        domain = [('partner_id', 'child_of', partner.id)]
        count = Certificate.search_count(domain)

        pager = portal_pager(
            url="/my/certificates",
            url_args={},
            total=count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        certificates = request.env['certificate.management'].sudo().search(domain,
            order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'sortings': sortings,
            'sortby': sortby,
            'certificates': certificates,
            'page_name': 'certificate',
            'default_url': '/my/certificates',
            'searchbar_sortings': sortings,
            'pager': pager
        })
        return request.render("pb_hms_certification.my_certificates", values)

    @http.route(['/my/certificates/<int:certificate_id>'], type='http', auth="user", website=True, sitemap=False)
    def my_certificate(self, certificate_id=None, access_token=None, **kw):
        try:
            order_sudo = self._document_check_access('certificate.management', certificate_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        return request.render("pb_hms_certification.my_certificate", {'certificate': order_sudo})

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
