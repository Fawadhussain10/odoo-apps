"""Routes of the Connect LinkedIn dialog (polling only: works behind proxies
that do not pass websockets, e.g. Cloudflare). Request bodies are never logged:
what the user types only passes through to the sign-in browser."""
import time

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.linkedin_sales_automation.engine.login_input import InputError, li_at_cookies
from odoo.addons.linkedin_sales_automation.models.li_login import read_session_zip


class LiSalesLoginController(http.Controller):

    def _profile(self, profile_id):
        profile = request.env['li.profile'].browse(int(profile_id)).exists()
        if not profile:
            raise AccessError('Unknown LinkedIn profile')
        profile.check_access('read')
        return profile

    def _error(self, exc):
        return {'error': exc.args[0] if exc.args else str(exc)}

    @http.route('/li_sales/connect/<int:profile_id>/start', type='json', auth='user')
    def start(self, profile_id, headless=None):
        try:
            profile = self._profile(profile_id)
            return {'token': profile._login_start('login', headless=headless), **profile._login_view()}
        except (UserError, AccessError) as exc:
            return self._error(exc)

    @http.route('/li_sales/connect/<int:profile_id>/cookie', type='json', auth='user')
    def cookie(self, profile_id, li_at=None):
        try:
            profile = self._profile(profile_id)
            cookies = li_at_cookies(li_at, time.time())
            return {'token': profile._login_start('cookies', cookies=cookies), **profile._login_view()}
        except InputError as exc:
            return {'error': str(exc)}
        except (UserError, AccessError) as exc:
            return self._error(exc)

    @http.route('/li_sales/connect/<int:profile_id>/import', type='http', auth='user', methods=['POST'])
    def import_session(self, profile_id, session_file=None, **_kw):
        try:
            profile = self._profile(profile_id)
            data = session_file.read() if session_file else b''
            cookies = read_session_zip(data)
            result = {'token': profile._login_start('cookies', cookies=cookies), **profile._login_view()}
        except (UserError, AccessError) as exc:
            result = self._error(exc)
        return request.make_json_response(result)

    @http.route('/li_sales/connect/<int:profile_id>/state', type='json', auth='user')
    def state(self, profile_id, token=None):
        try:
            return self._profile(profile_id)._login_poll(token)
        except (UserError, AccessError) as exc:
            return self._error(exc)

    @http.route('/li_sales/connect/<int:profile_id>/frame', type='http', auth='user', methods=['GET'])
    def frame(self, profile_id, after=-1, **_kw):
        token = request.httprequest.headers.get('X-Login-Token')
        try:
            data, seq = self._profile(profile_id)._login_frame(token, int(after))
        except (UserError, AccessError, ValueError):
            return request.make_response('', status=403)
        if data is None:
            return request.make_response('', status=204, headers=[('X-Frame-Seq', str(seq))])
        return request.make_response(data, headers=[('Content-Type', 'image/jpeg'), ('Cache-Control', 'no-store'),
                                                    ('X-Frame-Seq', str(seq))])

    @http.route('/li_sales/connect/<int:profile_id>/input', type='json', auth='user')
    def input(self, profile_id, token=None, events=None):
        try:
            return self._profile(profile_id)._login_input(token, events or [])
        except (UserError, AccessError) as exc:
            return self._error(exc)

    @http.route('/li_sales/connect/<int:profile_id>/cancel', type='json', auth='user')
    def cancel(self, profile_id, token=None):
        try:
            return self._profile(profile_id)._login_cancel(token)
        except (UserError, AccessError) as exc:
            return self._error(exc)
