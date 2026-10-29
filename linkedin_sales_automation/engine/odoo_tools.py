"""Extra engine tools Odoo needs, registered on the engine's own MCP server
(see runner.py), so they run on the same browser session and one at a time
with the engine's tools.

* create_post     - publish a post (text, optional image) on the signed-in account
* get_post_stats  - read a published post's page (reactions, comments, reposts)
* follow_person   - follow someone LinkedIn offers no Connect for (top card or More menu)
* get_recent_connections - the newest 1st-degree connections, one page read
* check_invite_dialog - open one person's invite dialog WITHOUT sending and say
  what LinkedIn asks there (e.g. the person's email address)
* send_invite_direct - send an invitation by every route LinkedIn offers (invite
  link, Connect button, Connect in the "More" menu), for profiles where the
  engine finds no Connect or misreads the buttons
* get_sent_invitations - LinkedIn's own list of invitations that are pending
  (My Network > Manage > Sent): the authority on whether an invite exists
* check_connection_state - open one person's profile and say what it shows now:
  pending (invited), connectable (Connect is offered: not invited), connected
* lookup_location - LinkedIn's own location suggestions for a place name (what
  its "Locations" filter offers), with the numeric location ids
* search_people_filtered - a people search with LinkedIn's real filters
  (location ids, title, connection degree, page) or a search URL built on LinkedIn

install_invite_notices() also makes connect_with_person report what LinkedIn
says in its pop-up when an invitation is not recorded (e.g. the weekly limit).

They follow the engine's conventions: auth errors go through its own
handle_auth_error, other errors through raise_tool_error.
"""
import asyncio
import logging
import os
import re
from typing import Any
from urllib.parse import quote

from fastmcp import Context, FastMCP

from linkedin_mcp_server.core.exceptions import AuthenticationError
from linkedin_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from linkedin_mcp_server.error_handler import raise_tool_error
from linkedin_mcp_server.linkedin.navigation import PageNavigator

logger = logging.getLogger(__name__)

FEED_URL = 'https://www.linkedin.com/feed/'
SHARE_URL = 'https://www.linkedin.com/feed/?shareActive=true'
POST_LINK = re.compile(r'/feed/update/(urn:li:(?:activity|share|ugcPost):\d+)')
MAX_POST_CHARS = 3000
CONNECTIONS_URL = 'https://www.linkedin.com/mynetwork/invite-connect/connections/'
SENT_INVITATIONS_URL = 'https://www.linkedin.com/mynetwork/invitation-manager/sent/'
MAX_SENT_INVITATIONS = 500
MAX_CONNECTIONS = 80


def _session_of(extractor):
    return extractor._content._session


async def _first_visible(page, selectors, timeout=10000):
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    while asyncio.get_running_loop().time() < deadline:
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                count = 0
            for index in range(count):
                item = locator.nth(index)
                try:
                    if await item.is_visible():
                        return item
                except Exception:
                    continue
        await asyncio.sleep(0.3)
    return None


def _result(status, message, retry_safe, **extra):
    return dict({'status': status, 'message': message, 'retry_safe': retry_safe}, **extra)


PEOPLE_SEARCH_URL = 'https://www.linkedin.com/search/results/people/'
MAX_SEARCH_PAGE = 100
# LinkedIn's location suggestions, as its "Locations" filter asks for them. Runs
# in the signed-in page: the csrf token is the JSESSIONID cookie, as for
# LinkedIn's own requests. Every object holding a geo urn and a text is a candidate.
LOCATION_LOOKUP_JS = """async (query) => {
    const match = document.cookie.match(/JSESSIONID="?([^";]+)/);
    const csrf = match ? match[1] : '';
    const url = '/voyager/api/typeahead/hitsV2?keywords=' + encodeURIComponent(query)
        + '&origin=OTHER&q=type&queryContext=List(geoVersion-%3E3,bingGeoSubTypeFilters-%3E'
        + 'MARKET_AREA%7CCOUNTRY_REGION%7CADMIN_DIVISION_1%7CCITY)&type=GEO';
    let response;
    try {
        response = await fetch(url, {credentials: 'include', headers: {
            'csrf-token': csrf, 'accept': 'application/json', 'x-restli-protocol-version': '2.0.0'}});
    } catch (e) {
        return {http: 0, error: String(e), candidates: []};
    }
    if (!response.ok) { return {http: response.status, candidates: []}; }
    const data = await response.json();
    const found = [];
    const textOf = (node) => {
        for (const key of ['text', 'title', 'displayName', 'defaultLocalizedName']) {
            const value = node[key];
            if (typeof value === 'string' && value.trim()) { return value.trim(); }
            if (value && typeof value.text === 'string' && value.text.trim()) { return value.text.trim(); }
        }
        return '';
    };
    const walk = (node) => {
        if (!node || typeof node !== 'object') { return; }
        if (Array.isArray(node)) { node.forEach(walk); return; }
        let id = null;
        for (const value of Object.values(node)) {
            if (typeof value === 'string') {
                const m = value.match(/urn:li:(?:fs_|fsd_)?geo:(\\d+)/);
                if (m) { id = m[1]; break; }
            }
        }
        const name = textOf(node);
        if (id && name) { found.push({id, name}); }
        Object.values(node).forEach(walk);
    };
    walk(data);
    const seen = new Set();
    return {http: response.status, candidates: found.filter((c) => !seen.has(c.id) && seen.add(c.id))};
}"""


def people_search_url(keywords='', geo_ids=None, title='', network=None, page=1, url=None):
    """A LinkedIn people search URL with LinkedIn's own filters (geoUrn is the
    "Locations" filter; a plain location word is ignored by LinkedIn). `url` is a
    search built on LinkedIn: only its page changes."""
    page = max(1, min(int(page or 1), MAX_SEARCH_PAGE))
    if url:
        base = re.sub(r'([?&])page=\d+&?', r'\1', url.strip()).rstrip('?&')
        return '%s%spage=%s' % (base, '&' if '?' in base else '?', page)

    def facet(values):
        return quote('[%s]' % ','.join('"%s"' % v for v in values), safe='')

    params = ['keywords=%s' % quote(keywords or '', safe='')]
    if geo_ids:
        params.append('geoUrn=%s' % facet(geo_ids))
    if title:
        params.append('titleFreeText=%s' % quote(title, safe=''))
    if network:
        params.append('network=%s' % facet(network))
    params += ['origin=FACETED_SEARCH', 'page=%s' % page]
    return '%s?%s' % (PEOPLE_SEARCH_URL, '&'.join(params))


async def lookup_location_flow(extractor, query):
    session = _session_of(extractor)
    page = session.page
    if 'linkedin.com' not in (page.url or ''):
        await PageNavigator(session)._navigate_to_page(FEED_URL)
        await session.check_rate_limit()
    answer = await page.evaluate(LOCATION_LOOKUP_JS, query)
    candidates = answer.get('candidates') or []
    if not candidates:
        return {'status': 'not_found' if answer.get('http') == 200 else 'unavailable', 'query': query,
                'http': answer.get('http'), 'error': answer.get('error', ''), 'candidates': []}
    return {'status': 'ok', 'query': query, 'candidates': candidates[:10]}


