import json
import os
import subprocess
import tempfile
from pathlib import Path

from odoo.tests import TransactionCase, tagged

FAIRAH = 'ACoAACPtKOgBJR2sjFePhHYiCFb3Il-BUTEWH4M'


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestEngineMessageTarget(TransactionCase):
    """The engine's Message-link lookup, in a real headless Chromium with the
    engine's own Python (skipped where the engine is not prepared)."""

    def test_message_link_is_found_on_open_to_work_profiles(self):
        manager = self.env['li.engine.manager']
        python, browsers = manager._engine_python(), manager._browsers_dir()
        if not python.exists() or not list(browsers.glob('chromium*')):
            self.skipTest('the LinkedIn engine is not prepared on this server')
        module = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as home:     # the same clean environment the engine runs with
            env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': home,
                   'LANG': os.environ.get('LANG', 'C.UTF-8'), 'PLAYWRIGHT_BROWSERS_PATH': str(browsers)}
            run = subprocess.run([str(python), str(module / 'tests' / 'engine_message_target_check.py'),
                                  str(module / 'engine')], capture_output=True, text=True, timeout=180, env=env)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        pages = json.loads(run.stdout.strip().splitlines()[-1])
        # the engine alone fails on profiles whose top card holds an "Open to work" or "Hiring" card
        self.assertEqual(pages['open_to_work']['engine'], 'unavailable')
        self.assertEqual(pages['open_to_work_titled']['engine'], 'unresolved')
        for key in ('open_to_work', 'open_to_work_titled', 'hiring', 'plain'):
            found = pages[key]
            self.assertEqual((found['patched'], found['patched_urn']), ('resolved', FAIRAH), key)
            self.assertEqual((found['path'], found['name']), ('/in/fairah-syed-974a36149/', 'FAIRAH SYED'), key)
        # never a guess: two people, a link naming two profiles, or no Message link stay unsent
        self.assertEqual((pages['two_people']['patched'], pages['two_people']['note']),
                         ('failed', '2 Message links in the top card'))
        self.assertEqual((pages['mixed_ids']['patched'], pages['mixed_ids']['note']),
                         ('failed', 'the Message link names no single profile'))
        for key in ('no_message', 'only_sidebar'):          # a sidebar Message link is someone else's
            self.assertEqual((pages[key]['patched'], pages[key]['patched_urn']), ('unavailable', None), key)
