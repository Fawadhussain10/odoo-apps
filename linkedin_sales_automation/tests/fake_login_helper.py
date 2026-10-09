#!/usr/bin/env python3
"""Stand-in for engine/login_helper.py in tests: same arguments and protocol, no
browser. Text sent as input drives the state: "TWOSTEP" -> two_step,
"CAPTCHA" -> captcha, "LOGIN-OK" -> connected, "LOGIN-BAD" -> failed.
Received events are appended to <session>/fake-events.jsonl so tests can check
forwarding (only the fake does this)."""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE = {'state': 'waiting', 'message': '', 'seq': 0}
JPEG = bytes.fromhex('ffd8ffe000104a46494600010100000100010000ffd9')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body=b'', ctype='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Frame-Seq', str(STATE['seq']))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        secret = os.environ['LI_LOGIN_SECRET']
        path, _sep, query = self.path.partition('?')
        if path == secret + '/state':
            return self._send(200, json.dumps(STATE).encode())
        if path == secret + '/frame':
            after = int(dict(p.split('=', 1) for p in query.split('&') if '=' in p).get('after', -1))
            if after == STATE['seq']:
                return self._send(204)
            return self._send(200, JPEG, 'image/jpeg')
        self._send(404)

    def do_POST(self):
        secret = os.environ['LI_LOGIN_SECRET']
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if self.path == secret + '/input':
            events = json.loads(body or b'{}').get('events') or []
            with open(self.server.events_file, 'a') as handle:
                handle.write(json.dumps(events) + '\n')
            for event in events:
                text = event.get('text', '')
                if text == 'TWOSTEP':
                    STATE['state'] = 'two_step'
                elif text == 'CAPTCHA':
                    STATE['state'] = 'captcha'
                elif text == 'LOGIN-OK':
                    self.server.session_ok()
                elif text == 'LOGIN-BAD':
                    STATE.update(state='failed', message='LinkedIn refused the sign-in')
            STATE['seq'] += 1
            return self._send(200, b'{"ok":true}')
        if self.path == secret + '/cancel':
            STATE.update(state='failed', message='Cancelled')
            return self._send(200, b'{"ok":true}')
        self._send(404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user-data-dir', required=True)
    parser.add_argument('--cookies')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    session = Path(args.user_data_dir).parent
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.events_file = str(session / 'fake-events.jsonl')

    def session_ok():
        (session / 'cookies.json').write_text('[{"name": "li_at", "value": "x"}]')
        STATE['state'] = 'connected'
    server.session_ok = session_ok
    if args.mode == 'cookies':
        cookies = json.loads(Path(args.cookies).read_text())
        Path(args.cookies).unlink()
        STATE['state'] = 'validating'

        def check():
            time.sleep(0.3)
            if any(c.get('name') == 'li_at' and c.get('value') != 'rejected-by-linkedin' * 3 for c in cookies):
                session_ok()
            else:
                STATE.update(state='failed', message='LinkedIn did not accept the session.')
        threading.Thread(target=check, daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    sys.exit(main())