async def filtered_search_flow(extractor, url):
    """The engine's own search (same page reading and result format as
    search_people), on a URL with LinkedIn's real filters."""
    from linkedin_mcp_server.linkedin import person as person_module
    original = person_module.build_people_search_url
    person_module.build_people_search_url = lambda *args, **kwargs: url
    try:
        return await extractor.search_people('filtered')
    finally:
        person_module.build_people_search_url = original


async def create_post_flow(extractor, text, image_path=None):
    """Open the share box, type the text, attach the image, press Post and read
    the new post's address. retry_safe is False from the moment Post is pressed."""
    session = _session_of(extractor)
    page = session.page
    navigator = PageNavigator(session)
    await navigator._navigate_to_page(SHARE_URL)
    await session.check_rate_limit()
    dialog = await _first_visible(page, ['div[role="dialog"]:has([contenteditable="true"])'], timeout=8000)
    if dialog is None:
        await navigator._navigate_to_page(FEED_URL)
        start = await _first_visible(page, ['button:has-text("Start a post")', '[aria-label*="Start a post"]'])
        if start is None:
            return _result('composer_unavailable', 'LinkedIn did not show the "Start a post" box.', True)
        await start.click()
        dialog = await _first_visible(page, ['div[role="dialog"]:has([contenteditable="true"])'])
    if dialog is None:
        return _result('composer_unavailable', 'The post editor did not open.', True)
    editor = dialog.locator('[contenteditable="true"]').first
    await editor.click()
    for index, paragraph in enumerate(text.split('\n')):
        if index:
            await page.keyboard.press('Enter')
        if paragraph:
            await page.keyboard.insert_text(paragraph)
    if image_path:
        media = await _first_visible(page, ['div[role="dialog"] button[aria-label*="Add media"]',
                                            'div[role="dialog"] button[aria-label*="Add a photo"]',
                                            'div[role="dialog"] button[aria-label*="photo"]'], timeout=5000)
        if media is None:
            return _result('image_unavailable', 'LinkedIn did not offer to add a photo.', True)
        async with page.expect_file_chooser(timeout=10000) as chooser_info:
            await media.click()
        chooser = await chooser_info.value
        await chooser.set_files(image_path)
        for label in ('Next', 'Done'):
            button = await _first_visible(page, ['div[role="dialog"] button:has-text("%s")' % label], timeout=15000)
            if button is not None and await button.is_enabled():
                await button.click()
                break
    post = await _first_visible(page, ['div[role="dialog"] button.share-actions__primary-action',
                                       'div[role="dialog"] button:text-is("Post")'], timeout=15000)
    if post is None:
        return _result('post_button_missing', 'The Post button did not appear.', True)
    for _i in range(20):
        if await post.is_enabled():
            break
        await asyncio.sleep(0.5)
    else:
        return _result('post_button_disabled', 'The Post button stayed disabled (text or image refused).', True)
    await post.click()
    # From here the post may be on LinkedIn: never report retry_safe true again.
    url = None
    for _i in range(40):
        for link in await page.locator('a[href*="/feed/update/urn:li:"]').all():
            try:
                href = await link.get_attribute('href') or ''
            except Exception:
                continue
            match = POST_LINK.search(href)
            if match:
                url = 'https://www.linkedin.com/feed/update/%s/' % match.group(1)
                break
        if url:
            break
        await asyncio.sleep(0.5)
    if url:
        return _result('published', 'Post published.', False, post_url=url, published=True)
    dialog_open = await _first_visible(page, ['div[role="dialog"]:has([contenteditable="true"])'], timeout=1000)
    if dialog_open is None:
        return _result('published_no_url', 'The editor closed after Post, but LinkedIn showed no link to the '
                       'post.', False, published=True)
    return _result('outcome_unknown', 'Post was pressed but LinkedIn did not confirm.', False)


async def post_stats_flow(extractor, post_url):
    session = _session_of(extractor)
    navigator = PageNavigator(session)
    await navigator._navigate_to_page(post_url)
    await session.check_rate_limit()
    await asyncio.sleep(2)
    text = await extractor.get_page_text()
    return {'url': post_url, 'sections': {'post': text or ''}}


# Follow state of the profile's own top card (the first section of the profile),
# never the "People also viewed" or company Follow buttons further down.
FOLLOW_STATE_JS = """(clickFollow) => {
    const root = document.querySelector('main section');
    const scopes = [root, ...document.querySelectorAll('[role="menu"]')].filter(Boolean);
    const label = (b) => ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).trim().toLowerCase();
    const visible = (b) => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
    const items = scopes.flatMap((s) => [...s.querySelectorAll('button, [role="menuitem"], [role="button"]')]);
    const following = items.some((b) => visible(b) && /^(following|unfollow)\\b/.test(label(b)));
    const follow = items.find((b) => visible(b) && /^\\+?\\s*follow\\b/.test(label(b)) && !/^following/.test(label(b)));
    if (clickFollow && follow && !following) { follow.click(); return {following, follow: true, clicked: true}; }
    return {following, follow: !!follow, clicked: false};
}"""


async def follow_flow(extractor, username):
    """Follow a person from their profile. Never clicks when already following
    (a second click would unfollow), so a repeat is always safe."""
    session = _session_of(extractor)
    page = session.page
    await PageNavigator(session)._navigate_to_page('https://www.linkedin.com/in/%s/' % quote(username))
    await session.check_rate_limit()
    await asyncio.sleep(1.5)
    state = await page.evaluate(FOLLOW_STATE_JS, False)
    if state['following']:
        return _result('already_following', 'Already following.', True)
    if not state['follow']:
        opened = await extractor._connection._open_more_menu()
        state = await page.evaluate(FOLLOW_STATE_JS, False) if opened else state
        if state['following']:
            return _result('already_following', 'Already following.', True)
        if not state['follow']:
            return _result('follow_unavailable', 'LinkedIn shows no Follow action for this profile.', True)
    clicked = await page.evaluate(FOLLOW_STATE_JS, True)
    if not clicked['clicked']:
        return _result('follow_unavailable', 'The Follow action could not be clicked.', True)
    for _i in range(10):
        await asyncio.sleep(0.5)
        if (await page.evaluate(FOLLOW_STATE_JS, False))['following']:
            return _result('followed', 'Now following.', True)
    try:
        await page.keyboard.press('Escape')
    except Exception:
        pass
    await PageNavigator(session)._navigate_to_page('https://www.linkedin.com/in/%s/' % quote(username))
    await asyncio.sleep(1.5)
    if (await page.evaluate(FOLLOW_STATE_JS, False))['following']:
        return _result('followed', 'Now following.', True)
    return _result('follow_unconfirmed', 'Follow was clicked but LinkedIn did not show Following.', True)


# Profile links of the connection cards in page order (the page lists the most
# recently added first); usernames only, de-duplicated.
CONNECTION_LINKS_JS = """() => {
    const seen = [];
    const root = document.querySelector('main') || document;
    for (const a of root.querySelectorAll('a[href*="/in/"]')) {
        const m = (a.getAttribute('href') || '').match(/\\/in\\/([^/?#]+)/);
        if (m && !seen.includes(m[1])) { seen.push(m[1]); }
    }
    return seen;
}"""


