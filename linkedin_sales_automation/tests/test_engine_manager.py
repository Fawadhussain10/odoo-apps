import os
import signal
import stat
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import requests

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import LiTransactionCase
from ..models import li_engine_manager
from ..models.li_engine_manager import ENGINE_LOCK_NAMESPACE, _pid_alive, _pid_cmdline

FAKE_ENGINE = os.path.join(os.path.dirname(__file__), 'fake_engine.py')
READY = {'prepared': True, 'ready': True, 'xvfb': False, 'missing_libs': [], 'admin_commands': [],
         'engine_version': 'test', 'python': 'test', 'chrome': '/fake/chrome'}


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestEngineManager(LiTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp(prefix='li-engine-test-')
        Manager = type(cls.env['li.engine.manager'])
        Profile = type(cls.env['li.profile'])
        cls.startClassPatcher(patch.object(Manager, '_root', lambda self: Path(cls.tmp)))

        def fake_command(self, port, headless):
            return [sys.executable, FAKE_ENGINE, '--transport', 'streamable-http', '--host', '127.0.0.1',
                    '--port', str(port), '--user-data-dir', str(self._profile_dir()), '--no-auto-import']
        cls.startClassPatcher(patch.object(Profile, '_engine_command', fake_command))
        cls.startClassPatcher(patch.object(Manager, '_check_ready', lambda self: dict(READY)))
        (cls.profile | cls.profile2).write({'execution_mode': 'engine'})

    def setUp(self):
        super().setUp()
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        for profile in (self.profile | self.profile2).exists():
            profile._engine_kill()

    # ------------------------------------------------------------------
    def test_start_status_stop(self):
        self.assertTrue(self.profile._engine_start())
        profile = self.profile.sudo()
        self.assertEqual(profile.engine_state, 'running')
        self.assertTrue(profile.engine_wanted)
        self.assertTrue(_pid_alive(profile.engine_pid))
        self.assertTrue(profile._engine_is_mine())
        self.assertIn('get_my_profile', [t['name'] for t in profile._engine_tools()])
        result = profile._engine_call('get_my_profile')
        self.assertIn('Harvey Reid', result['content'][0]['text'])
        self.assertEqual(self.env['li.profile']._own_profile_name(result), 'Harvey Reid')
        pid = profile.engine_pid
        self.profile.with_user(self.manager).action_engine_stop()
        self.assertFalse(_pid_alive(pid))
        self.assertEqual((profile.engine_state, profile.engine_pid, profile.engine_wanted), ('stopped', 0, False))

    def test_watchdog_restarts_an_engine_after_a_module_update(self):
        """Engine processes outlive Odoo restarts: after an update the watchdog starts
        them again with the new engine files (live test: follow_person missing)."""
        self.assertTrue(self.profile._engine_start())
        profile = self.profile.sudo()
        pid = profile.engine_pid
        self.assertEqual(profile.engine_code, li_engine_manager.engine_code_version())
        self.profile.env['li.profile']._cron_engine_watchdog()
        self.assertEqual(profile.engine_pid, pid)                       # same code: left alone
        profile.engine_code = 'older-files'
        self.profile.env['li.profile']._cron_engine_watchdog()
        self.assertNotEqual(profile.engine_pid, pid)
        self.assertFalse(_pid_alive(pid))
        self.assertEqual(profile.engine_code, li_engine_manager.engine_code_version())
        self.assertEqual(profile.engine_state, 'running')
        self.assertEqual(profile.engine_restarts, 1)

    def test_two_engines_on_their_own_ports(self):
        self.profile._engine_start()
        self.profile2._engine_start()
        a, b = self.profile.sudo(), self.profile2.sudo()
        self.assertNotEqual(a.engine_port, b.engine_port)
        self.assertNotEqual(a.engine_pid, b.engine_pid)
        self.assertNotEqual(a._profile_dir(), b._profile_dir())
        for profile in (a, b):
            self.assertEqual(len(profile._engine_tools()), 12)

    def test_engine_answers_only_on_its_secret_path(self):
        self.profile._engine_start()
        profile = self.profile.sudo()
        secret = profile.engine_secret_path
        self.assertRegex(secret, r'^/mcp-[0-9a-f]{32}$')
        self.assertNotIn(secret, _pid_cmdline(profile.engine_pid), 'never on the command line (ps)')
        environ = Path('/proc/%d/environ' % profile.engine_pid).read_bytes().decode(errors='replace')
        self.assertIn('HTTP_PATH=%s' % secret, environ)
        self.assertEqual(stat.S_IMODE(os.stat('/proc/%d/environ' % profile.engine_pid).st_mode) & 0o077, 0,
                         'the environment is private to the process owner')
        base = 'http://127.0.0.1:%d' % profile.engine_port
        for wrong in ('/mcp', '/', secret[:-1], '/mcp-' + '0' * 32):
            response = requests.post(base + wrong, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                                     timeout=5)
            self.assertEqual(response.status_code, 404, wrong)
        self.assertEqual(len(profile._engine_tools()), 12)
        with self.assertRaises(AccessError):
            self.profile.with_user(self.manager).read(['engine_secret_path'])
        first = secret
        self.profile._engine_kill()
        self.assertFalse(profile.engine_secret_path)
        self.profile._engine_start()
        self.assertNotEqual(self.profile.sudo().engine_secret_path, first, 'a new secret at every start')

    def test_session_folder_is_private(self):
        folder = self.profile._session_dir()
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
        self.assertEqual(folder.parent.name, self.env.cr.dbname)
        self.assertEqual(folder.name, str(self.profile.id))

    def test_engine_is_detached_from_odoo(self):
        self.profile._engine_start()
        pid = self.profile.sudo().engine_pid
        self.assertEqual(os.getpgid(pid), pid, 'own process group')
        with open('/proc/%d/stat' % pid) as handle:
            ppid = int(handle.read().split(')', 1)[1].split()[1])
        self.assertNotEqual(ppid, os.getpid(), 'not a child of the Odoo worker')

    def test_watchdog_restarts_a_dead_engine(self):
        self.profile._engine_start()
        old_pid = self.profile.sudo().engine_pid
        os.killpg(old_pid, signal.SIGKILL)
        for _i in range(50):
            if not _pid_alive(old_pid):
                break
            time.sleep(0.1)
        self.profile._engine_refresh()
        self.assertEqual(self.profile.engine_state, 'failed')
        self.assertEqual(self.env['li.profile']._cron_engine_watchdog(), 1)
        profile = self.profile.sudo()
        self.assertEqual(profile.engine_state, 'running')
        self.assertNotEqual(profile.engine_pid, old_pid)
        self.assertEqual(profile.engine_restarts, 1)
        # a stopped engine is left alone
        self.profile.action_engine_stop()
        self.assertEqual(self.env['li.profile']._cron_engine_watchdog(), 0)

    def test_one_action_at_a_time_per_account(self):
        self.assertTrue(self.profile._engine_lock())
        other = self.registry.cursor()
        try:
            other.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', (ENGINE_LOCK_NAMESPACE, self.profile.id))
            self.assertFalse(other.fetchone()[0], 'a second worker must not get the same account')
            other.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', (ENGINE_LOCK_NAMESPACE, self.profile2.id))
            self.assertTrue(other.fetchone()[0], 'another account is free')
        finally:
            other.rollback()
            other.close()

    def test_rights_and_modes(self):
        with self.assertRaises(UserError):
            self.profile.with_user(self.rep).action_engine_start()
        self.profile._engine_start()
        pid = self.profile.sudo().engine_pid
        self.profile.execution_mode = 'chrome'
        self.assertFalse(_pid_alive(pid), 'switching to Claude in Chrome stops the engine')
        self.assertEqual(self.profile.engine_state, 'stopped')
        with self.assertRaisesRegex(UserError, 'Claude in Chrome'):
            self.profile._engine_start()

    def test_odoo_sh_forces_chrome_mode(self):
        with patch.dict(os.environ, {'ODOO_STAGE': 'production'}):
            self.assertTrue(li_engine_manager.is_odoo_sh())
            profile = self.env['li.profile'].create({
                'name': 'On Odoo.sh', 'linkedin_url': 'https://www.linkedin.com/in/sh-test/', 'account_key': 'sh'})
            self.assertEqual(profile.execution_mode, 'chrome')
            self.assertTrue(profile.is_odoo_sh)
            with self.assertRaises(ValidationError):
                profile.execution_mode = 'engine'
            with self.assertRaises(UserError):
                self.env['li.engine.manager']._start_prepare(simulate=True)
            self.assertEqual(self.env['li.profile']._cron_engine_watchdog(), 0)
            values = self.env['res.config.settings']._li_engine_values()
            self.assertTrue(values['li_is_odoo_sh'])
        self.assertFalse(li_engine_manager.is_odoo_sh())
        new = self.env['li.profile'].create({
            'name': 'Self-hosted', 'linkedin_url': 'https://www.linkedin.com/in/self-test/', 'account_key': 'self'})
        self.assertEqual(new.execution_mode, 'engine')

    def test_delete_profile_stops_engine_and_removes_session(self):
        persona_free = self.env['li.profile'].create({
            'name': 'Temporary', 'linkedin_url': 'https://www.linkedin.com/in/tmp-test/', 'account_key': 'tmp',
            'connection_state': 'connected'})
        persona_free._engine_start()
        pid, folder = persona_free.sudo().engine_pid, persona_free._session_dir()
        (folder / 'cookies.json').write_text('{}')
        persona_free.unlink()
        self.assertFalse(_pid_alive(pid))
        self.assertFalse(folder.exists())


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestPrepareEngine(LiTransactionCase):

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix='li-prepare-test-')
        tmp = self.tmp
        self.startPatcher(patch.object(type(self.env['li.engine.manager']), '_root', lambda self: Path(tmp)))

    def _wait(self, manager, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            status = manager._prepare_status()
            if status['state'] in ('done', 'failed'):
                return status
            time.sleep(0.2)
        self.fail('installer did not finish: %s' % manager._prepare_status())

    def test_prepare_runs_detached_and_reports_progress(self):
        manager = self.env['li.engine.manager']
        self.assertEqual(manager._prepare_status()['state'], 'none')
        started = time.monotonic()
        manager._start_prepare(simulate=True)
        self.assertLess(time.monotonic() - started, 5, 'the request returns at once')
        status = self._wait(manager)
        self.assertEqual(status['state'], 'done', status)
        self.assertEqual(status['done_steps'], ['uv', 'python', 'environment', 'engine', 'browser', 'check'])
        self.assertTrue(status['engine_version'].startswith('4.26.2'))
        self.assertTrue((Path(self.tmp) / 'prepare.log').exists())
        values = self.env['res.config.settings']._li_engine_values()
        self.assertIn('4.26.2', values['li_engine_detail'])

    def test_interrupted_preparation_is_reported(self):
        manager = self.env['li.engine.manager']
        Path(self.tmp).mkdir(exist_ok=True)
        (Path(self.tmp) / 'prepare.json').write_text('{"state": "running", "pid": 999999999, "message": "x"}')
        self.assertEqual(manager._prepare_status()['state'], 'failed')

    def test_health_shows_the_admin_command(self):
        manager = self.env['li.engine.manager']
        chrome = Path(self.tmp) / 'browsers' / 'chromium-1' / 'chrome-linux64' / 'chrome'
        chrome.parent.mkdir(parents=True)
        chrome.write_text('')
        python = Path(self.tmp) / 'env' / 'bin' / 'python'
        python.parent.mkdir(parents=True)
        python.write_text('')
        real_run = li_engine_manager.subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == 'ldd':
                class Out:
                    stdout = '\tlibnss3.so => not found\n\tlibc.so.6 => /lib/libc.so.6\n'
                return Out()
            return real_run(cmd, *args, **kwargs)
        with patch.object(li_engine_manager.subprocess, 'run', fake_run):
            health = manager._health()
        self.assertEqual(health['missing_libs'], ['libnss3.so'])
        self.assertIn('patchright install-deps chromium', health['admin_commands'][0])
        self.assertFalse(health['ready'])
        with self.assertRaisesRegex(UserError, 'Prepare the LinkedIn engine first'):
            manager._check_ready()
