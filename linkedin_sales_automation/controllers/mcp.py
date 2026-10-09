"""Odoo MCP endpoint (section 11.1): MCP Streamable HTTP, JSON-RPC 2.0.

POST only, one application/json response per request; GET -> 405;
notifications -> 202 with an empty body; token (li.mcp.token) as a Bearer header or
in the connector URL /li_sales/mcp/<token> -> 401 when missing, invalid, inactive
or expired. Tools run as the module's technical
user (group LinkedIn Sales / MCP Agent).
"""
import json
import logging
import re
import time

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.linkedin_sales_automation.models.li_mcp_tools import ToolError
from odoo.addons.linkedin_sales_automation.models.li_misc import DEFAULT_INSTRUCTIONS

_logger = logging.getLogger(__name__)

_TOKEN_IN_PATH = re.compile(r'(/li_sales/(?:mcp|post_image/\d+)/)[^\s/?"]+')


class _HideConnectorToken(logging.Filter):
    """Connector URLs and post image links hold tokens: keep them out of Odoo's request log."""

    def filter(self, record):
        if record.args and isinstance(record.args, tuple):
            record.args = tuple(_TOKEN_IN_PATH.sub(r'\1***', a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = _TOKEN_IN_PATH.sub(r'\1***', record.msg)
        return True


_werkzeug = logging.getLogger('werkzeug')
if not any(isinstance(f, _HideConnectorToken) for f in _werkzeug.filters):
    _werkzeug.addFilter(_HideConnectorToken())

SUPPORTED_VERSIONS = ('2025-06-18', '2025-03-26')
LATEST_VERSION = SUPPORTED_VERSIONS[0]
SERVER_INFO = {'name': 'odoo-linkedin-sales', 'title': 'Odoo LinkedIn Sales', 'version': '18.0.1.0.0'}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# Optional MCP methods some clients probe first; not offered, and not an error worth logging.
OPTIONAL_METHODS = {'server/discover', 'resources/list', 'resources/templates/list', 'prompts/list',
                    'completion/complete', 'logging/setLevel'}


def _rpc_error(req_id, code, message):
    return {'jsonrpc': '2.0', 'id': req_id, 'error': {'code': code, 'message': message}}


def _rpc_result(req_id, result):
    return {'jsonrpc': '2.0', 'id': req_id, 'result': result}


class LiSalesMcpController(http.Controller):

    def _json(self, payload, status=200, headers=None):
        body = json.dumps(payload, ensure_ascii=False, default=str)
        hdrs = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store')]
        hdrs += headers or []
        return request.make_response(body, headers=hdrs, status=status)

    def _empty(self, status, headers=None):
        return request.make_response('', headers=headers or [], status=status)

    def _authenticate(self, path_token=None):
        """Check the token (li.mcp.token) and switch the environment to the
        module's technical user. The token comes as a bearer header, or in the
        connector URL (/li_sales/mcp/<token>) for clients that cannot send
        headers, such as Claude's custom connectors. Returns (token, error response)."""
        auth = request.httprequest.headers.get('Authorization', '')
        scheme, _sep, plain = auth.partition(' ')
        plain = plain.strip() if scheme.lower() == 'bearer' else ''
        plain = plain or (path_token or '').strip()
        if not plain:
            return None, self._unauthorized('Missing bearer token')
        token = request.env['li.mcp.token'].sudo()._authenticate(plain)
        if not token:
            return None, self._unauthorized('Invalid, inactive or expired token')
        user = request.env['li.mcp.token']._technical_user()
        if not user.has_group('linkedin_sales_automation.group_li_mcp_agent'):
            return None, self._json(_rpc_error(None, INVALID_REQUEST,
                                               'The technical user is not in group LinkedIn Sales / MCP Agent'),
                                    status=403)
        request.update_env(user=user.id)
        request.li_mcp_token_id = token.id
        return token, None

    def _unauthorized(self, message):
        return self._json(_rpc_error(None, INVALID_REQUEST, message), status=401,
                          headers=[('WWW-Authenticate', 'Bearer realm="li_sales_mcp"')])

    @http.route(['/li_sales/mcp', '/li_sales/mcp/<string:path_token>'], type='http', auth='none',
                methods=['POST', 'GET'], csrf=False, save_session=False, readonly=False)
    def mcp(self, path_token=None, **kwargs):
        httpreq = request.httprequest
        if httpreq.method != 'POST':
            return self._empty(405, headers=[('Allow', 'POST')])
        icp = request.env['ir.config_parameter'].sudo()
        if icp.get_param('li_sales.mcp_enabled', 'True') in ('False', '0', ''):
            return self._json(_rpc_error(None, INVALID_REQUEST, 'The MCP endpoint is disabled in Settings'),
                              status=404)
        token, error = self._authenticate(path_token)
        if error:
            return error
        try:
            message = json.loads(httpreq.get_data(as_text=True) or 'null')
        except ValueError:
            return self._json(_rpc_error(None, PARSE_ERROR, 'Parse error'), status=400)

        if isinstance(message, list):  # JSON-RPC batch (protocol 2025-03-26)
            if not message:
                return self._json(_rpc_error(None, INVALID_REQUEST, 'Empty batch'), status=400)
            responses = [r for r in (self._handle(m) for m in message) if r is not None]
            return self._json(responses) if responses else self._empty(202)
        response = self._handle(message)
        if response is None:
            return self._empty(202)
        return self._json(response)

    # ------------------------------------------------------------------
    def _handle(self, message):
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or 'method' not in message:
            if isinstance(message, dict) and 'method' not in message and ('result' in message or 'error' in message):
                return None  # a client response: nothing to answer
            return _rpc_error(message.get('id') if isinstance(message, dict) else None,
                              INVALID_REQUEST, 'Invalid request')
        method = message['method']
        req_id = message.get('id')
        params = message.get('params') or {}
        is_notification = 'id' not in message
        if is_notification:
            # notifications/initialized, notifications/cancelled, ...: accepted, no body
            return None
        started = time.monotonic()
        tool = params.get('name') if method == 'tools/call' and isinstance(params, dict) else None
        ok, error_text = True, None
        try:
            if method == 'initialize':
                response = _rpc_result(req_id, self._initialize(params))
            elif method == 'ping':
                response = _rpc_result(req_id, {})
            elif method == 'tools/list':
                response = _rpc_result(req_id, {'tools': request.env['li.mcp.tools'].list_tools()})
            elif method == 'tools/call':
                response, ok, error_text = self._tools_call(req_id, params)
            elif method in ('resources/list', 'prompts/list', 'resources/templates/list'):
                key = {'resources/list': 'resources', 'prompts/list': 'prompts',
                       'resources/templates/list': 'resourceTemplates'}[method]
                response = _rpc_result(req_id, {key: []})
            elif method in OPTIONAL_METHODS:
                response = _rpc_error(req_id, METHOD_NOT_FOUND, 'Method not found: %s' % method)
            else:
                ok, error_text = False, 'Method not found: %s' % method
                response = _rpc_error(req_id, METHOD_NOT_FOUND, error_text)
        except Exception as exc:  # never leak a traceback to the client
            _logger.exception('MCP %s failed', method)
            request.env.cr.rollback()
            ok, error_text = False, str(exc)
            response = _rpc_error(req_id, INTERNAL_ERROR, 'Internal error')
        self._log(method, tool, params, started, ok, error_text)
        return response

    def _initialize(self, params):
        wanted = (params or {}).get('protocolVersion')
        version = wanted if wanted in SUPPORTED_VERSIONS else LATEST_VERSION
        instructions = request.env['ir.config_parameter'].sudo().get_param(
            'li_sales.mcp_instructions') or DEFAULT_INSTRUCTIONS
        return {
            'protocolVersion': version,
            'capabilities': {'tools': {'listChanged': False}},
            'serverInfo': SERVER_INFO,
            'instructions': instructions,
        }

    def _tools_call(self, req_id, params):
        if not isinstance(params, dict) or not isinstance(params.get('name'), str):
            return _rpc_error(req_id, INVALID_PARAMS, 'params.name is required'), False, 'no tool name'
        name = params['name']
        arguments = params.get('arguments') or {}
        tools = request.env['li.mcp.tools']
        try:
            with request.env.cr.savepoint():
                result = tools.call_tool(name, arguments)
        except ToolError as exc:
            text = str(exc)
            structured = dict(exc.data, error=text)
            return _rpc_result(req_id, {'content': [{'type': 'text', 'text': text}],
                                        'structuredContent': structured, 'isError': True}), False, text
        except Exception as exc:
            # UserError / ValidationError / AccessError and unexpected errors:
            # report a plain reason Claude can act on, changes rolled back
            if isinstance(exc, (UserError, AccessError)):
                text = exc.args[0] if exc.args else str(exc)
                _logger.info('MCP tool %s refused: %s', name, text)
            else:
                _logger.exception('MCP tool %s failed', name)
                text = 'Internal error in %s: %s' % (name, exc)
            return _rpc_result(req_id, {'content': [{'type': 'text', 'text': str(text)}],
                                        'structuredContent': {'error': str(text)}, 'isError': True}), False, str(text)
        return _rpc_result(req_id, {'content': [{'type': 'text', 'text': tools._summarize(name, result)}],
                                    'structuredContent': result, 'isError': False}), True, None

    def _log(self, method, tool, params, started, ok, error_text):
        try:
            size = len(json.dumps(params.get('arguments') if tool else params, default=str))
        except (TypeError, ValueError):
            size = 0
        request.env['li.mcp.log'].sudo().create({
            'user_id': request.env.uid,
            'method': method,
            'tool': tool,
            'args_size': size,
            'duration_ms': int((time.monotonic() - started) * 1000),
            'ok': ok,
            'error': error_text,
            'remote_addr': request.httprequest.remote_addr,
            'token_id': getattr(request, 'li_mcp_token_id', False),
        })