async def recent_connections_flow(extractor, limit):
    """Open My Network > Connections (sorted by Recently added) and return the
    usernames of the newest connections, scrolling until `limit` are loaded."""
    session = _session_of(extractor)
    page = session.page
    await PageNavigator(session)._navigate_to_page(CONNECTIONS_URL)
    await session.check_rate_limit()
    await asyncio.sleep(2)
    usernames = await page.evaluate(CONNECTION_LINKS_JS)
    for _i in range(4):
        if len(usernames) >= limit:
            break
        await page.mouse.wheel(0, 4000)
        await asyncio.sleep(1.5)
        more = await page.evaluate(CONNECTION_LINKS_JS)
        if len(more) <= len(usernames):
            break
        usernames = more
    return {'url': CONNECTIONS_URL, 'usernames': usernames[:limit], 'count': min(len(usernames), limit)}


# What the invite dialog asks, read without touching it. An email field means
# LinkedIn only lets people who know this member's address invite them.
INVITE_DIALOG_JS = """() => {
    const dialog = [...document.querySelectorAll('dialog[open], [role="dialog"]')]
        .find((d) => !d.closest('[class*="msg-overlay"]'));
    if (!dialog) { return {open: false, email: false, text: ''}; }
    const email = !!dialog.querySelector('input[type="email"], input[name*="email" i], input[id*="email" i]');
    return {open: true, email, text: (dialog.innerText || '').trim().slice(0, 1500)};
}"""


async def invite_dialog_flow(extractor, username):
    """Open the invite dialog of one person, read it and close it. Never sends."""
    session = _session_of(extractor)
    page = session.page
    await PageNavigator(session)._navigate_to_page(
        'https://www.linkedin.com/preload/custom-invite/?vanityName=%s' % quote(username))
    await session.check_rate_limit()
    info = {'open': False, 'email': False, 'text': ''}
    for _i in range(8):
        await asyncio.sleep(0.5)
        info = await page.evaluate(INVITE_DIALOG_JS)
        if info['open']:
            break
    try:
        await extractor._connection._dismiss_dialog()
    except Exception:
        try:
            await page.keyboard.press('Escape')
        except Exception:
            pass
    status = 'email_required' if info['email'] else 'dialog' if info['open'] else 'no_dialog'
    return {'status': status, 'text': info['text'], 'retry_safe': True}


# LinkedIn's pop-up notices (bottom-left "toast"), e.g. "Your invitation was not
# sent because you have reached the weekly limit for connection invitations".
NOTICE_JS = """() => {
    const seen = [];
    const nodes = document.querySelectorAll(
        '[role="alert"], [role="status"], [aria-live="assertive"], .artdeco-toast-item, [class*="toast"]');
    for (const node of nodes) {
        if (!(node.offsetWidth || node.offsetHeight || node.getClientRects().length)) { continue; }
        const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
        // LinkedIn's own counters and status lines are not messages about this action
        if (/^\\d+ (new )?notifications?( total)?$|^status is (online|offline)|^\\d+ unread/i.test(text)) { continue; }
        if (text.length > 8 && !seen.some((t) => t.includes(text) || text.includes(t))) { seen.push(text); }
    }
    return seen.join(' | ').slice(0, 400);
}"""


async def read_notice(page, seconds=4.0):
    """The notice LinkedIn shows right after an action, or '' when none appears."""
    for _i in range(int(seconds / 0.5)):
        try:
            text = await page.evaluate(NOTICE_JS)
        except Exception:
            text = ''
        if text:
            return text
        await asyncio.sleep(0.5)
    return ''


# "Show more" / "Load more" at the end of a list (the engine keeps LinkedIn in English).
# Bring the end of a list into view (window and any scrolling box around it) and
# press its "Show more" / "Load more" control, whatever element it is.
MORE_BUTTON_JS = """() => {
    const root = document.querySelector('main') || document;
    const links = [...root.querySelectorAll('a[href*="/in/"]')];
    const last = links[links.length - 1];
    if (last) {
        last.scrollIntoView({block: 'end'});
        for (let el = last.parentElement; el; el = el.parentElement) {
            if (el.scrollHeight > el.clientHeight + 20) { el.scrollTop = el.scrollHeight; }
        }
    }
    window.scrollTo(0, document.documentElement.scrollHeight);
    const label = (b) => ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).trim();
    const button = [...document.querySelectorAll('button, [role="button"], a')].find((b) =>
        /^(show|load|see) more( results| people| invitations)?\\b/i.test(label(b))
        && !/options|actions|profiles for you/i.test(label(b)) && (b.offsetWidth || b.offsetHeight));
    if (button) { button.click(); return true; }
    return false;
}"""
MAIN_TEXT_JS = """() => ((document.querySelector('main') || document.body).innerText || '').trim().slice(0, 900)"""
# "People (23)" on the Sent invitations page: how many there are in all.
SENT_TOTAL = re.compile(r'People\s*\(?\s*(\d{1,4})\s*\)?', re.I)


# The people of the invitation rows only: every pending invitation has a
# "Withdraw" control, and the row around it links to exactly one person.
# Suggested people elsewhere on the page have no such control.
SENT_ROWS_JS = """() => {
    const root = document.querySelector('main') || document;
    const label = (b) => ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).trim();
    const person = (a) => ((a.getAttribute('href') || '').match(/\\/in\\/([^/?#]+)/) || [])[1];
    const buttons = [...root.querySelectorAll('button, [role="button"], a')]
        .filter((b) => /^withdraw\\b/i.test(label(b)));
    const seen = [];
    for (const button of buttons) {
        for (let el = button.parentElement; el && el !== root.parentElement; el = el.parentElement) {
            const names = [...new Set([...el.querySelectorAll('a[href*="/in/"]')].map(person).filter(Boolean))];
            if (!names.length) { continue; }
            if (names.length === 1 && !seen.includes(names[0])) { seen.push(names[0]); }
            break;                              // a box holding several people is past the row
        }
    }
    return {rows: buttons.length, usernames: seen};
}"""


async def _sent_people(page):
    """(usernames, rows_only): from the invitation rows when the page has any,
    else every profile link on the page (then nothing can be proven from it)."""
    try:
        found = await page.evaluate(SENT_ROWS_JS)
    except Exception:
        found = {'rows': 0, 'usernames': []}
    if found.get('rows'):
        return found.get('usernames') or [], True
    return await page.evaluate(CONNECTION_LINKS_JS), False


async def sent_invitations_flow(extractor, limit):
    """Open the Sent invitations page and return the usernames listed there,
    loading the whole list (scroll and "Show more") up to `limit`."""
    session = _session_of(extractor)
    page = session.page
    await PageNavigator(session)._navigate_to_page(SENT_INVITATIONS_URL)
    await session.check_rate_limit()
    await asyncio.sleep(2.5)
    usernames, rows_only = await _sent_people(page)
    page_text = await page.evaluate(MAIN_TEXT_JS)
    complete, stalls = False, 0
    for _i in range(60):
        if len(usernames) >= limit:
            break
        clicked = await page.evaluate(MORE_BUTTON_JS)
        await page.mouse.wheel(0, 6000)
        await asyncio.sleep(2.0 if clicked else 1.3)
        more, rows_only = await _sent_people(page)
        if len(more) > len(usernames):
            usernames, stalls = more, 0
            continue
        stalls += 1
        if stalls >= 3:
            complete = True                     # three rounds without a new name: nothing more loads
            break
    match = SENT_TOTAL.search(page_text or '')
    return {'url': SENT_INVITATIONS_URL, 'usernames': usernames[:limit], 'count': min(len(usernames), limit),
            'complete': complete, 'total': int(match.group(1)) if match else 0, 'page_text': page_text,
            'rows_only': rows_only}


