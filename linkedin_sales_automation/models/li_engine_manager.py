"""The LinkedIn engine, installed and run by Odoo itself.

* "Prepare engine" (Settings) installs the open-source linkedin-mcp-server and
  its Chromium into <data dir>/linkedin_engine with engine/installer.py, run
  as a detached process; Odoo only reads its progress file.
* Each LinkedIn Profile gets its own engine process on 127.0.0.1, its own
  browser profile folder and session, started detached through
  engine/launch.py so it outlives the Odoo worker that started it. Odoo talks
  to it as an MCP client. A cron restarts engines that died.
"""
import glob
import json
import logging
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_path
from odoo.tools import config

from .li_mcp_client import McpClient, McpClientError

_logger = logging.getLogger(__name__)

ENGINE_DIR = 'linkedin_engine'
ENGINE_LOCK_NAMESPACE = 74218302        # pg advisory lock: one engine action at a time per account
START_TIMEOUT = 25                      # seconds to wait for a new engine to answer
STOP_TIMEOUT = 10
# Shared libraries the engine's Chromium links against (from the binary's
# NEEDED entries). Checked with the system library cache before the browser is
# even downloaded, so Settings can show the admin command up front.
CHROMIUM_LIBRARIES = (
    'libasound.so.2', 'libatk-1.0.so.0', 'libatk-bridge-2.0.so.0', 'libatspi.so.0', 'libcairo.so.2',
    'libcups.so.2', 'libdbus-1.so.3', 'libexpat.so.1', 'libgbm.so.1', 'libgio-2.0.so.0', 'libglib-2.0.so.0',
    'libgobject-2.0.so.0', 'libnspr4.so', 'libnss3.so', 'libnssutil3.so', 'libpango-1.0.so.0', 'libsmime3.so',
    'libudev.so.1', 'libX11.so.6', 'libxcb.so.1', 'libXcomposite.so.1', 'libXdamage.so.1', 'libXext.so.6',
    'libXfixes.so.3', 'libxkbcommon.so.0', 'libXrandr.so.2',
)
ADMIN_LIBS_COMMAND_PREPARED = 'sudo %s -m patchright install-deps chromium'
ADMIN_LIBS_COMMAND_APT = ('sudo apt-get install -y libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 '
                          'libatspi2.0-0t64 libcairo2 libcups2t64 libdbus-1-3 libexpat1 libgbm1 libglib2.0-0t64 '
                          'libnspr4 libnss3 libpango-1.0-0 libudev1 libx11-6 libxcb1 libxcomposite1 libxdamage1 '
                          'libxext6 libxfixes3 libxkbcommon0 libxrandr2')
ENGINE_STATES = [
    ('stopped', 'Stopped'),
    ('starting', 'Starting'),
    ('running', 'Running'),
    ('failed', 'Failed'),
]


def is_odoo_sh():
    """Odoo.sh runs every build with ODOO_STAGE set (production / staging / dev).
    There the engine cannot run: only the Claude in Chrome mode is offered."""
    return bool(os.environ.get('ODOO_STAGE'))


def _module_file(*parts):
    return os.path.join(get_module_path('linkedin_sales_automation'), *parts)


def engine_code_version():
    """Fingerprint of the module's engine files (runner and Odoo tools). An engine
    started with other files is restarted by the watchdog: engine processes
    outlive Odoo restarts, so an update would otherwise not reach them."""
    import hashlib
    digest = hashlib.sha1()
    for name in ('runner.py', 'odoo_tools.py', 'login_input.py'):
        try:
            with open(_module_file('engine', name), 'rb') as handle:
                digest.update(handle.read())
        except OSError:
            pass
    return digest.hexdigest()[:12]


