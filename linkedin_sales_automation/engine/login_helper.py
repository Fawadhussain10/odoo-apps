"""Connect one LinkedIn account from inside Odoo. Run with the engine's Python.

Two modes, both ending with the engine's own session files (cookies.json and
source-state.json) in the account's folder:

* login   – runs the engine's interactive login (the same code as
            `mcp-server-linkedin --login`) on a browser whose screen is streamed
            with CDP screencast; Odoo shows it and forwards mouse and keyboard.
* cookies – the engine's session import (the code of `--import-from-browser`),
            fed with a cookie file Odoo received (uploaded session or pasted
            li_at): LinkedIn validates the cookies in a real browser first.

Odoo talks to this process over 127.0.0.1 on a secret path (environment
variable LI_LOGIN_SECRET, never on the command line):
  GET  <secret>/state          {"state", "message", "seq"}
  GET  <secret>/frame?after=N  JPEG, or 204 when no newer frame
  POST <secret>/input          {"events": [...]}  (see login_input.py)
  POST <secret>/cancel
Nothing typed is logged or written anywhere.
"""
import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import login_input  # noqa: E402

STATUS = {'state': 'starting', 'message': ''}
FRAMES = login_input.FrameStore()
PAGE = {'page': None}
CANCELLED = asyncio.Event()
CONNECTED_GRACE = 60          # keep answering /state this long after the end


def set_state(state, message=''):
    STATUS.update(state=state, message=message)


# ---------------------------------------------------------------------------
# Control server (tiny HTTP/1.1 on asyncio streams; no access log)
# ---------------------------------------------------------------------------
async def handle(reader, writer):
    try:
        head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout=10)
        lines = head.decode('latin-1').split('\r\n')
        method, target, _version = lines[0].split(' ', 2)
        headers = {k.strip().lower(): v.strip() for k, v in (l.split(':', 1) for l in lines[1:] if ':' in l)}
        length = min(int(headers.get('content-length', 0) or 0), 64 * 1024)
        body = await reader.readexactly(length) if length else b''
        path, _sep, query = target.partition('?')
        secret = os.environ['LI_LOGIN_SECRET']
        status, ctype, payload = 404, 'application/json', b'{"error":"not found"}'
        if path == secret + '/state' and method == 'GET':
            status, payload = 200, json.dumps(dict(STATUS, seq=FRAMES.seq)).encode()
        elif path == secret + '/frame' and method == 'GET':
            after = int(dict(p.split('=', 1) for p in query.split('&') if '=' in p).get('after', -1) or -1)
            if FRAMES.data and FRAMES.seq != after:
                status, ctype, payload = 200, 'image/jpeg', FRAMES.data
            else:
                status, payload = 204, b''
        elif path == secret + '/input' and method == 'POST':
            try:
                actions = login_input.validate_events(json.loads(body or b'{}').get('events'))
                page = PAGE['page']
                if page is not None:
                    size = page.viewport_size or {'width': FRAMES.width or 1280, 'height': FRAMES.height or 800}
                    await login_input.apply_actions(page, actions, (size['width'], size['height']))
                status, payload = 200, b'{"ok":true}'
            except login_input.InputError as exc:
                status, payload = 400, json.dumps({'error': str(exc)}).encode()
        elif path == secret + '/cancel' and method == 'POST':
            CANCELLED.set()
            status, payload = 200, b'{"ok":true}'
        reason = {200: 'OK', 204: 'No Content', 400: 'Bad Request', 404: 'Not Found'}[status]
        writer.write(('HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-store\r\n'
                      'X-Frame-Seq: %d\r\nConnection: close\r\n\r\n' % (status, reason, ctype, len(payload),
                                                                         FRAMES.seq)).encode() + payload)
        await writer.drain()
    except Exception:          # a broken client request must never stop the login
        pass
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# Login mode
# ---------------------------------------------------------------------------
async def stream(page):
    """Screencast the login page into FRAMES and keep STATUS in line with it."""
    PAGE['page'] = page
    cdp = await page.context.new_cdp_session(page)
    cdp.on('Page.screencastFrame', lambda params: asyncio.ensure_future(FRAMES.on_screencast_frame(cdp, params)))
    await cdp.send('Page.startScreencast', {'format': 'jpeg', 'quality': 60, 'maxWidth': 1280,
                                            'maxHeight': 900, 'everyNthFrame': 1})

    async def watch():
        last_frame = time.monotonic()
        seq = FRAMES.seq
        while STATUS['state'] not in ('connected', 'failed', 'validating'):
            try:
                frame_urls = [frame.url for frame in page.frames]
                set_state(login_input.classify_page(page.url, frame_urls))
                if FRAMES.seq != seq:
                    seq, last_frame = FRAMES.seq, time.monotonic()
                elif time.monotonic() - last_frame > 3:
                    # a still page sends no screencast frames: take one now and then
                    FRAMES.store(await page.screenshot(type='jpeg', quality=60))
                    seq, last_frame = FRAMES.seq, time.monotonic()
            except Exception:
                pass
            await asyncio.sleep(0.5)
    asyncio.ensure_future(watch())


