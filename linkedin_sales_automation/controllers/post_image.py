"""Signed link to a post image for Claude in Chrome (no Odoo login).

/li_sales/post_image/<post id>/<token>: the token is random, valid 6 hours and
only for that post's image (see li.post._signed_image_url). Anything else: 404.
"""
import base64

from odoo import http
from odoo.http import request


class LiPostImage(http.Controller):

    @http.route('/li_sales/post_image/<int:post_id>/<string:token>', type='http', auth='none', methods=['GET'],
                csrf=False, save_session=False)
    def post_image(self, post_id, token, **kwargs):
        post = request.env['li.post'].sudo().browse(post_id).exists()
        image = post._image_for_token(token) if post else False
        if not image:
            return request.not_found()
        data = base64.b64decode(image)
        mimetype = 'image/png' if data[:4] == b'\x89PNG' else 'image/gif' if data[:3] == b'GIF' else (
            'image/webp' if data[8:12] == b'WEBP' else 'image/jpeg')
        extension = mimetype.split('/')[1].replace('jpeg', 'jpg')
        return request.make_response(data, headers=[
            ('Content-Type', mimetype), ('Content-Length', str(len(data))),
            ('Content-Disposition', 'attachment; filename="linkedin-post-%s.%s"' % (post_id, extension)),
            ('Cache-Control', 'private, no-store'), ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer')])
