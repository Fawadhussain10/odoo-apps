import asyncio
import base64
import io
import json
import logging
import os
import shutil
import stat
import sys
import tempfile
import time
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import BaseCase, tagged

from .common import LiTransactionCase
from ..engine import login_input
from ..models.li_engine_manager import _pid_alive
from ..models.li_login import SessionZipError, read_session_zip

HERE = os.path.dirname(__file__)
FAKE_ENGINE = os.path.join(HERE, 'fake_engine.py')
FAKE_HELPER = os.path.join(HERE, 'fake_login_helper.py')
READY = {'prepared': True, 'ready': True, 'xvfb': False, 'missing_libs': [], 'admin_commands': [],
         'engine_version': 'test', 'python': 'test', 'chrome': '/fake/chrome'}
GOOD_LI_AT = 'AQEDA' + 'x' * 120


def make_zip(entries, symlinks=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        for name, target in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, target)
    return buffer.getvalue()


SESSION_COOKIES = json.dumps([{'name': 'li_at', 'value': GOOD_LI_AT, 'domain': '.www.linkedin.com', 'path': '/'},
                              {'name': 'JSESSIONID', 'value': 'ajax:1', 'domain': '.www.linkedin.com', 'path': '/'}])


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestConnectLinkedIn(LiTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp(prefix='li-login-test-')
        Manager = type(cls.env['li.engine.manager'])
        Profile = type(cls.env['li.profile'])
        cls.startClassPatcher(patch.object(Manager, '_root', lambda self: Path(cls.tmp)))
        cls.startClassPatcher(patch.object(Manager, '_check_ready', lambda self: dict(READY)))
        cls.startClassPatcher(patch.object(Manager, '_health', lambda self: dict(READY)))

        def engine_command(self, port, headless):
            return [sys.executable, FAKE_ENGINE, '--transport', 'streamable-http', '--host', '127.0.0.1',
                    '--port', str(port), '--user-data-dir', str(self._profile_dir()), '--no-auto-import']

        def helper_command(self, mode, port, headless, cookies_file=None):
            command = [sys.executable, FAKE_HELPER, '--mode', mode, '--port', str(port),
                       '--user-data-dir', str(self._profile_dir())]
            return command + (['--cookies', str(cookies_file)] if cookies_file else [])
        cls.startClassPatcher(patch.object(Profile, '_engine_command', engine_command))
        cls.startClassPatcher(patch.object(Profile, '_login_helper_command', helper_command))
        (cls.profile | cls.profile2).write({'execution_mode': 'engine', 'connection_state': 'not_connected',
                                            'my_display_name': False})
        cls.admin = cls.env.ref('base.user_admin')

    def setUp(self):
        super().setUp()
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        for profile in (self.profile | self.profile2).exists():
            profile.sudo()._login_kill()
            profile._engine_kill()
            shutil.rmtree(profile.sudo()._session_dir(), ignore_errors=True)   # files do not roll back

    def _poll_until(self, profile, token, states, seconds=20):
        deadline = time.monotonic() + seconds
        view = None
        while time.monotonic() < deadline:
            view = profile._login_poll(token)
            if view['state'] in states:
                return view
            time.sleep(0.2)
        self.fail('state %s not reached, last %s' % (states, view))

    def _start(self, profile, mode='login', **kwargs):
        token = profile._login_start(mode, **kwargs)
        if mode == 'login':
            self._poll_until(profile, token, ('waiting',))
        return token

    def _events_file(self, profile):
        return profile.sudo()._session_dir() / 'fake-events.jsonl'

    # ------------------------------------------------------------------
    # Rights and token
    # ------------------------------------------------------------------
    def test_only_owner_or_administrator(self):
        own = self.profile.with_user(self.rep)            # rep owns profile
        self.assertTrue(own._login_start('login'))
        with self.assertRaises(AccessError):
            self.profile2.with_user(self.rep)._login_start('login')       # owned by the manager
        with self.assertRaises(AccessError):
            self.profile.with_user(self.manager)._login_start('login')    # manager, not owner, not admin
        with self.assertRaises(AccessError):
            self.profile.with_user(self.manager).action_disconnect()
        self.assertTrue(self.profile2.with_user(self.manager)._login_start('login'))
        self.assertTrue(self.profile2.with_user(self.admin)._login_start('login'))
        chrome = self.env['li.profile'].create({'name': 'Chrome one', 'linkedin_url': 'https://www.linkedin.com/in/c1/',
                                                'account_key': 'c1', 'execution_mode': 'chrome', 'owner_id': self.rep.id})
        with self.assertRaisesRegex(UserError, 'Claude in Chrome'):
            chrome.with_user(self.rep)._login_start('login')

    def test_token_is_single_use_and_bound_to_the_user(self):
        profile = self.profile.with_user(self.rep)
        token = self._start(profile)
        sudo = self.profile.sudo()
        self.assertNotEqual(sudo.login_token_hash, token, 'only a hash is stored')
        self.assertEqual(len(sudo.login_token_hash), 64)
        with self.assertRaises(AccessError):
            profile._login_poll('wrong-token')
        with self.assertRaises(AccessError):
            self.profile.with_user(self.admin)._login_poll(token)     # right token, other user
        self.assertEqual(profile._login_poll(token)['state'], 'waiting')
        second = self._start(profile)
        with self.assertRaises(AccessError):
            profile._login_poll(token)                                 # replaced by the new sign-in
        self.assertEqual(profile._login_poll(second)['state'], 'waiting')
        with self.assertRaises(AccessError):
            self.profile.with_user(self.manager).read(['login_token_hash'])

    def test_timeout(self):
        profile = self.profile.with_user(self.rep)
        token = profile._login_start('login')
        pid = self.profile.sudo().login_pid
        self.assertTrue(_pid_alive(pid))
        self.profile.sudo().login_expires = fields.Datetime.now() - timedelta(seconds=1)
        view = profile._login_poll(token)
        self.assertEqual(view['state'], 'failed')
        self.assertIn('10 minutes', view['message'])
        self.assertFalse(_pid_alive(pid))
        self.assertEqual(profile._login_input(token, [{'type': 'text', 'text': 'a'}]), {'ok': False})
        # the watchdog cron ends expired sign-ins too
        token = profile._login_start('login')
        pid = self.profile.sudo().login_pid
        self.profile.sudo().login_expires = fields.Datetime.now() - timedelta(seconds=1)
        self.env['li.profile']._cron_engine_watchdog()
        self.assertEqual(self.profile.login_state, 'failed')
        self.assertFalse(_pid_alive(pid))

    # ------------------------------------------------------------------
    # Log in here: states, input, privacy, success
    # ------------------------------------------------------------------
    def test_state_machine_and_success(self):
        profile = self.profile.with_user(self.rep)
        token = profile._login_start('login')
        self.assertEqual(self.profile.engine_state, 'stopped', 'engine stopped during the sign-in')
        self.assertFalse(self.profile.engine_wanted, 'the watchdog leaves it alone')
        self.assertEqual(self._poll_until(profile, token, ('waiting',))['state'], 'waiting')
        frame, seq = profile._login_frame(token, -1)
        self.assertTrue(frame.startswith(b'\xff\xd8'))
        self.assertEqual(profile._login_frame(token, seq), (None, seq), 'no new frame: nothing sent')
        profile._login_input(token, [{'type': 'text', 'text': 'TWOSTEP'}])
        view = self._poll_until(profile, token, ('two_step',))
        self.assertIn('LinkedIn app', view['message'])
        profile._login_input(token, [{'type': 'text', 'text': 'CAPTCHA'}])
        self.assertIn('security check', self._poll_until(profile, token, ('captcha',))['message'])
        helper_pid = self.profile.sudo().login_pid
        profile._login_input(token, [{'type': 'text', 'text': 'LOGIN-OK'}])
        view = self._poll_until(profile, token, ('connected', 'failed'))
        self.assertEqual(view['state'], 'connected', view)
        sudo = self.profile.sudo()
        self.assertEqual(sudo.connection_state, 'connected')
        self.assertEqual(sudo.my_display_name, 'Harvey Reid')
        self.assertEqual(sudo.engine_state, 'running')
        self.assertTrue(sudo.engine_wanted)
        self.assertTrue(sudo.connected_date)
        self.assertFalse(_pid_alive(helper_pid), 'the sign-in browser is closed')
        self.assertFalse(sudo.login_secret)
        self.assertEqual(profile._login_input(token, [{'type': 'text', 'text': 'x'}]), {'ok': False})
        self.assertEqual(profile._login_frame(token, -1), (None, 0))
        self.assertEqual(profile._login_poll(token)['state'], 'connected', 'the final state stays readable')

    def test_failed_and_cancelled(self):
        profile = self.profile.with_user(self.rep)
        token = self._start(profile)
        profile._login_input(token, [{'type': 'text', 'text': 'LOGIN-BAD'}])
        view = self._poll_until(profile, token, ('failed',))
        self.assertIn('refused', view['message'])
        self.assertEqual(self.profile.connection_state, 'not_connected')
        token = profile._login_start('login')
        pid = self.profile.sudo().login_pid
        self.assertEqual(profile._login_cancel(token)['state'], 'failed')
        self.assertFalse(_pid_alive(pid))

    def test_input_is_forwarded_and_never_logged(self):
        profile = self.profile.with_user(self.rep)
        token = profile._login_start('login')
        self._poll_until(profile, token, ('waiting',))
        secret_text = 'my-Secret-Pa55word'
        events = [{'type': 'click', 'x': 0.5, 'y': 0.25, 'button': 'left'}, {'type': 'text', 'text': secret_text},
                  {'type': 'key', 'key': 'Enter'}]
        records = []

        class Grab(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())
        handler = Grab(level=logging.DEBUG)
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            self.assertEqual(profile._login_input(token, events), {'ok': True})
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)
        forwarded = [json.loads(line) for line in self._events_file(self.profile).read_text().splitlines()]
        self.assertEqual(forwarded[-1], events)
        self.assertFalse([m for m in records if secret_text in m], 'typed text never reaches a log')
        sudo = self.profile.sudo()
        stored = ' '.join(str(sudo[name]) for name in sudo._fields if sudo._fields[name].type in ('char', 'text'))
        self.assertNotIn(secret_text, stored, 'nor a field')

    def test_headless_or_window(self):
        from ..models.li_login import LiProfileLogin
        headless = LiProfileLogin._login_helper_command(self.profile, 'login', 8123, True)
        window = LiProfileLogin._login_helper_command(self.profile, 'login', 8123, False)
        self.assertIn('--headless', headless)
        self.assertNotIn('xvfb-run', headless)
        self.assertEqual(window[0], 'xvfb-run')
        self.assertNotIn('--headless', window)

    # ------------------------------------------------------------------
    # Import session and paste cookie
    # ------------------------------------------------------------------
    def test_import_session(self):
        data = make_zip({'.linkedin-mcp/cookies.json': SESSION_COOKIES,
                         '.linkedin-mcp/source-state.json': '{"version": 1}',
                         '.linkedin-mcp/profile/Default/Preferences': '{}'})
        cookies = read_session_zip(data)
        self.assertEqual(cookies[0]['name'], 'li_at')
        profile = self.profile.with_user(self.rep)
        token = profile._login_start('cookies', cookies=cookies)
        self.assertEqual(self.profile.login_state, 'validating')
        session = self.profile.sudo()._session_dir()
        view = self._poll_until(profile, token, ('connected', 'failed'))
        self.assertEqual(view['state'], 'connected', view)
        self.assertEqual(self.profile.my_display_name, 'Harvey Reid')
        self.assertFalse(list((Path(self.tmp) / 'incoming').glob('*.json')), 'the uploaded cookies are not left behind')

    def test_import_is_checked_with_get_my_profile(self):
        cookies = read_session_zip(make_zip({'cookies.json': SESSION_COOKIES}))
        session = self.profile.sudo()._session_dir()
        (session / 'fake-logged-out').write_text('1')
        profile = self.profile.with_user(self.rep)
        token = profile._login_start('cookies', cookies=cookies)
        view = self._poll_until(profile, token, ('connected', 'failed'))
        self.assertEqual(view['state'], 'failed')
        self.assertIn('could not be confirmed', view['message'])
        self.assertEqual(self.profile.connection_state, 'not_connected')
        self.assertEqual(self.profile.engine_state, 'stopped')
        self.assertFalse((session / 'cookies.json').exists(), 'a refused session is deleted')

    def test_zip_rejections(self):
        cases = {
            'slip': make_zip({'../evil.json': '{}', 'cookies.json': SESSION_COOKIES}),
            'nested slip': make_zip({'profile/../../evil': 'x', 'cookies.json': SESSION_COOKIES}),
            'absolute': make_zip({'/etc/cron.d/x': 'x', 'cookies.json': SESSION_COOKIES}),
            'windows drive': make_zip({'C:/x': 'x', 'cookies.json': SESSION_COOKIES}),
            'symlink': make_zip({'cookies.json': SESSION_COOKIES}, symlinks=[('profile/link', '/etc/passwd')]),
            'unexpected': make_zip({'cookies.json': SESSION_COOKIES, 'evil.sh': 'rm -rf /'}),
            'missing': make_zip({'source-state.json': '{}'}),
            'no li_at': make_zip({'cookies.json': json.dumps([{'name': 'JSESSIONID', 'value': 'x',
                                                               'domain': '.linkedin.com'}])}),
            'not a list': make_zip({'cookies.json': '{"li_at": "x"}'}),
            'twice': make_zip({'cookies.json': SESSION_COOKIES, '.linkedin-mcp/cookies.json': SESSION_COOKIES}),
            'not a zip': b'PK-not-really',
            'empty': b'',
        }
        for label, data in cases.items():
            with self.assertRaises(SessionZipError, msg=label):
                read_session_zip(data)
        big = io.BytesIO()
        with zipfile.ZipFile(big, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('cookies.json', SESSION_COOKIES)
            archive.writestr('profile/huge', b'\0' * (601 * 1024 * 1024))
        with self.assertRaisesRegex(SessionZipError, 'too large'):
            read_session_zip(big.getvalue())

    def test_paste_cookie(self):
        with self.assertRaises(login_input.InputError):
            login_input.li_at_cookies('short', time.time())
        with self.assertRaises(login_input.InputError):
            login_input.li_at_cookies('has spaces ' * 10, time.time())
        cookies = login_input.li_at_cookies('li_at=%s' % GOOD_LI_AT, 1000)
        self.assertEqual((cookies[0]['name'], cookies[0]['value']), ('li_at', GOOD_LI_AT))
        self.assertGreater(cookies[0]['expires'], 1000)
        profile = self.profile.with_user(self.rep)
        token = profile._login_start('cookies', cookies=login_input.li_at_cookies('rejected-by-linkedin' * 3, 0))
        view = self._poll_until(profile, token, ('connected', 'failed'))
        self.assertEqual(view['state'], 'failed')
        self.assertIn('did not accept', view['message'])

    # ------------------------------------------------------------------
    # Disconnect and session expiry
    # ------------------------------------------------------------------
    def test_disconnect(self):
        profile = self.profile.with_user(self.rep)
        token = self._start(profile)
        profile._login_input(token, [{'type': 'text', 'text': 'LOGIN-OK'}])
        self._poll_until(profile, token, ('connected',))
        sudo = self.profile.sudo()
        engine_pid, session = sudo.engine_pid, sudo._session_dir()
        self.assertTrue((session / 'cookies.json').exists())
        profile.action_disconnect()
        self.assertFalse(_pid_alive(engine_pid))
        self.assertFalse((session / 'cookies.json').exists())
        self.assertEqual((sudo.connection_state, sudo.engine_state, sudo.engine_wanted),
                         ('not_connected', 'stopped', False))

    def test_session_expiry_from_tool_errors(self):
        persona = self._make_persona('Expiry persona', profile=self.profile)
        persona.chat_agent_id.write({'step_ids': [(0, 0, {'name': 'Intro', 'trigger': 'after_accept'})],
                                     'pivot_criteria': 'Asks for a call'})
        profile = self.profile.with_user(self.rep)
        token = self._start(profile)
        profile._login_input(token, [{'type': 'text', 'text': 'LOGIN-OK'}])
        self._poll_until(profile, token, ('connected',))
        persona.action_connection_run()
        self.assertEqual(persona.state, 'active')
        (self.profile.sudo()._session_dir() / 'fake-logged-out').write_text('1')
        result = self.profile._engine_call('search_people', {'keywords': 'Founder'})
        self.assertTrue(result['isError'])
        self.assertEqual(self.profile.connection_state, 'reconnect_needed')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertTrue(self.profile.activity_ids.filtered(lambda a: a.user_id == self.rep))


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestLoginInput(BaseCase):
    """The pure part of the sign-in browser: input checks and forwarding, with a
    fake page and a fake CDP session."""

    def test_validate_events(self):
        actions = login_input.validate_events([
            {'type': 'click', 'x': 0.5, 'y': 2, 'button': 'left'},
            {'type': 'key', 'key': 'Enter'}, {'type': 'key', 'key': 'Control+a'},
            {'type': 'text', 'text': 'hello'}, {'type': 'scroll', 'dx': 0, 'dy': 99999},
        ])
        self.assertEqual(actions, [('click', 0.5, 1.0, 'left'), ('key', 'Enter'), ('key', 'Control+a'),
                                   ('text', 'hello'), ('scroll', 0, 2000)])
        for bad in ([{'type': 'eval', 'js': 'x'}], [{'type': 'key', 'key': 'F12'}],
                    [{'type': 'key', 'key': 'Control+Shift+i'}], [{'type': 'text', 'text': 'x' * 513}],
                    [{'type': 'click', 'x': 'a', 'y': 0}], [{'type': 'click', 'x': 0, 'y': 0, 'button': 'back'}],
                    'not a list', [{}] * 51):
            with self.assertRaises(login_input.InputError, msg=repr(bad)[:40]):
                login_input.validate_events(bad)

    def test_apply_actions_on_a_fake_page(self):
        calls = []

        class Mouse:
            async def click(self, x, y, button, click_count):
                calls.append(('click', x, y, button, click_count))

            async def move(self, x, y):
                calls.append(('move', x, y))

            async def wheel(self, dx, dy):
                calls.append(('wheel', dx, dy))

        class Keyboard:
            async def press(self, key):
                calls.append(('press', key))

            async def insert_text(self, text):
                calls.append(('insert', text))

        class Page:
            mouse, keyboard = Mouse(), Keyboard()

        actions = login_input.validate_events([
            {'type': 'click', 'x': 0.5, 'y': 0.25}, {'type': 'dblclick', 'x': 0, 'y': 1},
            {'type': 'text', 'text': 'abc'}, {'type': 'key', 'key': 'Tab'}, {'type': 'scroll', 'dx': 3, 'dy': -4}])
        asyncio.run(login_input.apply_actions(Page(), actions, (1280, 800)))
        self.assertEqual(calls, [('click', 640.0, 200.0, 'left', 1), ('click', 0.0, 800.0, 'left', 2),
                                 ('insert', 'abc'), ('press', 'Tab'), ('wheel', 3, -4)])

    def test_screencast_frames_are_kept_and_acknowledged(self):
        sent = []

        class Cdp:
            async def send(self, method, params):
                sent.append((method, params))

        store = login_input.FrameStore()
        jpeg = b'\xff\xd8frame\xff\xd9'
        params = {'data': base64.b64encode(jpeg).decode(), 'sessionId': 7,
                  'metadata': {'deviceWidth': 1280, 'deviceHeight': 800}}
        asyncio.run(store.on_screencast_frame(Cdp(), params))
        self.assertEqual((store.data, store.seq, store.width, store.height), (jpeg, 1, 1280, 800))
        self.assertEqual(sent, [('Page.screencastFrameAck', {'sessionId': 7})])

    def test_classify_page(self):
        self.assertEqual(login_input.classify_page('https://www.linkedin.com/login'), 'waiting')
        self.assertEqual(login_input.classify_page('https://www.linkedin.com/checkpoint/challenge/AgF'), 'two_step')
        self.assertEqual(login_input.classify_page('https://www.linkedin.com/checkpoint/challenge/x',
                                                   ['https://client-api.arkoselabs.com/fc/gc/']), 'captcha')
