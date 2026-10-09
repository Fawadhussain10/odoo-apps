"""Minimal MCP (Streamable HTTP) client.

Odoo uses it to talk to its own LinkedIn engines on 127.0.0.1 (one engine
process per LinkedIn profile). Plain JSON and server-sent-event answers are
both understood.
"""
import json
import logging
import time

import requests

_logger = logging.getLogger(__name__)

PROTOCOL_VERSION = '2025-06-18'


class McpClientError(Exception):
    pass


class McpClient:
    def __init__(self, url, token=None, timeout=30, retries=3, backoff=2.0):
        self.url = url
        self.token = token
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.session_id = None
        self._next_id = 1

    # -- transport -------------------------------------------------------
    def _headers(self):
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': PROTOCOL_VERSION,
        }
        if self.token:
            headers['Authorization'] = 'Bearer %s' % self.token
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        return headers

    @staticmethod
    def _parse_sse(text, wanted_id):
        """Return the JSON-RPC message with id == wanted_id from an SSE body."""
        data_lines = []
        for line in text.splitlines() + ['']:
            if line.startswith('data:'):
                data_lines.append(line[5:].lstrip())
            elif not line.strip() and data_lines:
                try:
                    msg = json.loads('\n'.join(data_lines))
                except ValueError:
                    msg = None
                data_lines = []
                if isinstance(msg, dict) and msg.get('id') == wanted_id:
                    return msg
        raise McpClientError('No response for request %s in the event stream' % wanted_id)

    def _post(self, payload, timeout=None):
        last_exc = None
        for attempt in range(self.retries):
            try:
                resp = requests.post(self.url, data=json.dumps(payload), headers=self._headers(),
                                     timeout=timeout or self.timeout)
                if resp.status_code in (401, 403):
                    raise McpClientError('The engine refused the request (HTTP %s)' % resp.status_code)
                if resp.status_code >= 500 and attempt < self.retries - 1:
                    raise requests.RequestException('HTTP %s' % resp.status_code)
                return resp
            except McpClientError:
                raise
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.retries - 1:
                    time.sleep(self.backoff * (2 ** attempt))
        raise McpClientError('Connection failed after %s attempts: %s' % (self.retries, last_exc))

    def request(self, method, params=None, timeout=None):
        req_id = self._next_id
        self._next_id += 1
        payload = {'jsonrpc': '2.0', 'id': req_id, 'method': method}
        if params is not None:
            payload['params'] = params
        resp = self._post(payload, timeout=timeout)
        if resp.headers.get('Mcp-Session-Id'):
            self.session_id = resp.headers['Mcp-Session-Id']
        # MCP is UTF-8; requests would decode a charset-less text/event-stream as Latin-1
        resp.encoding = 'utf-8'
        if resp.status_code >= 400:
            raise McpClientError('HTTP %s: %s' % (resp.status_code, resp.text[:300]))
        ctype = resp.headers.get('Content-Type', '')
        if 'text/event-stream' in ctype:
            msg = self._parse_sse(resp.text, req_id)
        else:
            try:
                msg = resp.json()
            except ValueError:
                raise McpClientError('Invalid JSON response: %s' % resp.text[:300])
        if msg.get('error'):
            raise McpClientError('%s' % msg['error'].get('message', msg['error']))
        return msg.get('result') or {}

    def notify(self, method, params=None):
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        self._post(payload)

    # -- MCP helpers -----------------------------------------------------
    def initialize(self):
        result = self.request('initialize', {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {},
            'clientInfo': {'name': 'odoo-linkedin-sales', 'version': '18.0'},
        })
        self.notify('notifications/initialized')
        return result

    def list_tools(self):
        return self.request('tools/list', {}).get('tools', [])

    def call_tool(self, name, arguments, timeout=200):
        return self.request('tools/call', {'name': name, 'arguments': arguments}, timeout=timeout)
