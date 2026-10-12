"""Private link to a service's portfolio file, for prospects (no Odoo login).

/li_sales/portfolio/<token>: the token is random and belongs to one service's
file; uploading a new file or removing it ends the old link. Anything else: 404.
"""
import base64

from odoo import http
from odoo.http import request

# Shown in the browser: only these, and only when the file really is one (its first bytes).
# Everything else is a download: never a page or a drawing that could run script on this site.
INLINE_TYPES = {
    'pdf': ('application/pdf', lambda d: d[:5] == b'%PDF-'),
    'png': ('image/png', lambda d: d[:8] == b'\x89PNG\r\n\x1a\n'),
    'jpg': ('image/jpeg', lambda d: d[:3] == b'\xff\xd8\xff'),
    'jpeg': ('image/jpeg', lambda d: d[:3] == b'\xff\xd8\xff'),
    'gif': ('image/gif', lambda d: d[:6] in (b'GIF87a', b'GIF89a')),
    'webp': ('image/webp', lambda d: d[:4] == b'RIFF' and d[8:12] == b'WEBP'),
}


def portfolio_headers(name, data):
    """(content type, disposition) for a portfolio file."""
    extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    mimetype, is_real = INLINE_TYPES.get(extension, (None, None))
    if mimetype and is_real(data):
        return mimetype, 'inline'
    return 'application/octet-stream', 'attachment'


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
        name = ''.join(c for c in (service.portfolio_filename or 'portfolio.pdf') if c.isprintable()
                       and c not in '"\\/').strip() or 'portfolio'
        mimetype, disposition = portfolio_headers(name, data)
        return request.make_response(data, headers=[
            ('Content-Type', mimetype), ('Content-Length', str(len(data))),
            ('Content-Disposition', '%s; filename="%s"' % (disposition, name)),
            ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
            ('X-Robots-Tag', 'noindex, nofollow')])
