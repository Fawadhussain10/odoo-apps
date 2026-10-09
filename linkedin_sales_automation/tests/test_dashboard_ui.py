from odoo.tests import HttpCase, tagged

from .common import LiCommon


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestDashboardUi(HttpCase, LiCommon):
    """The OWL client action compiles, renders its tiles and reacts to filters."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_li()
        persona = cls._make_persona('UI persona')
        persona.action_connection_run()
        prospect = cls.env['li.prospect'].create({'name': 'Ali Raza', 'persona_id': persona.id,
                                                  'linkedin_url': 'https://www.linkedin.com/in/ui-ali/',
                                                  'location': 'Lahore, Punjab, Pakistan', 'headline': 'Founder at Brand X'})
        for event_type in ('invite_sent', 'invite_accepted'):
            cls.env['li.event']._log(event_type, 'connection', persona=persona, prospect=prospect)

    def test_dashboard_renders(self):
        code = """
            (async () => {
                const wait = async (selector, test = (el) => el) => {
                    for (let i = 0; i < 150; i++) {
                        const el = document.querySelector(selector);
                        if (el && test(el)) { return el; }
                        await new Promise((r) => setTimeout(r, 100));
                    }
                    throw new Error('missing ' + selector);
                };
                try {
                    await wait('.o_li_tile');
                    const tiles = document.querySelectorAll('.o_li_tiles:not(.o_li_tiles_ops) .o_li_tile');
                    if (tiles.length !== 10) { throw new Error('expected 10 tiles, got ' + tiles.length); }
                    if (!tiles[0].innerText.includes('1')) { throw new Error('connections sent not shown'); }
                    await wait('.o_li_bar');
                    await wait('.o_li_alert');
                    // the map: one glowing spot, its popup lists the prospect
                    await wait('.o_li_map_land path');
                    const spots = document.querySelectorAll('.o_li_map_dot');
                    if (spots.length !== 1) { throw new Error('expected 1 map spot, got ' + spots.length); }
                    spots[0].dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 10, clientY: 10 }));
                    await wait('.o_li_map_person_name', (el) => el.innerText.includes('Ali Raza'));
                    document.querySelector('.o_li_map_close').click();
                    await wait('.o_li_map_tools', () => !document.querySelector('.o_li_map_popup'));
                    document.querySelector('.o_li_map_tools button').click();
                    [...document.querySelectorAll('.o_li_segment button')].find((b) => b.innerText.trim() === 'Chat').click();
                    await wait('.o_li_segment_on', () => [...document.querySelectorAll('.o_li_segment_on')].some((b) => b.innerText.trim() === 'Chat'));
                    await wait('.o_li_tiles:not(.o_li_tiles_ops) .o_li_tile_value', () => document.querySelector('.o_li_tiles:not(.o_li_tiles_ops) .o_li_tile_value').innerText.trim() === '0');
                    console.log('test successful');
                } catch (e) {
                    console.error(e.message);
                }
            })();
        """
        self.browser_js('/odoo/action-linkedin_sales_automation.action_li_dashboard', code, login='li_manager',
                        timeout=120)


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestConnectDialogUi(HttpCase, LiCommon):
    """The Connect LinkedIn dialog compiles, shows its three ways and starts a
    sign-in (fake helper, no browser on LinkedIn)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_li()
        import sys
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        here = Path(__file__).parent
        tmp = tempfile.mkdtemp(prefix='li-ui-test-')
        ready = {'prepared': True, 'ready': True, 'xvfb': False, 'missing_libs': [], 'admin_commands': [],
                 'engine_version': 't', 'python': 't', 'chrome': '/fake'}
        Manager = type(cls.env['li.engine.manager'])
        Profile = type(cls.env['li.profile'])
        cls.startClassPatcher(patch.object(Manager, '_root', lambda self: Path(tmp)))
        cls.startClassPatcher(patch.object(Manager, '_check_ready', lambda self: dict(ready)))
        cls.startClassPatcher(patch.object(Manager, '_health', lambda self: dict(ready)))

        def helper_command(self, mode, port, headless, cookies_file=None):
            return [sys.executable, str(here / 'fake_login_helper.py'), '--mode', mode, '--port', str(port),
                    '--user-data-dir', str(self._profile_dir())]
        cls.startClassPatcher(patch.object(Profile, '_login_helper_command', helper_command))
        cls.profile.write({'execution_mode': 'engine', 'owner_id': cls.manager.id})

    def tearDown(self):
        self.profile.sudo()._login_kill()
        super().tearDown()

    def test_connect_dialog(self):
        code = """
            (async () => {
                const wait = async (selector, test = (el) => el) => {
                    for (let i = 0; i < 150; i++) {
                        const el = document.querySelector(selector);
                        if (el && test(el)) { return el; }
                        await new Promise((r) => setTimeout(r, 100));
                    }
                    throw new Error('missing ' + selector);
                };
                try {
                    await wait('.o_main_navbar');
                    const env = odoo.__WOWL_DEBUG__.root.env;
                    env.services.action.doAction({type: 'ir.actions.client', tag: 'li_linkedin_connect', target: 'new',
                        name: 'Connect', params: {profile_id: %d, profile_name: 'Test', xvfb: false}});
                    const tabs = await wait('.o_li_connect .nav-tabs');
                    if (tabs.querySelectorAll('a').length !== 3) { throw new Error('expected 3 ways'); }
                    tabs.querySelectorAll('a')[1].click();
                    await wait('.o_li_connect input[type=file]');
                    tabs.querySelectorAll('a')[2].click();
                    await wait('.o_li_connect input[type=password]');
                    tabs.querySelectorAll('a')[0].click();
                    (await wait('.o_li_connect .btn-primary',
                                (el) => el.innerText.includes('Open LinkedIn sign-in') && !el.disabled)).click();
                    try {
                        await wait('.o_li_connect .alert', (el) => el.innerText.includes('Sign in to LinkedIn'));
                    } catch (e) {
                        const alert = document.querySelector('.o_li_connect .alert');
                        throw new Error('no sign-in state, dialog shows: ' + (alert ? alert.innerText : 'nothing'));
                    }
                    await wait('.o_li_connect img.o_li_screen');
                    console.log('test successful');
                } catch (e) {
                    console.error(e.message);
                }
            })();
        """ % self.profile.id
        self.browser_js('/odoo', code, login='li_manager', timeout=120)