SENT_NOTICE = re.compile(r'invitation sent|invite sent|request sent', re.I)
REFUSAL_NOTICE = re.compile(r'not sent|was(n.t| not) sent|weekly limit|limit for connection invitations|'
                            r'invitation limit|too many (pending )?invitations|unable to (send|connect)', re.I)


# Find a visible Connect control: on the top card of the profile (the section
# that holds the person's name), or inside the open "More" menu, and mark it so
# it can be pressed with a real mouse click. "500+ connections" and "Remove
# connection" never match.
CONNECT_CLICK_JS = """(inMenu) => {
    const label = (b) => ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).trim().toLowerCase();
    const visible = (b) => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
    const name = document.querySelector('main h1');
    const card = (name && name.closest('section')) || document.querySelector('main section');
    const scopes = inMenu
        ? [...document.querySelectorAll('[role="menu"], .artdeco-dropdown__content')]
        : [card].filter(Boolean);
    const items = scopes.flatMap((s) => [...s.querySelectorAll('button, a, [role="menuitem"], [role="button"]')]);
    let hit = items.find((b) => visible(b)
        && /(^|\\s)connect(\\s|$)|invite .{1,80} to connect/.test(label(b))
        && !/disconnect|remove connection/.test(label(b)));
    if (!hit && name) {
        // LinkedIn changes its page structure: anywhere on the page, the control that names THIS
        // person ("Invite <name> to connect"). Other people's Connect buttons name someone else.
        const who = (name.innerText || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        if (who.length > 2) {
            hit = [...document.querySelectorAll('button, a, [role="menuitem"], [role="button"]')]
                .find((b) => visible(b) && label(b).replace(/\\s+/g, ' ').includes('invite ' + who + ' to connect'));
        }
    }
    document.querySelectorAll('[data-odoo-connect]').forEach((b) => b.removeAttribute('data-odoo-connect'));
    if (hit) { hit.setAttribute('data-odoo-connect', '1'); return true; }
    return false;
}"""


async def _press_connect(page, in_menu):
    """Press the Connect control like a person does (scrolled into view, a real
    click); a scripted click only when that is not possible. False: none found."""
    if not await page.evaluate(CONNECT_CLICK_JS, in_menu):
        return False
    try:
        await page.locator('[data-odoo-connect="1"]').first.click(timeout=4000)
    except Exception:
        try:
            await page.evaluate("""() => { const b = document.querySelector('[data-odoo-connect="1"]');
                                           if (b) { b.click(); } }""")
        except Exception:
            return False
    return True


# The top card of the profile now shows "Pending": an invitation is outstanding.
PENDING_SHOWN_JS = """() => {
    const root = document.querySelector('main section');
    if (!root) { return false; }
    const label = (b) => ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).trim().toLowerCase();
    const visible = (b) => !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
    return [...root.querySelectorAll('button, a, [role="button"]')]
        .some((b) => visible(b) && /(^|\\s)pending(\\W|$)/.test(label(b)));
}"""


async def send_invite_direct_flow(extractor, username, note):
    """Send an invitation by every route LinkedIn offers, in turn: its invite
    link, the Connect button on the profile, and Connect inside the "More"
    menu (where it sits when Follow is the main button). The dialog is
    submitted with the engine's own handling. What LinkedIn shows (dialog,
    pop-up) decides the answer; Odoo still verifies it against the Sent list.
    When Connect was pressed but nothing shows what LinkedIn did, the answer is
    maybe_sent: Odoo then reads the Sent list before it does anything else."""
    session = _session_of(extractor)
    page = session.page
    actions = extractor._connection
    navigator = PageNavigator(session)
    url = 'https://www.linkedin.com/in/%s/' % quote(username)
    pressed = []                                # routes where Connect was pressed without a visible result

    async def submit(route):
        """Submit the open dialog; None when no dialog opened on this route."""
        submitted, note_sent, limit_message = await actions._submit_invite_dialog(note)
        notice = getattr(actions, '_odoo_notice', '') or ''
        dialog = getattr(actions, '_odoo_dialog', None) or {}
        answer = {'url': url, 'note_sent': bool(note_sent), 'linkedin_notice': notice, 'route': route,
                  'invite_dialog': (dialog.get('text') or '')[:400], 'confirmed': bool(SENT_NOTICE.search(notice)),
                  'direct': True}
        if limit_message is not None:
            return dict(answer, status='custom_note_limit_reached', message=limit_message)
        if REFUSAL_NOTICE.search(notice):
            return dict(answer, status='send_failed',
                        message='LinkedIn did not send the invitation. LinkedIn says: %s' % notice)
        if dialog.get('email') and not answer['confirmed']:
            return dict(answer, status='connect_unavailable',
                        message='LinkedIn asks for this member\'s email address to connect.')
        if not submitted:
            return None
        if not dialog.get('open'):
            # submitted, but the dialog could not be read beforehand: nothing proves what was sent
            return dict(answer, status='maybe_sent',
                        message='The invite dialog was submitted (%s) but could not be read: check the Sent '
                                'list.' % route)
        return dict(answer, status='connected',
                    message='Invitation submitted (%s).%s' % (route, ' LinkedIn confirmed it.' if answer['confirmed']
                                                              else ' LinkedIn showed no confirmation.'))

    async def sent_without_dialog(route):
        """Some profiles send on the click itself: LinkedIn then only shows its pop-up."""
        notice = await read_notice(page, 3.0)
        if REFUSAL_NOTICE.search(notice):
            return {'url': url, 'status': 'send_failed', 'route': route, 'linkedin_notice': notice,
                    'confirmed': False, 'direct': True, 'note_sent': False, 'invite_dialog': '',
                    'message': 'LinkedIn did not send the invitation. LinkedIn says: %s' % notice}
        if SENT_NOTICE.search(notice):
            return {'url': url, 'status': 'connected', 'route': route, 'linkedin_notice': notice,
                    'confirmed': True, 'direct': True, 'note_sent': False, 'invite_dialog': '',
                    'message': 'Invitation sent on the click (%s). LinkedIn confirmed it.' % route}
        try:
            pending = await page.evaluate(PENDING_SHOWN_JS)
        except Exception:
            pending = False
        if pending:
            return {'url': url, 'status': 'connected', 'route': route, 'linkedin_notice': notice,
                    'confirmed': False, 'page_pending': True, 'direct': True, 'note_sent': False,
                    'invite_dialog': '',
                    'message': 'Invitation sent on the click (%s): the profile now shows Pending.' % route}
        pressed.append(route)
        return None

    async def settle(route):
        """Wait until the page has finished loading its scripts (a button pressed
        before that does nothing), press Connect and watch what LinkedIn does:
        an invite dialog (submitted as usual), its "Invitation sent" pop-up or
        the button turning into "Pending" (many profiles send on the click
        itself, without any dialog), or a refusal. Connect still there and
        nothing happened: pressed once more."""
        in_menu = route == 'More menu'
        did_press = False
        for _attempt in range(2):
            if not await _press_connect(page, in_menu):
                break
            did_press = True
            for _i in range(15):                # up to 6 seconds
                await asyncio.sleep(0.4)
                try:
                    dialog = await page.evaluate(INVITE_DIALOG_JS)
                    notice = await page.evaluate(NOTICE_JS)
                    pending = await page.evaluate(PENDING_SHOWN_JS)
                except Exception:
                    continue
                if dialog.get('open'):
                    return await submit(route) or await sent_without_dialog(route)
                if REFUSAL_NOTICE.search(notice or ''):
                    return {'url': url, 'status': 'send_failed', 'route': route, 'linkedin_notice': notice,
                            'confirmed': False, 'direct': True, 'note_sent': False, 'invite_dialog': '',
                            'message': 'LinkedIn did not send the invitation. LinkedIn says: %s' % notice}
                if SENT_NOTICE.search(notice or '') or pending:
                    return {'url': url, 'status': 'connected', 'route': route, 'linkedin_notice': notice or '',
                            'confirmed': bool(SENT_NOTICE.search(notice or '')), 'page_pending': bool(pending),
                            'direct': True, 'note_sent': False, 'invite_dialog': '',
                            'message': 'Invitation sent on the click (%s): %s.' % (
                                route, 'LinkedIn confirmed it' if SENT_NOTICE.search(notice or '')
                                else 'the profile now shows Pending')}
            if in_menu:                         # the menu closed with the click: open it for the second try
                try:
                    if not await actions._open_more_menu():
                        break
                except Exception:
                    break
            else:
                await asyncio.sleep(2.0)
        if did_press:
            pressed.append(route)               # pressed, and nothing shows what LinkedIn did
        return None

    async def loaded():
        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(2.0)

    # 1. LinkedIn's invite link
    await navigator._navigate_to_page(
        'https://www.linkedin.com/preload/custom-invite/?vanityName=%s' % quote(username))
    await session.check_rate_limit()
    answer = await submit('invite link')
    if answer:
        return answer
    # 2. the Connect button on the profile itself
    await navigator._navigate_to_page(url)
    await session.check_rate_limit()
    await loaded()
    answer = await settle('Connect button')
    if answer:
        return answer
    # 3. Connect inside the "More" menu
    try:
        opened = await actions._open_more_menu()
    except Exception:
        opened = False
    if opened:
        answer = await settle('More menu')
        if answer:
            return answer
    try:
        await page.keyboard.press('Escape')
    except Exception:
        pass
    if pressed:
        return {'url': url, 'status': 'maybe_sent', 'route': ', '.join(pressed), 'direct': True, 'note_sent': False,
                'linkedin_notice': '', 'invite_dialog': '', 'confirmed': False,
                'message': 'Connect was pressed (%s) but LinkedIn showed neither a dialog nor a confirmation: '
                           'check the Sent list.' % ', '.join(pressed)}
    return {'url': url, 'status': 'connect_unavailable', 'route': '', 'direct': True, 'note_sent': False,
            'linkedin_notice': '', 'invite_dialog': '', 'confirmed': False,
            'message': 'LinkedIn offers no Connect for this profile: not by its invite link, not on the profile, '
                       'not in the More menu.'}


