# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.tools.translate import _
import base64


class PbImageEditor(http.Controller):

    @http.route(['/my/pb/image/editor/<int:record>'], type='http', auth="user", website=True, sitemap=False)
    def pb_image_editor(self, model=False, record=False, **kwargs):
        record = request.env['ir.attachment'].browse([record])
        data = {
            'pb_doc': record,
            'pb_model': kwargs.get('pb_model'),
            'pb_rec_id': kwargs.get('pb_rec_id'),
            'pb_action_id': kwargs.get('pb_action_id')
        }
        return request.render("pb_hms_body_chart.pb_image_editor", data)

    @http.route(['/my/pb/image/<int:record>'], type="http", auth="user", methods=['post'], website=True, csrf=False, sitemap=False)
    def pb_image_editor_updateimage(self, record, **kwargs):
        attachment = request.env['ir.attachment'].browse([record])
        datas = list(kwargs.keys())[0]
        image_data = datas.split("base64,")[1].replace(' ','+')
        strImage = image_data + "=" * ((4 - len(image_data) % 4) % 4)
        attachment.write({
            'datas': strImage
        })
        return request.redirect('/my/pb/image/editor/%s' % record)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: