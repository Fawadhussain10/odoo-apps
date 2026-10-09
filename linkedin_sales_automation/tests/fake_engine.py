#!/usr/bin/env python3
"""Stand-in for linkedin-mcp-server in tests: same command-line arguments, a
minimal MCP Streamable HTTP server on 127.0.0.1, no browser, no network."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOOLS = ['check_invite_dialog', 'connect_with_person', 'create_post', 'follow_person', 'get_conversation', 'get_inbox',
         'get_my_profile', 'get_person_profile', 'get_post_stats', 'get_recent_connections', 'search_people',
         'send_message']
DEFAULTS = {
    'connect_with_person': {'status': 'connected', 'message': 'Connection request sent. State after send: pending.'},
    'send_message': {'status': 'sent', 'message': 'Message sent.', 'sent': True, 'retry_safe': False},
    'get_inbox': {'url': 'https://www.linkedin.com/messaging/', 'sections': {'inbox': ''}},
    'get_conversation': {'url': 'https://www.linkedin.com/messaging/thread/x/', 'sections': {'conversation': ''}},
    'get_person_profile': {'url': 'https://www.linkedin.com/in/x/', 'sections': {
        'main_profile': 'Ali Raza\nFounder at Brand X\nLahore\nAbout\nI run a fashion brand on Shopify.'}},
    'search_people': {'url': 'https://www.linkedin.com/search/results/people/', 'sections': {'search_results': ''}},
    'check_invite_dialog': {'status': 'dialog', 'text': 'Add a note to your invitation?', 'retry_safe': True},
    'follow_person': {'status': 'followed', 'message': 'Now following.', 'retry_safe': True},
    'get_recent_connections': {'url': 'https://www.linkedin.com/mynetwork/invite-connect/connections/',
                               'usernames': [], 'count': 0},
    'create_post': {'status': 'published', 'message': 'Post published.', 'retry_safe': False, 'published': True,
                    'post_url': 'https://www.linkedin.com/feed/update/urn:li:activity:7000000000000000001/'},
    'get_post_stats': {'url': 'https://www.linkedin.com/feed/update/urn:li:activity:7000000000000000001/',
                       'sections': {'post': 'Harvey Reid\nOur new post\nAli Raza and 41 others\n5 comments\n2 reposts'}},
}


def scripted(session, name):
    """Next scripted answer for a tool: <session>/fake-script.json = {tool: [answer, ...]},
    an answer being {"data": {...}} or {"error": "text"}, optionally with "sleep": seconds."""
    path = session / 'fake-script.json'
    if not path.exists():
        return None
    script = json.loads(path.read_text() or '{}')
    queue = script.get(name) or []
    if not queue:
        return None
    answer = queue.pop(0)
    path.write_text(json.dumps(script))
    return answer


def as_result(answer):
    if answer.get('sleep'):
        time.sleep(answer['sleep'])
    if 'error' in answer:
        return {'content': [{'type': 'text', 'text': answer['error']}], 'isError': True}
    data = answer['data']
    return {'content': [{'type': 'text', 'text': json.dumps(data)}], 'structuredContent': data, 'isError': False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b''
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != self.server.mcp_path:
            return self._send(404, {'error': 'not found'})
        message = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if 'id' not in message:
            return self._send(202)
        method, req_id = message.get('method'), message['id']
        if method == 'initialize':
            result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'fake-linkedin-engine', 'version': '0.0'}}
        elif method == 'tools/list':
            result = {'tools': [{'name': n, 'inputSchema': {'type': 'object'}} for n in TOOLS]}
        elif method == 'tools/call':
            name = message['params']['name']
            session = Path(self.server.user_data_dir).parent
            with open(session / 'fake-calls.jsonl', 'a') as log:
                log.write(json.dumps({'tool': name, 'args': message['params'].get('arguments') or {}}) + '\n')
            answer = scripted(session, name)
            if answer is not None:
                result = as_result(answer)
            elif (session / 'fake-logged-out').exists():
                result = {'content': [{'type': 'text', 'text': 'LinkedIn login required: the session expired.'}],
                          'isError': True}
            elif name == 'get_my_profile':
                profile = {'url': 'https://www.linkedin.com/in/harvey-reid/',
                           'sections': {'main_profile': 'Harvey Reid\nFounder at Example Ltd'}}
                result = {'content': [{'type': 'text', 'text': json.dumps(profile)}], 'structuredContent': profile,
                          'isError': False}
            elif name in DEFAULTS:
                data = dict(DEFAULTS[name])
                if name == 'connect_with_person':
                    data['note_sent'] = bool((message['params'].get('arguments') or {}).get('note'))
                result = as_result({'data': data})
            else:
                result = {'content': [{'type': 'text', 'text': 'ok %s' % name}], 'isError': False}
        else:
            return self._send(200, {'jsonrpc': '2.0', 'id': req_id, 'error': {'code': -32601, 'message': 'no'}})
        self._send(200, {'jsonrpc': '2.0', 'id': req_id, 'result': result})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--path', default=os.environ.get('HTTP_PATH', '/mcp'))
    parser.add_argument('--user-data-dir')
    parser.add_argument('--no-auto-import', action='store_true')
    parser.add_argument('--no-headless', action='store_true')
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.mcp_path = args.path
    server.user_data_dir = args.user_data_dir or '.'
    server.serve_forever()


if __name__ == '__main__':
    sys.exit(main())