async def connection_state_flow(extractor, username):
    """Open the profile and read its action area with the engine's own detection.
    Read twice a few seconds apart: right after loading, LinkedIn can still be
    drawing the buttons."""
    from linkedin_mcp_server.linkedin import connection
    actions = extractor._connection
    profile = await actions._read_main_profile(username)
    top_text = ((profile or {}).get('sections') or {}).get('main_profile', '')[:1500]
    await _session_of(extractor).check_rate_limit()
    states = []
    for _i in range(2):
        await asyncio.sleep(2.5)
        states.append(connection.detect_connection_state(await actions._read_action_signals(username)))
    state = states[-1]
    if 'connectable' in states:
        state = 'connectable'                   # Connect was offered at some point: not invited
    return {'status': state, 'seen': states, 'top_text': top_text, 'retry_safe': True}


# LinkedIn's "Press Enter to Send" preference hides the composer's Send button,
# which the engine's send_message needs. The send-options toggle next to the
# composer opens a menu with "Press Enter to Send" / "Click Send to send".
SEND_TOGGLE = ('.msg-form__send-toggle', 'button[aria-label*="send options" i]',
               'button[aria-label*="Open send" i]')
SEND_BUTTON = ('form.msg-form button.msg-form__send-button', 'form.msg-form button[type="submit"]')
# LinkedIn words the option "Click Send", "Click Send to send" or "Click send button
# to send": anything that starts with "Click" and names Send, never "Press Enter".
CLICK_SEND_OPTION = re.compile(r'^\s*click\b.{0,20}\bsend\b', re.I | re.S)
MESSAGING_URL = 'https://www.linkedin.com/messaging/'
# What a send-options menu shows once open (for the error when no option matched)
SEND_MENU_JS = """() => {
    const visible = e => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
    const menus = Array.from(document.querySelectorAll(
        '[role="menu"], [role="listbox"], [role="dialog"], .artdeco-dropdown__content, .msg-form__send-options'))
        .filter(visible);
    return menus.map(m => (m.innerText || '').replace(/\\s+/g, ' ').trim()).filter(Boolean).join(' || ').slice(0, 400);
}"""


async def _visible(page, selectors):
    for selector in selectors:
        locator = page.locator(selector)
        try:
            for index in range(await locator.count()):
                if await locator.nth(index).is_visible():
                    return locator.nth(index)
        except Exception:
            continue
    return None


# LinkedIn's own marker on the "Click Send" radio button of the send-options menu
CLICK_SEND_INPUT = '[data-test-msg-ui-send-mode-toggle-presenter__click-to-send-input]'


async def _click_send_option(page):
    """The "Click Send" choice of an open send-options menu: LinkedIn's marked
    radio button, else a menu item, radio or option named so, else the smallest
    visible element with that text."""
    marked = page.locator(CLICK_SEND_INPUT)
    try:
        if await marked.count():
            return marked.first
    except Exception:
        pass
    for role in ('menuitemradio', 'menuitem', 'radio', 'option'):
        found = await _first_matching(page.get_by_role(role, name=CLICK_SEND_OPTION))
        if found:
            return found
    return await _first_matching(page.get_by_text(CLICK_SEND_OPTION))


async def _first_matching(locator):
    try:
        for index in range(await locator.count()):
            item = locator.nth(index)
            if await item.is_visible():
                return item
    except Exception:
        return None
    return None


async def _choose(page, option):
    """Choose the option as a person does. A radio button is chosen through its
    label: LinkedIn draws the label over the button, so a click on the button
    itself never lands. Returns an error text, or '' when chosen."""
    targets = []
    try:
        if await option.evaluate("e => e.tagName === 'INPUT'"):
            input_id = await option.get_attribute('id')
            if input_id:
                targets.append(page.locator('label[for="%s"]' % input_id.replace('"', '\\"')).first)
            targets.append(option.locator('xpath=ancestor::label[1]'))
    except Exception:
        pass
    targets.append(option)
    error = ''
    for target in targets:
        try:
            if not await target.count():
                continue
            await target.click(timeout=5000)
            return ''
        except Exception as exc:
            error = str(exc).splitlines()[0][:200]
    try:
        if await option.evaluate("e => e.tagName === 'INPUT'"):
            await option.check(force=True, timeout=5000)     # a radio button: choosing it sends nothing
            return ''
    except Exception as exc:
        error = str(exc).splitlines()[0][:200]
    return error or 'no clickable element'


