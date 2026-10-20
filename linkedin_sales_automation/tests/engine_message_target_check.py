"""Run by test_engine_message_target with the engine's Python: opens LinkedIn-like
profile pages in headless Chromium (served locally, no network) and prints, per
page, what the engine's own Message-link lookup and Odoo's lookup find.

Usage: python engine_message_target_check.py <engine folder>"""
import asyncio
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])

from linkedin_mcp_server.linkedin import message_sender  # noqa: E402
from patchright.async_api import async_playwright  # noqa: E402

import odoo_tools  # noqa: E402
from launch import lift_inherited_limits  # noqa: E402

lift_inherited_limits()             # Odoo's memory limit is inherited; the browser needs more, as for the engine

FAIRAH = 'ACoAACPtKOgBJR2sjFePhHYiCFb3Il-BUTEWH4M'
OTHER = 'ACoAABBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB'
URL = 'https://www.linkedin.com/in/fairah-syed-974a36149/'


def compose(urn, recipient=None):
    return ('https://www.linkedin.com/messaging/compose/?profileUrn=urn%%3Ali%%3Afsd_profile%%3A%s&recipient=%s'
            % (urn, recipient or urn))


def page(top_card, aside=True):
    side = ('<aside><section><h2>People also viewed</h2><a href="%s">Message</a></section></aside>'
            % compose(OTHER)) if aside else ''
    return ('<html><body><main><section class="wrapper">%s</section>'
            '<section><h2>About</h2><p>HR professional.</p></section></main>%s</body></html>' % (top_card, side))


NAME = '<h1>FAIRAH SYED</h1><div>Admin &amp; HR Executive | Operations | Compliance</div>'
BUTTONS = '<a href="%s">Message</a><button>More</button>' % compose(FAIRAH)
PAGES = {
    # LinkedIn today: the "Open to work" card is a section inside the top card
    'open_to_work': page('<section class="top-card">%s%s<section class="open-to-work"><h2>Open to work</h2>'
                         '<a href="#">Show details</a></section></section>' % (NAME, BUTTONS)),
    # the server's error: the card the engine looks at has two headings, so it gives up
    'open_to_work_titled': page('<section class="top-card">%s%s<section class="open-to-work"><h2>Open to work'
                                '</h2><h3>Admin roles</h3></section></section>' % (NAME, BUTTONS)),
    'hiring': page('<section class="top-card">%s%s<section><h3>Hiring: Reservations Agent</h3></section>'
                   '</section>' % (NAME, BUTTONS)),
    'plain': page('<section class="top-card">%s%s</section>' % (NAME, BUTTONS)),
    'two_people': page('<section class="top-card">%s%s<a href="%s">Message</a></section>'
                       % (NAME, BUTTONS, compose(OTHER))),
    'mixed_ids': page('<section class="top-card">%s<a href="%s">Message</a></section>'
                      % (NAME, compose(FAIRAH, OTHER))),
    'no_message': page('<section class="top-card">%s<button>Connect</button></section>' % NAME),
    'only_sidebar': page('<section class="top-card">%s<button>Follow</button></section>' % NAME, aside=True),
}


def composer(menu_items, send_button=False):
    """A message box in "Press Enter to Send" mode: the toggle opens a menu; the
    "Click Send" choice puts a Send button in place of the toggle. Submitting the
    form is recorded, so the check can prove nothing was sent."""
    toggle = '' if send_button else (
        '<span>Press Enter to Send</span>'
        '<button type="button" class="msg-form__send-toggle" aria-label="Open send options">...</button>')
    send = '<button type="submit" class="msg-form__send-button">Send</button>' if send_button else ''
    return ("""<html><body><main><form class="msg-form" onsubmit="document.body.dataset.sent = 'yes'; return false;">
        <div contenteditable="true" role="textbox"></div><footer>%s%s</footer></form>
        <div class="artdeco-dropdown__content" role="menu" style="display:none">%s</div></main>
        <script>
        const menu = document.querySelector('[role=menu]');
        const toggle = document.querySelector('.msg-form__send-toggle');
        if (toggle) toggle.addEventListener('click', () => { menu.style.display = 'block'; });
        const choose = choice => {
            menu.style.display = 'none';
            if (choice !== 'click') return;
            const footer = document.querySelector('footer');
            footer.innerHTML = '<button type="submit" class="msg-form__send-button">Send</button>';
        };
        document.querySelectorAll('[data-choice]').forEach(item => {
            if (item.tagName === 'INPUT') item.addEventListener('change', () => choose(item.dataset.choice));
            else item.addEventListener('click', () => choose(item.dataset.choice));
        });
        </script></body></html>""" % (toggle, send, menu_items))


