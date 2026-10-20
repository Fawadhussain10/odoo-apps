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
        finally:
            await browser.close()
    print(json.dumps(results))


asyncio.run(main())