async def switch_send_mode(page, wait=15.0):
    """On a page with a message composer: choose "Click Send" in its send options.
    Types and sends nothing."""
    toggle = None
    for _i in range(int(wait / 0.5)):
        if await _visible(page, SEND_BUTTON):
            return _result('click_to_send', 'LinkedIn already uses Click Send to send.', True)
        toggle = await _visible(page, SEND_TOGGLE)
        if toggle:
            break
        await asyncio.sleep(0.5)
    if not toggle:
        return _result('composer_unavailable', 'No message composer with send options was found on %s.' % page.url,
                       True)
    option = None
    for opening in ('click', 'Enter'):             # a second try with the keyboard if the click opened nothing
        if opening == 'click':
            await toggle.click()
        else:
            await toggle.focus()
            await page.keyboard.press('Enter')
        for _i in range(12):
            await asyncio.sleep(0.4)
            option = await _click_send_option(page)
            if option:
                break
        if option:
            break
    if not option:
        menu = ''
        try:
            menu = await page.evaluate(SEND_MENU_JS)
        except Exception:
            pass
        try:
            await page.keyboard.press('Escape')
        except Exception:
            pass
        return _result('option_unavailable', 'No "Click Send" option in the send options. Menu shown: %s'
                       % (menu or 'none'), True)
    error = await _choose(page, option)
    if error:
        try:
            await page.keyboard.press('Escape')
        except Exception:
            pass
        return _result('option_unavailable', 'The "Click Send" option could not be chosen: %s' % error, True)
    for _i in range(12):
        await asyncio.sleep(0.5)
        if await _visible(page, SEND_BUTTON):
            return _result('click_to_send', 'Switched to Click Send to send.', True)
    return _result('unconfirmed', 'The option was chosen but no Send button appeared.', True)


async def click_to_send_flow(extractor, url=None):
    """Switch LinkedIn messaging to "Click Send to send". Types nothing and sends
    nothing: it only opens a composer and changes the send option."""
    session = _session_of(extractor)
    target = url if url and re.match(r'^https://www\.linkedin\.com/messaging/', url) else MESSAGING_URL
    await PageNavigator(session)._navigate_to_page(target)
    await session.check_rate_limit()
    return await switch_send_mode(session.page)


def install_invite_notices():
    """Wrap the engine's invite flow in memory (no engine file is changed): keep
    the notice LinkedIn shows after the invite dialog is submitted, and add it
    to the answer when the invitation was not recorded (send_failed)."""
    from linkedin_mcp_server.linkedin.connection_actions import ConnectionActions
    if getattr(ConnectionActions, '_odoo_notices', False):
        return
    submit, connect = ConnectionActions._submit_invite_dialog, ConnectionActions.connect_with_person

    async def _submit_invite_dialog(self, note):
        self._odoo_notice, self._odoo_dialog = '', {}
        try:                                    # what LinkedIn asks in the dialog, before anything is clicked
            await self._dialog_is_open(timeout=5000)
            self._odoo_dialog = await self._session.page.evaluate(INVITE_DIALOG_JS)
        except Exception:
            self._odoo_dialog = {}
        result = await submit(self, note)
        if result and result[0]:
            self._odoo_notice = await read_notice(self._session.page)
        return result

    async def connect_with_person(self, *args, **kwargs):
        self._odoo_notice, self._odoo_dialog = '', {}
        result = await connect(self, *args, **kwargs)
        if not isinstance(result, dict):
            return result
        notice = getattr(self, '_odoo_notice', '') or ''
        dialog = getattr(self, '_odoo_dialog', None) or {}
        # always say what LinkedIn showed: Odoo keeps it with the action
        result['linkedin_notice'] = notice
        result['invite_dialog'] = (dialog.get('text') or '')[:400]
        result['confirmed'] = bool(SENT_NOTICE.search(notice))
        if result.get('status') == 'send_failed' and notice:
            result['message'] = '%s LinkedIn says: %s' % (result.get('message') or '', notice)
        elif result.get('status') == 'connected' and REFUSAL_NOTICE.search(notice):
            # LinkedIn said no in its pop-up: its word counts, whatever the page showed right after
            result['status'] = 'send_failed'
            result['message'] = 'LinkedIn did not send the invitation. LinkedIn says: %s' % notice
        elif result.get('status') == 'connected' and dialog.get('email') and not result['confirmed']:
            # the dialog asked for the member's email address: nothing can have been sent
            result['status'] = 'connect_unavailable'
            result['message'] = 'LinkedIn asks for this member\'s email address to connect.'
        return result

    ConnectionActions._submit_invite_dialog = _submit_invite_dialog
    ConnectionActions.connect_with_person = connect_with_person
    ConnectionActions._odoo_notices = True


# The engine looks for the Message link in the first <section> of the profile
# that holds no other section. A profile with an "Open to work" (or "Hiring")
# card has that card as a section inside the top card, so the engine looks in
# the card, finds no Message link and never messages the person. This check
# starts from the Message link instead: the section that holds it must hold no
# other Message link, and the link must name one profile. The engine then
# verifies the recipient again on the message page, as for any other profile.
MESSAGE_TARGET_JS = r"""() => {
    const visible = e => {
        const visibility = e && getComputedStyle(e).visibility;
        return !!(e && visibility !== 'hidden' && visibility !== 'collapse' &&
                  (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
    };
    const active = a => visible(a) && !a.hasAttribute('disabled') &&
        (a.getAttribute('aria-disabled') || '').toLowerCase() !== 'true';
    const profileId = value => {
        if (typeof value !== 'string' || /[\\\x00-\x1f\x7f]/.test(value)) return null;
        try {
            const url = new URL(value, window.location.href);
            const host = url.hostname.toLowerCase().replace(/\.$/, '');
            if (url.protocol !== 'https:' || !/(^|\.)linkedin\.com$/.test(host) || url.username ||
                url.password || (url.port && url.port !== '443') || url.hash ||
                url.pathname !== '/messaging/compose/') return null;
            const ids = [...url.searchParams.getAll('recipient'), ...url.searchParams.getAll('profileUrn')]
                .map(item => item.trim().replace(/^urn:li:fsd_profile:/, ''));
            if (!ids.length || !ids.every(id => /^[A-Za-z0-9_-]+$/.test(id) && id === ids[0])) return null;
            return ids[0];
        } catch (error) {
            return null;
        }
    };
    const main = document.querySelector('main');
    if (!main) return {status: 'unresolved', why: 'no main area on the page'};
    const links = Array.from(main.querySelectorAll('a[href*="/messaging/compose/"]'))
        .filter(a => visible(a) && !a.closest('aside'));
    if (!links.length) return {status: 'unresolved', why: 'no Message link on the page'};
    const card = links[0].closest('section');
    if (!card) return {status: 'unresolved', why: 'the Message link is outside any section'};
    const own = links.filter(a => a.closest('section') === card);
    if (own.length !== 1 || !active(own[0])) {
        return {status: 'unresolved', why: own.length + ' Message links in the top card'};
    }
    const href = own[0].getAttribute('href') || own[0].href || '';
    if (!profileId(href)) return {status: 'unresolved', why: 'the Message link names no single profile'};
    const heading = Array.from(card.querySelectorAll('h1, h2, h3'))
        .find(h => visible(h) && h.closest('section') === card);
    return {
        status: 'resolved',
        pageUrl: window.location.href,
        displayName: heading ? (heading.innerText || heading.textContent || '').replace(/\s+/g, ' ').trim() : '',
        composeHrefs: [href],
    };
}"""


