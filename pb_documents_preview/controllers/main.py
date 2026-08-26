# -*- coding: utf-8 -*-

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.translate import _


class PbImageZoom(http.Controller):

    @http.route(['/my/pb/image/<string:model>/<int:record>'], type='http', auth="user", website=True, sitemap=False)
    def pb_image_preview(self, model=False, record=False, **kwargs):
        # model/record come straight from the URL; this is shared by staff and
        # portal users previewing attachments across many different HMS
        # models, so there's no single "must own this record" rule that fits
        # everyone. The real gate is Odoo's own ACL/record rules, which apply
        # automatically here because we use the caller's own (non-sudo) env -
        # this just makes a bogus model/record fail gracefully instead of a
        # raw 500 that could leak a traceback.
        if model not in request.env.registry.models:
            return request.not_found()
        try:
            record = request.env[model].browse(int(record)).exists()
        except (AccessError, ValueError):
            return request.not_found()
        attachments = request.env['ir.attachment'].search([
            ('id', 'in', record.attachment_ids.ids),
            ('mimetype', 'in', ['image/jpeg','image/jpg','image/png','image/gif']),
        ])
        return request.render("pb_documents_preview.pb_image_preview", {'attachments':attachments})

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: