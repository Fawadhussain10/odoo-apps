"""Connect LinkedIn from inside Odoo (Stage 2).

The profile owner (or a LinkedIn Sales Administrator) opens "Connect LinkedIn"
and picks one of three ways; each runs engine/login_helper.py detached, with the
engine stopped, and ends with the engine's own session files in the account's
folder:

* Log in here    – the engine's login browser streamed into an Odoo dialog.
* Import session – the cookies.json of a session made with `--login` on the
                   user's computer, uploaded as a zip.
* Paste cookie   – the li_at cookie value.

Then Odoo starts the engine and reads the own profile to confirm the session.
Every login is bound to the user who started it, a single-use token (only its
hash is stored) and a 10-minute limit. Nothing typed is logged or stored.
"""
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.translate import LazyTranslate

from .li_engine_manager import ENGINE_LOCK_NAMESPACE, _free_port, _module_file, _pid_alive, _pid_cmdline, is_odoo_sh
from .li_engine_parse import error_kind
from .li_mcp_client import McpClientError

_logger = logging.getLogger(__name__)

LOGIN_MINUTES = 10
LOGIN_LOCK_NAMESPACE = ENGINE_LOCK_NAMESPACE + 1
LOGIN_STATES = [
    ('none', 'Not started'),
    ('starting', 'Starting'),
    ('waiting', 'Waiting for login'),
    ('two_step', '2-step check'),
    ('captcha', 'Security check'),
    ('validating', 'Checking the session'),
    ('connected', 'Connected'),
    ('failed', 'Failed'),
]
STATE_MESSAGES = {
    'starting': 'Opening the LinkedIn sign-in page…',
    'waiting': 'Sign in to LinkedIn in the window below.',
    'two_step': 'LinkedIn asks for a 2-step check: approve the sign-in in the LinkedIn app, or enter the code '
                'LinkedIn sent you.',
    'captcha': 'LinkedIn shows a security check: solve it in the window below.',
    'validating': 'LinkedIn is checking the session…',
    'connected': 'Connected.',
}

# Session zip: what may be inside (a zip of the engine's folder ~/.linkedin-mcp,
# or of its two session files). Only cookies.json is used.
ZIP_MAX_BYTES = 25 * 1024 * 1024          # compressed upload
ZIP_MAX_UNCOMPRESSED = 600 * 1024 * 1024
ZIP_MAX_ENTRIES = 20000
COOKIES_MAX_BYTES = 2 * 1024 * 1024
ZIP_ALLOWED_TOP = {'cookies.json', 'source-state.json', 'profile', 'runtime-profiles', 'browser-install.json',
                   'profile-claim.json', 'profile-claim.lock', 'profile.lock', 'patchright-browsers',
                   'trace-runs', '.linkedin-mcp'}
_lt = LazyTranslate(__name__, default_lang='en_US')   # no request in tests: English


class SessionZipError(UserError):
    pass