ENTER_ITEM = ('<div role="menuitemradio" aria-checked="true" data-choice="enter">'
              '<p>Press <strong>Enter</strong> to Send</p><p>Press Enter to send, Shift+Enter for a new line</p></div>')
# What LinkedIn showed on the server: radio buttons, each covered by its label
# (a click on the button itself is intercepted by the label)
def radio(ident, value, marker, choice, text):
    return ('<div style="position:relative;height:40px">'
            '<input type="radio" id="%s" name="send-settings-send-mode-toggle-presenter-ember198" value="%s" %s '
            'data-choice="%s" style="position:absolute;left:4px;top:8px;width:16px;height:16px;margin:0">'
            '<label for="%s" style="position:absolute;inset:0;display:block;padding:8px 8px 8px 28px;'
            'background:rgba(255,255,255,0.01);z-index:2">%s</label></div>' % (ident, value, marker, choice, ident, text))


LINKEDIN_RADIOS = (radio('enter-send-mode-toggle-presenter-ember198', 'enter',
                         'data-test-msg-ui-send-mode-toggle-presenter__enter-to-send-input checked', 'enter',
                         '<p>Press <strong>Enter</strong> to Send</p>')
                   + radio('send-send-mode-toggle-presenter-ember198', 'send',
                           'data-test-msg-ui-send-mode-toggle-presenter__click-to-send-input', 'click',
                           '<p>Click <strong>Send</strong></p>'))
COMPOSERS = {
    'linkedin_radios': composer(LINKEDIN_RADIOS),
    'menu_click_send': composer(ENTER_ITEM + '<div role="menuitemradio" aria-checked="false" data-choice="click">'
                                '<p>Click <strong>Send</strong></p><p>Click Send to send, Enter for a new line</p>'
                                '</div>'),
    'plain_click_send_to_send': composer('<div data-choice="enter">Press Enter to Send</div>'
                                         '<div data-choice="click">Click Send to send</div>'),
    'no_click_option': composer(ENTER_ITEM + '<div data-choice="other">Messaging settings</div>'),
    'already_click_send': composer('', send_button=True),
}


def server(html):
    async def serve(route, *_request):
        await route.fulfill(status=200, content_type='text/html', body=html)
    return serve


async def main():
    odoo_tools.install_message_target_fix()
    results = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for key, html in PAGES.items():
                tab = await browser.new_page()
                await tab.route('https://www.linkedin.com/**', server(html))
                await tab.goto(URL)
                engine = await tab.evaluate(message_sender._PROFILE_MESSAGE_TARGET_JS)
                odoo = await tab.evaluate(odoo_tools.MESSAGE_TARGET_JS)
                target = odoo_tools.message_target(odoo, message_sender)
                # the patched engine method on this page, as send_message calls it
                sender = message_sender.MessageSender(SimpleNamespace(page=tab), None)
                resolution = await sender._read_profile_message_target(timeout_ms=200)
                results[key] = {
                    'engine': engine.get('status'),
                    'odoo': odoo.get('status'),
                    'why': odoo.get('why', ''),
                    'urn': target.profile_urn if target else None,
                    'path': target.profile_path if target else None,
                    'name': target.display_name if target else None,
                    'patched': resolution.status,
                    'patched_urn': resolution.target.profile_urn if resolution.target else None,
                    'note': getattr(sender, '_odoo_target_note', ''),
                }
                await tab.close()
            # switching "Press Enter to Send" off: never sends anything
            for key, html in COMPOSERS.items():
                tab = await browser.new_page()
                await tab.route('https://www.linkedin.com/**', server(html))
                await tab.goto('https://www.linkedin.com/messaging/compose/')
                switched = await odoo_tools.switch_send_mode(tab, wait=3)
                results['send_mode_' + key] = {'status': switched['status'], 'message': switched['message'],
                                               'sent': await tab.evaluate("document.body.dataset.sent || 'no'")}
                await tab.close()
        finally:
            await browser.close()
    print(json.dumps(results))


asyncio.run(main())
