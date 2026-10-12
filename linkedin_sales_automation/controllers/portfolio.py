"""Private link to a service's portfolio file, for prospects (no Odoo login).

/li_sales/portfolio/<token>: the token is random and belongs to one service's
file; uploading a new file or removing it ends the old link. Anything else: 404.
"""
import base64
import mimetypes

from odoo import http
from odoo.http import request


class LiPortfolio(http.Controller):

    @http.route('/li_sales/portfolio/<string:token>', type='http', auth='none', methods=['GET'], csrf=False,
                save_session=False)
    def portfolio(self, token, **kwargs):
        if not token or len(token) < 20:
            return request.not_found()
        service = request.env['li.service'].sudo().with_context(active_test=False).search(
            [('portfolio_token', '=', token)], limit=1)
        if not service or not service.portfolio_file:
            return request.not_found()
        data = base64.b64decode(service.portfolio_file)
        name = (service.portfolio_filename or 'portfolio.pdf').replace('"', '')
        mimetype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        return request.make_response(data, headers=[
            ('Content-Type', mimetype), ('Content-Length', str(len(data))),
            ('Content-Disposition', 'inline; filename="%s"' % name),
            ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
            ('X-Robots-Tag', 'noindex, nofollow')])
