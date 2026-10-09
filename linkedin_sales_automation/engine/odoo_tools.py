"""Extra engine tools Odoo needs, registered on the engine's own MCP server
(see runner.py), so they run on the same browser session and one at a time
with the engine's tools.

* create_post     - publish a post (text, optional image) on the signed-in account
* get_post_stats  - read a published post's page (reactions, comments, reposts)
* follow_person   - follow someone LinkedIn offers no Connect for (top card or More menu)
* get_recent_connections - the newest 1st-degree connections, one page read
* check_invite_dialog - open one person's invite dialog WITHOUT sending and say
  what LinkedIn asks there (e.g. the person's email address)

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


def install_invite_notices():
    """Wrap the engine's invite flow in memory (no engine file is changed): keep
    the notice LinkedIn shows after the invite dialog is submitted, and add it
    to the answer when the invitation was not recorded (send_failed)."""
    from linkedin_mcp_server.linkedin.connection_actions import ConnectionActions
    if getattr(ConnectionActions, '_odoo_notices', False):
        return
    submit, connect = ConnectionActions._submit_invite_dialog, ConnectionActions.connect_with_person

    async def _submit_invite_dialog(self, note):
        self._odoo_notice = ''
        result = await submit(self, note)
        if result and result[0]:
            self._odoo_notice = await read_notice(self._session.page)
        return result

    async def connect_with_person(self, *args, **kwargs):
        self._odoo_notice = ''
        result = await connect(self, *args, **kwargs)
        notice = getattr(self, '_odoo_notice', '')
        if notice and isinstance(result, dict) and result.get('status') == 'send_failed':
            result['message'] = '%s LinkedIn says: %s' % (result.get('message') or '', notice)
        return result

    ConnectionActions._submit_invite_dialog = _submit_invite_dialog
    ConnectionActions.connect_with_person = connect_with_person
    ConnectionActions._odoo_notices = True


def register_odoo_tools(mcp: FastMCP, *, tool_timeout: float) -> None:

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
