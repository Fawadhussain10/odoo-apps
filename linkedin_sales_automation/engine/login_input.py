"""Pure logic of the in-Odoo LinkedIn login: input validation and forwarding,
screencast frames, page classification. No engine or browser import, so Odoo's
tests use it directly (with a fake page and a fake CDP session).

Privacy: nothing here logs or keeps what the user types. Events are applied to
the browser and dropped.
"""
import base64
import re

MAX_EVENTS = 50
MAX_TEXT = 512
NAMED_KEYS = {
    'Enter', 'Tab', 'Backspace', 'Delete', 'Escape', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
    'Home', 'End', 'PageUp', 'PageDown', 'Space',
}
MODIFIED_KEY = re.compile(r'^(Control|Meta|Shift|Alt)\+[A-Za-z0-9]$')
BUTTONS = {'left', 'right', 'middle'}

LOGIN_STATES = ('starting', 'waiting', 'two_step', 'captcha', 'validating', 'connected', 'failed')
TWO_STEP_MARKERS = ('/checkpoint/challenge', '/checkpoint/lg/', 'two-step', 'two_step', '/checkpoint/pk/',
                    'verification', 'add-phone')
CAPTCHA_MARKERS = ('captcha', 'arkoselabs', 'funcaptcha', 'hcaptcha', 'recaptcha')


class InputError(ValueError):
    pass


def _fraction(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InputError('%s must be a number' % name) from None
    return min(max(number, 0.0), 1.0)


def validate_events(events):
    """Turn raw client events into a list of safe actions.

    Coordinates are fractions (0–1) of the shown frame, so the client never needs
    to know the browser's real size. Unknown events are refused.
    """
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise InputError('events must be a list of at most %d items' % MAX_EVENTS)
    actions = []
    for event in events:
        if not isinstance(event, dict):
            raise InputError('each event must be an object')
        kind = event.get('type')
        if kind in ('click', 'dblclick', 'move'):
            x, y = _fraction(event.get('x'), 'x'), _fraction(event.get('y'), 'y')
            button = event.get('button', 'left')
            if button not in BUTTONS:
                raise InputError('unknown mouse button')
            actions.append((kind, x, y, button))
        elif kind == 'scroll':
            dx = max(min(int(event.get('dx', 0)), 2000), -2000)
            dy = max(min(int(event.get('dy', 0)), 2000), -2000)
            actions.append(('scroll', dx, dy))
        elif kind == 'key':
            key = event.get('key')
            if not isinstance(key, str) or not (key in NAMED_KEYS or MODIFIED_KEY.match(key)):
                raise InputError('key not allowed')
            actions.append(('key', 'Space' if key == ' ' else key))
        elif kind == 'text':
            text = event.get('text')
            if not isinstance(text, str) or not text or len(text) > MAX_TEXT:
                raise InputError('text must be 1–%d characters' % MAX_TEXT)
            actions.append(('text', text))
        else:
            raise InputError('unknown event type')
    return actions


async def apply_actions(page, actions, size):
    """Replay validated actions on a Playwright-like page.

    size = (width, height) of the page in CSS pixels.
    """
    width, height = size
    for action in actions:
        kind = action[0]
        if kind in ('click', 'dblclick', 'move'):
            x, y = action[1] * width, action[2] * height
            if kind == 'move':
                await page.mouse.move(x, y)
            else:
                await page.mouse.click(x, y, button=action[3], click_count=2 if kind == 'dblclick' else 1)
        elif kind == 'scroll':
            await page.mouse.wheel(action[1], action[2])
        elif kind == 'key':
            await page.keyboard.press(action[1])
        elif kind == 'text':
            await page.keyboard.insert_text(action[1])


class FrameStore:
    """Latest screencast frame, as JPEG bytes with a sequence number."""

    def __init__(self):
        self.data = b''
        self.seq = 0
        self.width = 0
        self.height = 0

    def store(self, jpeg, width=None, height=None):
        self.data = jpeg
        self.seq += 1
        if width:
            self.width = int(width)
        if height:
            self.height = int(height)

    async def on_screencast_frame(self, cdp, params):
        """Page.screencastFrame handler: keep the frame and acknowledge it, or
        Chromium stops sending."""
        metadata = params.get('metadata') or {}
        self.store(base64.b64decode(params['data']), metadata.get('deviceWidth'), metadata.get('deviceHeight'))
        await cdp.send('Page.screencastFrameAck', {'sessionId': params['sessionId']})


def classify_page(url, frame_urls=()):
    """Login state shown to the user, from the page address."""
    lowered = (url or '').lower()
    frames = ' '.join(frame_urls).lower()
    if any(marker in lowered or marker in frames for marker in CAPTCHA_MARKERS):
        return 'captcha'
    if any(marker in lowered for marker in TWO_STEP_MARKERS):
        return 'two_step'
    return 'waiting'


LI_AT_PATTERN = re.compile(r'^[A-Za-z0-9_\-\.%=~]{40,1500}$')


def li_at_cookies(value, now):
    """The portable cookie list for a pasted li_at value (Playwright format)."""
    value = (value or '').strip().strip('"').strip("'")
    if value.lower().startswith('li_at='):
        value = value[6:]
    if not LI_AT_PATTERN.match(value):
        raise InputError('This does not look like a li_at cookie value.')
    return [{
        'name': 'li_at', 'value': value, 'domain': '.www.linkedin.com', 'path': '/',
        'expires': int(now) + 365 * 24 * 3600, 'httpOnly': True, 'secure': True, 'sameSite': 'None',
    }]