def read_session_zip(data):
    """Validate an uploaded session zip and return its cookies (a list).

    Refused: oversize, absolute paths, "..", symbolic links and other special
    files, names outside the engine's session layout, a missing or invalid
    cookies.json, or one without a LinkedIn li_at cookie. Nothing is written to
    disk: only cookies.json is read, in memory.
    """
    if not data or len(data) > ZIP_MAX_BYTES:
        raise SessionZipError(str(_lt('The file is empty or larger than %s MB.', ZIP_MAX_BYTES // (1024 * 1024))))
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise SessionZipError(str(_lt('This is not a zip file.'))) from exc
    if len(entries) > ZIP_MAX_ENTRIES:
        raise SessionZipError(str(_lt('The zip has too many files.')))
    total, cookies_entry = 0, None
    for info in entries:
        name = info.filename
        parts = [p for p in name.replace('\\', '/').split('/') if p not in ('', '.')]
        if name.startswith(('/', '\\')) or (len(name) > 1 and name[1] == ':') or '..' in parts:
            raise SessionZipError(str(_lt('Unsafe path in the zip: %s', name)))
        file_type = stat.S_IFMT(info.external_attr >> 16)   # 0 when the zip tool recorded no type
        if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
            raise SessionZipError(str(_lt('The zip contains a link or a special file: %s', name)))
        if parts and parts[0] == '.linkedin-mcp':
            parts = parts[1:]
        if parts and parts[0] not in ZIP_ALLOWED_TOP:
            raise SessionZipError(str(_lt('Unexpected file in the zip: %s', name)))
        total += info.file_size
        if total > ZIP_MAX_UNCOMPRESSED:
            raise SessionZipError(str(_lt('The zip is too large once unpacked.')))
        if parts == ['cookies.json'] and not info.is_dir():
            if cookies_entry is not None:
                raise SessionZipError(str(_lt('The zip contains cookies.json twice.')))
            cookies_entry = info
    if cookies_entry is None:
        raise SessionZipError(str(_lt('cookies.json is missing: zip the folder made by the engine login (see the steps).')))
    if cookies_entry.file_size > COOKIES_MAX_BYTES:
        raise SessionZipError(str(_lt('cookies.json is too large.')))
    try:
        cookies = json.loads(archive.read(cookies_entry))
    except (ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        raise SessionZipError(str(_lt('cookies.json is not valid.'))) from exc
    if not isinstance(cookies, list) or not all(isinstance(c, dict) and c.get('name') and 'value' in c
                                                 for c in cookies):
        raise SessionZipError(str(_lt('cookies.json is not a cookie list.')))
    if not any(c.get('name') == 'li_at' and 'linkedin.com' in (c.get('domain') or '') for c in cookies):
        raise SessionZipError(str(_lt('cookies.json holds no LinkedIn session (li_at). Log in again on your computer.')))
    return cookies


def _hash_token(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


class LiProfileLogin(models.Model):
    _inherit = 'li.profile'

    login_state = fields.Selection(LOGIN_STATES, default='none', required=True, readonly=True, copy=False)
    login_message = fields.Char(readonly=True, copy=False)
    login_user_id = fields.Many2one('res.users', readonly=True, copy=False)
    login_expires = fields.Datetime(readonly=True, copy=False)
    login_token_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    login_pid = fields.Integer(readonly=True, copy=False, groups='base.group_system')
    login_port = fields.Integer(readonly=True, copy=False, groups='base.group_system')
    login_secret = fields.Char(readonly=True, copy=False, groups='base.group_system')
    connected_date = fields.Datetime(readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Rights
    # ------------------------------------------------------------------
    def _check_connect_rights(self):
        self.ensure_one()
        user = self.env.user
        if self.owner_id != user and not user.has_group('linkedin_sales_automation.group_li_admin'):
            raise AccessError(_('Only the owner of this LinkedIn profile or a LinkedIn Sales Administrator can '
                                'connect or disconnect it.'))
        if self.execution_mode != 'engine' or is_odoo_sh():
            raise UserError(_('This profile uses Claude in Chrome: LinkedIn is signed in to in your own Chrome.'))

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_open_connect(self):
        """Open the Connect LinkedIn dialog (nothing starts yet)."""
        self.ensure_one()
        self._check_connect_rights()
        return {
            'type': 'ir.actions.client',
            'tag': 'li_linkedin_connect',
            'name': _('Connect LinkedIn: %s', self.name),
            'target': 'new',
            'params': {'profile_id': self.id, 'profile_name': self.name,
                       'xvfb': self.env['li.engine.manager']._health()['xvfb']},
        }

    def action_disconnect(self):
        """Stop the engine, delete the session folder: Not connected."""
        for profile in self:
            profile._check_connect_rights()
            sudo = profile.sudo()
            sudo._login_kill()
            sudo.engine_wanted = False
            sudo._engine_kill()
            shutil.rmtree(sudo._session_dir(), ignore_errors=True)
            sudo.write({'connection_state': 'not_connected', 'login_state': 'none', 'login_message': False,
                        'connected_date': False})
            sudo.message_post(body=_('LinkedIn disconnected by %s: session deleted from this server.',
                                     self.env.user.name), author_id=self.env.user.partner_id.id,
                              subtype_xmlid='mail.mt_note')
        return True

    # ------------------------------------------------------------------
    # Login process
    # ------------------------------------------------------------------
    def _login_helper_command(self, mode, port, headless, cookies_file=None):
        manager = self.env['li.engine.manager']
        command = [str(manager._engine_python()), _module_file('engine', 'login_helper.py'), '--mode', mode,
                   '--port', str(port), '--user-data-dir', str(self._profile_dir()),
                   '--timeout', str(LOGIN_MINUTES * 60)]
        if cookies_file:
            command += ['--cookies', str(cookies_file)]
        if headless:
            return command + ['--headless']
        return ['xvfb-run', '-a', '-s', '-screen 0 1280x900x24'] + command

    def _login_start(self, mode, headless=None, cookies=None):
        """Start the helper detached. Returns the single-use token (plain)."""
        self.ensure_one()
        self._check_connect_rights()
        profile = self.sudo()
        health = self.env['li.engine.manager']._check_ready()
        if headless is None or not health['xvfb']:
            headless = not health['xvfb']
        profile._login_kill()
        profile.engine_wanted = False          # the watchdog must not restart it during the login
        profile._engine_kill()
        session = profile._session_dir()
        cookies_file = None
        if mode == 'cookies':
            # outside the account folder: the engine only claims a folder that
            # holds nothing but its own files
            manager = self.env['li.engine.manager']
            incoming = manager._secure_dir(manager._root() / 'incoming')
            cookies_file = incoming / ('%s-%s-%s.json' % (self.env.cr.dbname, profile.id, secrets.token_hex(8)))
            fd = os.open(cookies_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump(cookies, handle)
        port = _free_port()
        secret = '/login-' + secrets.token_hex(16)
        token = secrets.token_urlsafe(32)
        env = dict(profile._engine_env(), LI_LOGIN_SECRET=secret)
        launch = [sys.executable, _module_file('engine', 'launch.py'), '--cwd', str(session),
                  '--log', str(profile._log_path()), '--'] + profile._login_helper_command(
            mode, port, headless, cookies_file)
        try:
            out = subprocess.run(launch, capture_output=True, text=True, check=True, timeout=30, env=env)
            pid = int(out.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            if cookies_file:
                cookies_file.unlink(missing_ok=True)
            raise UserError(_('The LinkedIn sign-in could not be started: %s', exc)) from exc
        profile.write({
            'login_state': 'validating' if mode == 'cookies' else 'starting',
            'login_message': _(STATE_MESSAGES['validating' if mode == 'cookies' else 'starting']),
            'login_user_id': self.env.user.id, 'login_expires': fields.Datetime.now() + timedelta(minutes=LOGIN_MINUTES),
            'login_token_hash': _hash_token(token), 'login_pid': pid, 'login_port': port, 'login_secret': secret,
        })
        return token

    def _login_check_token(self, token):
        """The request comes from the user who started this login, with its token."""
        self.ensure_one()
        profile = self.sudo()
        if not token or not profile.login_token_hash or profile.login_user_id != self.env.user \
                or not hmac.compare_digest(profile.login_token_hash, _hash_token(token)):
            raise AccessError(_('This LinkedIn sign-in is not yours or has ended.'))
        return profile

    def _login_is_mine(self):
        profile = self.sudo()
        return bool(profile.login_pid) and _pid_alive(profile.login_pid) \
            and str(self._profile_dir()) in _pid_cmdline(profile.login_pid)

    def _login_kill(self):
        profile = self.sudo()
        pid = profile.login_pid
        if pid and profile._login_is_mine():
            try:
                os.killpg(pid, 15)
                for _i in range(30):
                    if not _pid_alive(pid):
                        break
                    time.sleep(0.2)
                if _pid_alive(pid):
                    os.killpg(pid, 9)
            except (ProcessLookupError, PermissionError):
                pass
        manager = self.env['li.engine.manager']
        for leftover in (manager._root() / 'incoming').glob('%s-%s-*.json' % (self.env.cr.dbname, profile.id)):
            leftover.unlink(missing_ok=True)
        profile.write({'login_pid': 0, 'login_port': 0, 'login_secret': False})

    def _login_end(self, state, message):
        """The token stays valid for reading this final state only: frames and
        input are refused once the sign-in is over, and a new sign-in gets a new
        token."""
        profile = self.sudo()
        profile._login_kill()
        profile.write({'login_state': state, 'login_message': message})

    def _helper(self, method, path, **kwargs):
        profile = self.sudo()
        url = 'http://127.0.0.1:%d%s%s' % (profile.login_port, profile.login_secret, path)
        return requests.request(method, url, timeout=kwargs.pop('timeout', 10), **kwargs)

    def _login_poll(self, token):
        """Current state for the dialog; finishes the connection once LinkedIn
        accepted the session."""
        profile = self._login_check_token(token)
        if profile.login_state in ('connected', 'failed'):
            return profile._login_view()
        if profile.login_expires and profile.login_expires < fields.Datetime.now():
            profile._login_end('failed', _('The 10 minutes are over. Start again.'))
            return profile._login_view()
        try:
            state = profile._helper('GET', '/state').json()
        except (requests.RequestException, ValueError):
            if not profile._login_is_mine():
                profile._login_end('failed', _('The sign-in browser stopped. See the engine log.'))
            return profile._login_view()
        helper_state = state.get('state')
        if helper_state == 'connected':
            profile._login_finish()
        elif helper_state == 'failed':
            profile._login_end('failed', state.get('message') or _('The sign-in failed.'))
        elif helper_state in dict(LOGIN_STATES):
            profile.write({'login_state': helper_state,
                           'login_message': _(STATE_MESSAGES.get(helper_state, '')) or state.get('message')})
        view = profile._login_view()
        view['seq'] = state.get('seq', 0)
        return view

    def _login_view(self):
        profile = self.sudo()
        return {'state': profile.login_state, 'message': profile.login_message or '',
                'display_name': profile.my_display_name or '', 'connection_state': profile.connection_state}

    def _login_frame(self, token, after):
        profile = self._login_check_token(token)
        if profile.login_state in ('connected', 'failed') or not profile.login_port:
            return None, 0
        try:
            response = profile._helper('GET', '/frame', params={'after': after})
        except requests.RequestException:
            return None, 0
        if response.status_code != 200:
            return None, int(response.headers.get('X-Frame-Seq', after or 0))
        return response.content, int(response.headers.get('X-Frame-Seq', 0))

    def _login_input(self, token, events):
        profile = self._login_check_token(token)
        if profile.login_state in ('connected', 'failed', 'validating'):
            return {'ok': False}
        try:
            response = profile._helper('POST', '/input', json={'events': events})
        except requests.RequestException:
            return {'ok': False}
        return {'ok': response.status_code == 200}

    def _login_cancel(self, token):
        profile = self._login_check_token(token)
        try:
            profile._helper('POST', '/cancel', timeout=3)
        except requests.RequestException:
            pass
        profile._login_end('failed', _('Cancelled.'))
        return profile._login_view()

    def _login_finish(self):
        """LinkedIn accepted the session: start the engine, read the own
        profile, show Connected. One worker at a time."""
        profile = self.sudo()
        self.env.cr.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', (LOGIN_LOCK_NAMESPACE, profile.id))
        if not self.env.cr.fetchone()[0]:
            return
        profile._login_kill()
        profile.write({'login_state': 'validating', 'login_message': _('Starting the engine…')})
        try:
            profile._engine_start()
            for _i in range(40):
                if profile.engine_state == 'running':
                    break
                time.sleep(0.5)
                profile._engine_refresh()
            result = profile._engine_call('get_my_profile', {}, timeout=75)
            if result.get('isError'):
                raise UserError(profile._tool_text(result)[:300] or _('LinkedIn did not return the profile.'))
            name = profile._own_profile_name(result)
        except (UserError, McpClientError) as exc:
            profile.engine_wanted = False
            profile._engine_kill()
            shutil.rmtree(profile._session_dir(), ignore_errors=True)
            profile.write({'connection_state': 'not_connected'})
            profile._login_end('failed', _('The session could not be confirmed: %s', exc))
            return
        values = {'connection_state': 'connected', 'connected_date': fields.Datetime.now()}
        if name:
            values['my_display_name'] = name
        profile.write(values)
        profile._apply_interface_language(result)
        profile._login_end('connected', _('Connected as %s.', name) if name else _('Connected.'))
        profile.message_post(body=_('LinkedIn connected%s by %s.', (' (%s)' % name) if name else '',
                                    self.env.user.name), subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # Engine results
    # ------------------------------------------------------------------
    @api.model
    def _tool_text(self, result):
        return ' '.join(c.get('text', '') for c in (result or {}).get('content', []) if c.get('type') == 'text')

    @api.model
    def _own_profile_name(self, result):
        """The name on the own profile: first line of its main section."""
        data = result.get('structuredContent')
        if not isinstance(data, dict):
            try:
                data = json.loads(self._tool_text(result))
            except ValueError:
                data = None
        text = ''
        if isinstance(data, dict):
            sections = data.get('sections') or {}
            text = sections.get('main_profile') or next(iter(sections.values()), '') if sections else ''
        text = text or self._tool_text(result)
        for line in (text or '').splitlines():
            line = line.strip()
            if line and len(line) <= 80:
                return line
        return False

    def _engine_call(self, tool, arguments=None, timeout=200):
        """Engine calls notice an expired LinkedIn session (6.x): the profile
        becomes Reconnect needed, its agents pause, the owner gets an activity."""
        result = super()._engine_call(tool, arguments, timeout)
        if result.get('isError') and error_kind(self._tool_text(result))[0] == 'session':
            self.sudo()._set_reconnect_needed(self._tool_text(result)[:300])
        return result

    # ------------------------------------------------------------------
    @api.model
    def _cron_engine_watchdog(self):
        """Also ends sign-ins that ran past their time."""
        for profile in self.sudo().search([('login_state', 'in', ('starting', 'waiting', 'two_step', 'captcha',
                                                                   'validating')),
                                           ('login_expires', '<', fields.Datetime.now())]):
            profile._login_end('failed', _('The 10 minutes are over. Start again.'))
        return super()._cron_engine_watchdog()