async def run_login(args):
    import linkedin_mcp_server.setup as setup

    base = setup.BrowserManager

    class StreamingBrowserManager(base):
        """The engine's login browser, shown in Odoo instead of on a screen."""

        def __init__(self, *a, **kw):
            kw['headless'] = args.headless
            if args.headless and not kw.get('viewport'):
                kw['viewport'] = {'width': 1280, 'height': 800}
            super().__init__(*a, **kw)

        async def __aenter__(self):
            result = await super().__aenter__()
            await stream(self.page)
            return result

    setup.BrowserManager = StreamingBrowserManager
    set_state('waiting')
    return await setup.interactive_login(Path(args.user_data_dir))


# ---------------------------------------------------------------------------
# Cookies mode
# ---------------------------------------------------------------------------
async def run_cookies(args):
    cookies_file = Path(args.cookies)
    cookies = json.loads(cookies_file.read_text())
    cookies_file.unlink()          # the value now lives only in this process
    from linkedin_mcp_server.common_utils import secure_write_text
    from linkedin_mcp_server.browser_import import orchestrate

    def discover(_browser):
        return [(SimpleNamespace(browser='odoo', profile_dir_name='upload'), None)], []

    def stage(_profile, cookie_path):
        secure_write_text(cookie_path, json.dumps(cookies, indent=2), mode=0o600)
        return True

    orchestrate._discover_and_rank = discover
    orchestrate._extract_and_stage = stage
    set_state('validating', 'LinkedIn is checking the session…')
    return await orchestrate.import_session_from_browser(None, user_data_dir=Path(args.user_data_dir))


# ---------------------------------------------------------------------------
async def main_async(args):
    server = await asyncio.start_server(handle, '127.0.0.1', args.port)
    job = asyncio.ensure_future(run_login(args) if args.mode == 'login' else run_cookies(args))
    cancel = asyncio.ensure_future(CANCELLED.wait())
    done, _pending = await asyncio.wait({job, cancel}, timeout=args.timeout + 30,
                                        return_when=asyncio.FIRST_COMPLETED)
    if job in done and not job.cancelled() and job.exception() is None and job.result():
        set_state('connected', 'Connected')
    elif job in done and job.exception() is not None:
        error = job.exception()
        message = str(error).splitlines()[0][:300] if str(error) else error.__class__.__name__
        set_state('failed', message)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    elif cancel in done:
        job.cancel()
        set_state('failed', 'Cancelled')
    elif job in done:
        set_state('failed', 'LinkedIn did not accept the session.')
    else:
        job.cancel()
        set_state('failed', 'Timed out')
    for task in (job, cancel):
        if not task.done():
            task.cancel()
    await asyncio.sleep(CONNECTED_GRACE)
    server.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('login', 'cookies'), required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user-data-dir', required=True)
    parser.add_argument('--cookies', help='cookie file for --mode cookies (deleted once read)')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args(argv)
    if 'LI_LOGIN_SECRET' not in os.environ:
        print('LI_LOGIN_SECRET is required', file=sys.stderr)
        return 64
    prepare_engine(args)
    asyncio.run(main_async(args))
    return 0


def prepare_engine(args):
    """The steps the engine's own CLI takes before `--login` and
    `--import-from-browser` (linkedin_mcp_server.cli_main.main), in its order."""
    from linkedin_mcp_server.bootstrap import configure_browser_environment, ensure_browser_installed
    from linkedin_mcp_server.config import set_config
    from linkedin_mcp_server.config.loaders import load_config
    from linkedin_mcp_server.drivers.browser import set_headless
    from linkedin_mcp_server.profile_claim import ensure_profile_claim
    argv = ['--user-data-dir', args.user_data_dir, '--no-auto-import', '--login-timeout', str(args.timeout)]
    if args.mode == 'login' and not args.headless:
        argv.append('--no-headless')
    config = load_config(argv)
    set_config(config)
    ensure_profile_claim(Path(config.browser.user_data_dir), claim_anyway=False)
    configure_browser_environment()
    set_headless(True if args.mode == 'cookies' else args.headless)
    ensure_browser_installed()


if __name__ == '__main__':
    sys.exit(main())