def message_target(data, sender_module):
    """The engine's message target from MESSAGE_TARGET_JS's answer, built with
    the engine's own URL checks; None when it is not one clear recipient."""
    if not isinstance(data, dict) or data.get('status') != 'resolved':
        return None
    page_url, hrefs = data.get('pageUrl'), data.get('composeHrefs')
    if not isinstance(page_url, str) or not isinstance(hrefs, list) or len(hrefs) != 1:
        return None
    profile_path = sender_module._profile_path_from_url(page_url)
    parsed = sender_module._safe_linkedin_url(hrefs[0], base=page_url) if isinstance(hrefs[0], str) else None
    if profile_path is None or parsed is None:
        return None
    compose_url = parsed.geturl()
    profile_urn = sender_module._profile_urn_from_compose_url(compose_url)
    if profile_urn is None:
        return None
    return sender_module._ProfileMessageTarget(profile_path=profile_path, profile_urn=profile_urn,
                                               compose_url=compose_url,
                                               display_name=(data.get('displayName') or '').strip() or None)


def install_message_target_fix():
    """Wrap the engine's Message-link lookup in memory (no engine file is
    changed): when the engine finds no clear Message link, MESSAGE_TARGET_JS
    looks again from the link itself; why it found none goes into the answer.
    A profile with no Message link at all keeps the engine's own answer."""
    from linkedin_mcp_server.linkedin import message_sender
    sender = getattr(message_sender, 'MessageSender', None)
    if sender is None or not hasattr(sender, '_read_profile_message_target') \
            or getattr(sender, '_odoo_target_fix', False):
        return
    read_target, send = sender._read_profile_message_target, sender.send_message

    async def _read_profile_message_target(self, *args, **kwargs):
        self._odoo_target_note = ''
        resolution = await read_target(self, *args, **kwargs)
        if resolution.status == 'resolved':
            return resolution
        # 'failed' (no clear link) or 'unavailable' (no link in the section it looked at): look from the link
        try:
            data = await self._page.evaluate(MESSAGE_TARGET_JS)
        except Exception as error:
            self._odoo_target_note = 'page check failed: %s' % error
            return resolution
        target = message_target(data, message_sender)
        if target is None:
            self._odoo_target_note = (data or {}).get('why') or 'no single recipient'
            return resolution
        logger.info('Message link found from the link itself (the engine\'s own lookup failed)')
        return message_sender._ProfileMessageTargetResolution('resolved', target)

    async def send_message(self, *args, **kwargs):
        self._odoo_target_note = ''
        result = await send(self, *args, **kwargs)
        note = getattr(self, '_odoo_target_note', '')
        if isinstance(result, dict) and note and result.get('status') in ('recipient_resolution_failed',
                                                                          'message_unavailable'):
            result['message'] = '%s Odoo check: %s.' % (result.get('message') or '', note)
        return result

    sender._read_profile_message_target = _read_profile_message_target
    sender.send_message = send_message
    sender._odoo_target_fix = True