def _pid_alive(pid):
    """True when pid exists and is not a zombie."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open('/proc/%d/stat' % pid) as handle:
            return handle.read().split(')', 1)[1].split()[0] != 'Z'
    except (OSError, IndexError):
        return True


def _pid_cmdline(pid):
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as handle:
            return handle.read().replace(b'\0', b' ').decode(errors='replace')
    except OSError:
        return ''


def system_libraries_missing():
    """Chromium libraries absent from the system library cache (read-only)."""
    try:
        cache = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        for candidate in ('/sbin/ldconfig', '/usr/sbin/ldconfig'):
            try:
                cache = subprocess.run([candidate, '-p'], capture_output=True, text=True, timeout=30).stdout
                break
            except (OSError, subprocess.SubprocessError):
                continue
        else:
            return None                     # cannot tell
    present = {line.split()[0] for line in cache.splitlines()[1:] if line.strip()}
    return sorted(lib for lib in CHROMIUM_LIBRARIES if lib not in present)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LiEngineManager(models.AbstractModel):
    _name = 'li.engine.manager'
    _description = 'LinkedIn engine manager'

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------
    @api.model
    def _root(self):
        return Path(config['data_dir']) / ENGINE_DIR

    @api.model
    def _secure_dir(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        return path

    @api.model
    def _engine_python(self):
        return self._root() / 'env' / 'bin' / 'python'

    @api.model
    def _browsers_dir(self):
        return self._root() / 'browsers'

    # ------------------------------------------------------------------
    # Prepare engine
    # ------------------------------------------------------------------
    @api.model
    def _prepare_status(self):
        path = self._root() / 'prepare.json'
        try:
            status = json.loads(path.read_text())
        except (OSError, ValueError):
            return {'state': 'none', 'message': _('The engine has not been prepared yet.')}
        if status.get('state') == 'running' and not _pid_alive(status.get('pid')):
            status.update(state='failed', message=_('The preparation was interrupted (the installer stopped).'))
        return status

    @api.model
    def _installer_command(self, simulate=False):
        command = [sys.executable, _module_file('engine', 'installer.py'), str(self._root()),
                   '--odoo-python', sys.executable]
        return command + (['--simulate'] if simulate else [])

    @api.model
    def _start_prepare(self, simulate=False):
        """Start the installer detached; returns at once."""
        if is_odoo_sh():
            raise UserError(_('Odoo.sh cannot run the built-in engine: use Claude in Chrome.'))
        status = self._prepare_status()
        if status.get('state') == 'running':
            raise UserError(_('The engine is already being prepared. Refresh in a minute.'))
        root = self._secure_dir(self._root())
        (root / 'prepare.json').unlink(missing_ok=True)
        launch = [sys.executable, _module_file('engine', 'launch.py'), '--cwd', str(root),
                  '--log', str(root / 'prepare.out'), '--'] + self._installer_command(simulate)
        pid = int(subprocess.run(launch, capture_output=True, text=True, check=True, timeout=30).stdout.strip())
        _logger.info('LinkedIn engine: preparation started (pid %s)', pid)
        return pid

    @api.model
    def _health(self):
        """What the engine needs from the server, and the one admin command if
        something is missing."""
        python = self._engine_python()
        chrome = sorted(glob.glob(str(self._browsers_dir() / 'chromium-*' / 'chrome-linux*' / 'chrome')))
        missing = None
        if chrome:
            try:
                out = subprocess.run(['ldd', chrome[-1]], capture_output=True, text=True, timeout=60).stdout
                missing = sorted({line.split()[0] for line in out.splitlines() if 'not found' in line})
            except (OSError, subprocess.SubprocessError):
                missing = None
        if missing is None:
            missing = system_libraries_missing() or []
        xvfb = bool(shutil.which('xvfb-run') and shutil.which('Xvfb'))
        status = self._prepare_status()
        prepared = python.exists() and bool(chrome) and status.get('state') == 'done'
        commands = []
        if missing:
            commands.append(ADMIN_LIBS_COMMAND_PREPARED % python if python.exists() else ADMIN_LIBS_COMMAND_APT)
        if not xvfb:
            commands.append('sudo apt-get install -y xvfb      # optional: lets the browser run with a window')
        return {
            'prepared': prepared,
            'engine_version': status.get('engine_version'),
            'python': status.get('python'),
            'chrome': chrome[-1] if chrome else None,
            'missing_libs': missing,
            'xvfb': xvfb,
            'admin_commands': commands,
            'ready': prepared and not missing,
        }

    @api.model
    def _check_ready(self):
        health = self._health()
        if not health['prepared']:
            raise UserError(_('Prepare the LinkedIn engine first: Configuration › Settings › LinkedIn engine.'))
        if health['missing_libs']:
            raise UserError(_('The browser needs system libraries that are missing on this server. An '
                              'administrator runs once:\n\n%s', health['admin_commands'][0]))
        return health


class LiProfileEngine(models.Model):
    _inherit = 'li.profile'

    execution_mode = fields.Selection([
        ('engine', 'Built-in engine'),
        ('chrome', 'Claude in Chrome'),
    ], required=True, tracking=True, default=lambda self: 'chrome' if is_odoo_sh() else 'engine',
        help='Built-in engine: Odoo runs the LinkedIn browser on its own server and does the LinkedIn work in '
             'the background; Claude only writes the texts.\n'
             'Claude in Chrome: Claude does the LinkedIn clicks in your own Chrome (Claude in Chrome extension), '
             'only while that computer is on. The only mode on Odoo.sh.')
    is_odoo_sh = fields.Boolean(compute='_compute_is_odoo_sh')
    engine_state = fields.Selection(ENGINE_STATES, default='stopped', required=True, readonly=True, copy=False)
    engine_wanted = fields.Boolean(readonly=True, copy=False,
                                   help='The engine should be running: the watchdog restarts it if it stops.')
    engine_pid = fields.Integer(readonly=True, copy=False, groups='linkedin_sales_automation.group_li_admin')
    engine_port = fields.Integer(readonly=True, copy=False, groups='linkedin_sales_automation.group_li_admin')
    engine_host = fields.Char(readonly=True, copy=False, groups='linkedin_sales_automation.group_li_admin')
    engine_secret_path = fields.Char(readonly=True, copy=False, groups='linkedin_sales_automation.group_li_admin',
                                     help='Random URL path of the engine, new at every start. The engine has no '
                                          'login of its own: only a process that knows this path can use it.')
    engine_started = fields.Datetime(readonly=True, copy=False)
    engine_restarts = fields.Integer(readonly=True, copy=False)
    engine_error = fields.Text(readonly=True, copy=False)
    engine_code = fields.Char(readonly=True, copy=False, help='Version of the engine files the running engine started with.')
    engine_headless = fields.Boolean(readonly=True, copy=False, help='Runs without a window (no Xvfb found).')
    engine_log_tail = fields.Text(compute='_compute_engine_log_tail',
                                  groups='linkedin_sales_automation.group_li_admin')

    def _compute_is_odoo_sh(self):
        for profile in self:
            profile.is_odoo_sh = is_odoo_sh()

    @api.constrains('execution_mode')
    def _check_execution_mode(self):
        if is_odoo_sh() and any(p.execution_mode == 'engine' for p in self):
            raise ValidationError(_('Odoo.sh cannot run the built-in engine: use Claude in Chrome.'))

    def write(self, vals):
        if vals.get('execution_mode') == 'chrome':
            for profile in self.filtered(lambda p: p.execution_mode == 'engine' and p.id):
                profile.sudo().engine_wanted = False
                profile._engine_kill()
        return super().write(vals)

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    def _session_dir(self):
        """<root>/sessions/<database>/<profile id>, permissions 700."""
        self.ensure_one()
        manager = self.env['li.engine.manager']
        sessions = manager._secure_dir(manager._root() / 'sessions')
        return manager._secure_dir(manager._secure_dir(sessions / self.env.cr.dbname) / str(self.id))

    def _profile_dir(self):
        return self._session_dir() / 'profile'

    def _log_path(self):
        manager = self.env['li.engine.manager']
        logs = manager._secure_dir(manager._root() / 'logs')
        return logs / ('%s-%s.log' % (self.env.cr.dbname, self.id))

    def _compute_engine_log_tail(self):
        for profile in self:
            try:
                data = profile._log_path().read_bytes()[-6000:] if profile.id else b''
                profile.engine_log_tail = data.decode(errors='replace')
            except OSError:
                profile.engine_log_tail = False

    # ------------------------------------------------------------------
    # Process control
    # ------------------------------------------------------------------
    def _engine_command(self, port, headless):
        self.ensure_one()
        manager = self.env['li.engine.manager']
        # The secret path is passed as HTTP_PATH in the environment (see
        # _engine_env), never on the command line, which every local user can read.
        command = [str(manager._engine_python()), _module_file('engine', 'runner.py'),
                   '--transport', 'streamable-http', '--host', '127.0.0.1', '--port', str(port),
                   '--user-data-dir', str(self._profile_dir()), '--no-auto-import']
        if headless:
            return command
        return ['xvfb-run', '-a', '-s', '-screen 0 1280x900x24'] + command + ['--no-headless']

    def _engine_env(self, secret_path=None):
        session = self._session_dir()
        env = {
            'HTTP_PATH': secret_path or self.sudo().engine_secret_path or '/mcp',
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': str(session),                  # the engine keeps its own state out of Odoo's home
            'LANG': os.environ.get('LANG', 'C.UTF-8'),
            'PLAYWRIGHT_BROWSERS_PATH': str(self.env['li.engine.manager']._browsers_dir()),
            'PYTHONUNBUFFERED': '1',
            # the engine gives up on a LinkedIn action after this many seconds; Odoo waits a little longer
            'TOOL_TIMEOUT': str(self.env['li.mcp.tools']._param('engine_tool_timeout', 60)),
        }
        return env

    def _engine_lock(self, wait=False):
        """One engine action at a time per account, across workers and databases'
        crons. Transaction-scoped: released at commit / rollback."""
        self.ensure_one()
        sql = 'SELECT pg_advisory_xact_lock(%s, %s)' if wait else 'SELECT pg_try_advisory_xact_lock(%s, %s)'
        self.env.cr.execute(sql, (ENGINE_LOCK_NAMESPACE, self.id))
        return wait or self.env.cr.fetchone()[0]

    def _engine_is_mine(self):
        """The recorded pid really is this profile's engine, on this machine."""
        self.ensure_one()
        profile = self.sudo()
        if not profile.engine_pid or profile.engine_host != socket.gethostname():
            return False
        return _pid_alive(profile.engine_pid) and str(self._profile_dir()) in _pid_cmdline(profile.engine_pid)

    def _engine_url(self):
        profile = self.sudo()
        return 'http://127.0.0.1:%d%s' % (profile.engine_port, profile.engine_secret_path or '/mcp')

    def _engine_client(self, timeout=30):
        return McpClient(self._engine_url(), timeout=timeout, retries=1)

    def _engine_ping(self, timeout=5):
        if not self.sudo().engine_port:
            return False
        try:
            self._engine_client(timeout=timeout).initialize()
            return True
        except McpClientError:
            return False

    def _engine_start(self):
        """Start the engine detached. Returns True once it answers (or False
        while it is still starting)."""
        self.ensure_one()
        profile = self.sudo()
        if profile.execution_mode != 'engine':
            raise UserError(_('%s uses Claude in Chrome: it has no engine to start.', profile.name))
        health = self.env['li.engine.manager']._check_ready()
        if profile._engine_is_mine() and profile._engine_ping():
            profile.write({'engine_state': 'running', 'engine_wanted': True})
            return True
        profile._engine_kill()
        port = _free_port()
        secret_path = '/mcp-' + secrets.token_hex(16)
        headless = not health['xvfb']
        session = profile._session_dir()
        command = profile._engine_command(port, headless)
        launch = [sys.executable, _module_file('engine', 'launch.py'), '--cwd', str(session),
                  '--log', str(profile._log_path()), '--'] + command
        try:
            out = subprocess.run(launch, capture_output=True, text=True, check=True, timeout=30,
                                 env=profile._engine_env(secret_path))
            pid = int(out.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            profile.write({'engine_state': 'failed', 'engine_error': str(exc)})
            raise UserError(_('The engine could not be started: %s', exc)) from exc
        profile.write({'engine_pid': pid, 'engine_port': port, 'engine_host': socket.gethostname(),
                       'engine_secret_path': secret_path,
                       'engine_state': 'starting', 'engine_wanted': True, 'engine_started': fields.Datetime.now(),
                       'engine_code': engine_code_version(),
                       'engine_error': False, 'engine_headless': headless})
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if not _pid_alive(pid):
                profile.write({'engine_state': 'failed', 'engine_error': _('The engine exited at start. See its log.')})
                return False
            if profile._engine_ping(timeout=3):
                profile.engine_state = 'running'
                _logger.info('LinkedIn engine %s (profile %s) running on port %s', pid, profile.id, port)
                return True
            time.sleep(0.5)
        return False

    def _engine_kill(self):
        """Stop this profile's engine (its whole process group)."""
        self.ensure_one()
        profile = self.sudo()
        pid = profile.engine_pid
        if pid and profile._engine_is_mine():
            for sig, wait in ((signal.SIGTERM, STOP_TIMEOUT), (signal.SIGKILL, 3)):
                try:
                    os.killpg(pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
                deadline = time.monotonic() + wait
                while time.monotonic() < deadline and _pid_alive(pid):
                    time.sleep(0.2)
                if not _pid_alive(pid):
                    break
        profile.write({'engine_pid': 0, 'engine_port': 0, 'engine_secret_path': False, 'engine_state': 'stopped'})

    def _engine_refresh(self):
        """Bring engine_state in line with reality."""
        for profile in self.sudo():
            if profile._engine_is_mine():
                state = 'running' if profile._engine_ping() else 'starting'
            elif profile.engine_state in ('running', 'starting'):
                state = 'failed' if profile.engine_wanted else 'stopped'
            else:
                state = profile.engine_state
            if state != profile.engine_state:
                profile.engine_state = state

    def _engine_call(self, tool, arguments=None, timeout=200):
        """Call one engine tool, one call at a time per account."""
        self.ensure_one()
        if not self._engine_lock(wait=False):
            raise UserError(_('The engine of %s is busy with another action.', self.name))
        if not (self._engine_is_mine() and self._engine_ping()):
            raise UserError(_('The engine of %s is not running.', self.name))
        client = self._engine_client(timeout=timeout)
        client.initialize()
        return client.call_tool(tool, arguments or {}, timeout=timeout)

    def _engine_tools(self):
        self.ensure_one()
        client = self._engine_client()
        client.initialize()
        return client.list_tools()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def _post_as_user(self, body):
        # managers only read profiles; the note is still theirs
        self.sudo().message_post(body=body, author_id=self.env.user.partner_id.id, subtype_xmlid='mail.mt_note')

    def _check_engine_rights(self):
        if not self.env.user.has_group('linkedin_sales_automation.group_li_manager'):
            raise UserError(_('Only a LinkedIn Sales Manager can start or stop engines.'))

    def action_engine_start(self):
        self._check_engine_rights()
        for profile in self:
            if not profile._engine_lock(wait=False):
                raise UserError(_('The engine of %s is busy. Try again in a moment.', profile.name))
            ok = profile._engine_start()
            profile._post_as_user(_('Engine started by %s', self.env.user.name) if ok
                                  else _('Engine starting (started by %s)', self.env.user.name))
        return self._notify(_('Engine'), _('Engine running.') if self.engine_state == 'running'
                            else _('The engine is starting; press Status in a moment.'), 'info')

    def action_engine_stop(self):
        self._check_engine_rights()
        for profile in self:
            profile._engine_lock(wait=True)
            profile.sudo().engine_wanted = False
            profile._engine_kill()
            profile._post_as_user(_('Engine stopped by %s', self.env.user.name))
        return True

    def action_engine_status(self):
        self._engine_refresh()
        profile = self.sudo()
        if profile.engine_state != 'running':
            return self._notify(_('Engine'), _('Engine %s.', dict(ENGINE_STATES)[profile.engine_state]),
                                'warning')
        try:
            tools = sorted(t.get('name') for t in self._engine_tools())
        except McpClientError as exc:
            return self._notify(_('Engine'), str(exc), 'danger')
        return self._notify(_('Engine running'), _('%(n)s tools: %(names)s', n=len(tools), names=', '.join(tools)),
                            'success')

    # ------------------------------------------------------------------
    # Watchdog and clean-up
    # ------------------------------------------------------------------
    @api.model
    def _cron_engine_watchdog(self):
        """Every 5 minutes: restart engines that should run but do not (crash,
        Odoo restart, reboot)."""
        restarted = 0
        if is_odoo_sh():
            return 0
        for profile in self.sudo().search([('engine_wanted', '=', True), ('execution_mode', '=', 'engine')]):
            if not profile._engine_lock(wait=False):
                continue
            if profile._engine_is_mine():
                if profile.engine_code != engine_code_version():
                    # the module was updated: start the engine again with the new files
                    _logger.info('LinkedIn engine of profile %s restarted after a module update', profile.id)
                    profile._engine_kill()
                    profile.engine_wanted = True
                    profile._post_as_user(_('Engine restarted after a module update.'))
                else:
                    profile._engine_refresh()
                    continue
            if profile.engine_host and profile.engine_host != socket.gethostname() and profile.engine_pid:
                continue                    # managed by another Odoo server
            try:
                profile._engine_start()
                profile.engine_restarts += 1
                restarted += 1
            except UserError as exc:
                profile.write({'engine_state': 'failed', 'engine_error': str(exc)})
        return restarted

    def unlink(self):
        for profile in self:
            profile._engine_kill()
            shutil.rmtree(profile._session_dir(), ignore_errors=True)
        return super().unlink()