def register_odoo_tools(mcp: FastMCP, *, tool_timeout: float) -> None:

    @mcp.tool(timeout=tool_timeout, title='Send Invite Direct',
              annotations={'destructiveHint': True, 'openWorldHint': True}, tags={'person', 'actions'})
    async def send_invite_direct(linkedin_username: str, ctx: Context, note: str | None = None) -> dict[str, Any]:
        """Send a connection invitation through LinkedIn's invite link (Odoo add-on
        tool), for a member whose profile the engine reads as "pending" although
        no invitation exists. Returns status connected, send_failed,
        connect_unavailable, custom_note_limit_reached or maybe_sent (Connect was
        pressed but nothing shows what LinkedIn did), with what LinkedIn showed."""
        username = re.sub(r'^.*linkedin\.com/in/', '', (linkedin_username or '').strip()).strip('/').split('/')[0]
        if not re.match(r'^[A-Za-z0-9%_.-]{2,120}$', username):
            return {'status': 'invalid_username', 'message': 'Not a LinkedIn username.', 'retry_safe': True}
        try:
            extractor = await get_ready_extractor(ctx, tool_name='send_invite_direct')
            return await send_invite_direct_flow(extractor, username, (note or '').strip() or None)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'send_invite_direct')
        except Exception as e:
            raise_tool_error(e, 'send_invite_direct')

    @mcp.tool(timeout=tool_timeout, title='Get Sent Invitations',
              annotations={'readOnlyHint': True, 'openWorldHint': True}, tags={'person'})
    async def get_sent_invitations(ctx: Context, limit: int = 300) -> dict[str, Any]:
        """Usernames of the people who have a pending invitation from the signed-in
        account, from LinkedIn's Sent invitations page (Odoo add-on tool; one page).
        Returns usernames, count, complete (the whole list was loaded), rows_only
        (the names come from invitation rows, not from other links) and the
        first text of the page."""
        limit = max(1, min(int(limit or 300), MAX_SENT_INVITATIONS))
        try:
            extractor = await get_ready_extractor(ctx, tool_name='get_sent_invitations')
            return await sent_invitations_flow(extractor, limit)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'get_sent_invitations')
        except Exception as e:
            raise_tool_error(e, 'get_sent_invitations')

    @mcp.tool(timeout=tool_timeout, title='Check Connection State',
              annotations={'readOnlyHint': True, 'openWorldHint': True}, tags={'person'})
    async def check_connection_state(linkedin_username: str, ctx: Context) -> dict[str, Any]:
        """Open one member's profile and report what it offers now (Odoo add-on tool):
        pending (an invitation is outstanding), connectable (Connect is offered, so no
        invitation is outstanding), already_connected, follow_only, incoming_request
        or unavailable."""
        username = re.sub(r'^.*linkedin\.com/in/', '', (linkedin_username or '').strip()).strip('/').split('/')[0]
        if not re.match(r'^[A-Za-z0-9%_.-]{2,120}$', username):
            return {'status': 'invalid_username', 'retry_safe': True}
        try:
            extractor = await get_ready_extractor(ctx, tool_name='check_connection_state')
            return await connection_state_flow(extractor, username)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'check_connection_state')
        except Exception as e:
            raise_tool_error(e, 'check_connection_state')

    @mcp.tool(timeout=tool_timeout, title='Check Invite Dialog',
              annotations={'readOnlyHint': True, 'openWorldHint': True}, tags={'person'})
    async def check_invite_dialog(linkedin_username: str, ctx: Context) -> dict[str, Any]:
        """Open one member's invite dialog without sending and report what it asks
        (Odoo add-on tool). Returns status email_required (LinkedIn wants the
        member's email address), dialog (a normal invite dialog) or no_dialog,
        and the dialog text."""
        username = re.sub(r'^.*linkedin\.com/in/', '', (linkedin_username or '').strip()).strip('/').split('/')[0]
        if not re.match(r'^[A-Za-z0-9%_.-]{2,120}$', username):
            return {'status': 'invalid_username', 'text': '', 'retry_safe': True}
        try:
            extractor = await get_ready_extractor(ctx, tool_name='check_invite_dialog')
            return await invite_dialog_flow(extractor, username)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'check_invite_dialog')
        except Exception as e:
            raise_tool_error(e, 'check_invite_dialog')

    @mcp.tool(timeout=tool_timeout, title='Look Up Location',
              annotations={'readOnlyHint': True, 'openWorldHint': True}, tags={'search'})
    async def lookup_location(query: str, ctx: Context) -> dict[str, Any]:
        """LinkedIn's own location suggestions for a place name, as its people
        search "Locations" filter offers them (Odoo add-on tool; no page is
        opened when LinkedIn is already open). Returns status ok, not_found or
        unavailable, and candidates [{id, name}]: the id is LinkedIn's location id."""
        query = (query or '').strip()[:100]
        if not query:
            return {'status': 'not_found', 'query': query, 'candidates': []}
        try:
            extractor = await get_ready_extractor(ctx, tool_name='lookup_location')
            return await lookup_location_flow(extractor, query)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'lookup_location')
        except Exception as e:
            raise_tool_error(e, 'lookup_location')

    @mcp.tool(timeout=tool_timeout, title='Search People Filtered',
              annotations={'readOnlyHint': True, 'openWorldHint': True}, tags={'search'})
    async def search_people_filtered(ctx: Context, keywords: str = '', geo_ids: list[str] | None = None,
                                     title: str = '', network: list[str] | None = None, page: int = 1,
                                     url: str | None = None) -> dict[str, Any]:
        """One page of a LinkedIn people search with LinkedIn's real filters
        (Odoo add-on tool): geo_ids are LinkedIn location ids (from
        lookup_location), title its Title filter, network degrees F/S/O, page
        1-100. url: a people search URL built on LinkedIn, used as it is (only
        its page changes). Same answer as search_people."""
        geo_ids = [g for g in (str(x).strip() for x in (geo_ids or [])) if g.isdigit()][:10]
        network = [n for n in (network or []) if n in ('F', 'S', 'O')]
        if url and not url.startswith(PEOPLE_SEARCH_URL):
            return {'status': 'invalid_url', 'message': 'Only a LinkedIn people search URL can be used.'}
        target = people_search_url(keywords, geo_ids, title, network, page, url)
        try:
            extractor = await get_ready_extractor(ctx, tool_name='search_people_filtered')
            return await filtered_search_flow(extractor, target)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'search_people_filtered')
        except Exception as e:
            raise_tool_error(e, 'search_people_filtered')

    @mcp.tool(timeout=tool_timeout, title='Get Recent Connections',
              annotations={'readOnlyHint': True, 'openWorldHint': True}, tags={'person'})
    async def get_recent_connections(ctx: Context, limit: int = 40) -> dict[str, Any]:
        """Usernames of the signed-in account's newest 1st-degree connections,
        most recent first (Odoo add-on tool; one page read). Returns url,
        usernames and count."""
        limit = max(1, min(int(limit or 40), MAX_CONNECTIONS))
        try:
            extractor = await get_ready_extractor(ctx, tool_name='get_recent_connections')
            return await recent_connections_flow(extractor, limit)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'get_recent_connections')
        except Exception as e:
            raise_tool_error(e, 'get_recent_connections')

    @mcp.tool(timeout=tool_timeout, title='Follow Person',
              annotations={'destructiveHint': False, 'openWorldHint': True}, tags={'person', 'actions'})
    async def follow_person(linkedin_username: str, ctx: Context) -> dict[str, Any]:
        """Follow a LinkedIn member who offers no Connect action (Odoo add-on tool).

        Returns status followed, already_following, follow_unavailable or
        follow_unconfirmed, with message and retry_safe (always true: it never
        clicks when already following)."""
        username = re.sub(r'^.*linkedin\.com/in/', '', (linkedin_username or '').strip()).strip('/').split('/')[0]
        if not re.match(r'^[A-Za-z0-9%_.-]{2,120}$', username):
            return _result('invalid_username', 'Not a LinkedIn username.', True)
        try:
            extractor = await get_ready_extractor(ctx, tool_name='follow_person')
            return await follow_flow(extractor, username)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'follow_person')
        except Exception as e:
            raise_tool_error(e, 'follow_person')


    @mcp.tool(timeout=tool_timeout, title='Use Click Send To Send',
              annotations={'destructiveHint': False, 'openWorldHint': True}, tags={'messaging', 'actions'})
    async def use_click_to_send(ctx: Context, url: str | None = None) -> dict[str, Any]:
        """Switch LinkedIn messaging from "Press Enter to Send" to "Click Send to
        send", so send_message finds its Send button (Odoo add-on tool). Types and
        sends nothing. url: the messaging page send_message reported (optional).

        Returns status click_to_send (done or already so), or composer_unavailable,
        option_unavailable, unconfirmed; with message and retry_safe (always true)."""
        try:
            extractor = await get_ready_extractor(ctx, tool_name='use_click_to_send')
            return await click_to_send_flow(extractor, url)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'use_click_to_send')
        except Exception as e:
            raise_tool_error(e, 'use_click_to_send')

    @mcp.tool(timeout=tool_timeout, title='Create Post',
              annotations={'destructiveHint': True, 'openWorldHint': True}, tags={'post', 'actions'})
    async def create_post(text: str, ctx: Context, image_path: str | None = None) -> dict[str, Any]:
        """Publish a LinkedIn post on the signed-in account (Odoo add-on tool).

        Args:
            text: post text (line breaks allowed, at most 3000 characters)
            image_path: optional local image file to attach

        Returns status (published, published_no_url, outcome_unknown, or a refusal
        such as composer_unavailable with retry_safe true), message, retry_safe and
        post_url when LinkedIn showed the link."""
        if not (text or '').strip() or len(text) > MAX_POST_CHARS:
            return _result('invalid_text', 'The text must hold 1 to %s characters.' % MAX_POST_CHARS, True)
        if image_path and not os.path.isfile(image_path):
            return _result('invalid_image', 'The image file does not exist.', True)
        try:
            extractor = await get_ready_extractor(ctx, tool_name='create_post')
            logger.info('Creating a post (%s characters, image=%s)', len(text), bool(image_path))
            return await create_post_flow(extractor, text, image_path)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'create_post')
        except Exception as e:
            raise_tool_error(e, 'create_post')

    @mcp.tool(timeout=tool_timeout, title='Get Post Stats',
              annotations={'readOnlyHint': True, 'openWorldHint': True}, tags={'post'})
    async def get_post_stats(post_url: str, ctx: Context) -> dict[str, Any]:
        """Read the page of one published post (Odoo add-on tool). Returns url
        and sections.post (raw text with the reaction, comment and repost counts)."""
        if not re.match(r'^https://www\.linkedin\.com/(feed/update|posts)/', post_url or ''):
            return {'url': post_url, 'sections': {}, 'error': 'not a LinkedIn post address'}
        try:
            extractor = await get_ready_extractor(ctx, tool_name='get_post_stats')
            return await post_stats_flow(extractor, post_url)
        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, 'get_post_stats')
        except Exception as e:
            raise_tool_error(e, 'get_post_stats')
