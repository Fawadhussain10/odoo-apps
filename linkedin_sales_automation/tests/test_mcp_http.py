import json
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import LiCommon


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestMcpHttp(HttpCase, LiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_li()
        Token = cls.env['li.mcp.token']
        cls.token_rec, cls.key = Token._generate('Claude test')
        cls.inactive_rec, cls.inactive_key = Token._generate('Revoked')
        cls.inactive_rec.active = False
        cls.expired_rec, cls.expired_key = Token._generate('Expired', fields.Datetime.now() - timedelta(days=1))

    def post(self, payload, key=None, headers=None, url='/li_sales/mcp'):
        hdrs = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if key:
            hdrs['Authorization'] = 'Bearer %s' % key
        hdrs.update(headers or {})
        return self.url_open(url, data=json.dumps(payload), headers=hdrs)

    def rpc(self, method, params=None, req_id=1):
        resp = self.post({'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params or {}}, key=self.key)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.headers['Content-Type'].startswith('application/json'))
        return resp.json()

    def tool(self, name, **arguments):
        body = self.rpc('tools/call', {'name': name, 'arguments': arguments})
        return body['result']

    def test_optional_probes_are_answered_quietly(self):
        last_log = self.env['li.mcp.log'].search([], order='id desc', limit=1).id or 0
        body = self.rpc('server/discover')
        self.assertEqual(body['error']['code'], -32601)
        self.assertEqual(self.rpc('resources/list')['result'], {'resources': []})
        self.assertEqual(self.rpc('prompts/list')['result'], {'prompts': []})
        self.assertEqual(self.rpc('no/such')['error']['code'], -32601)
        logs = self.env['li.mcp.log'].search([('id', '>', last_log)])
        self.assertEqual(logs.filtered(lambda l: not l.ok).mapped('method'), ['no/such'])

    def test_connector_url_with_the_token_in_the_path(self):
        payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
        resp = self.post(payload, url='/li_sales/mcp/%s' % self.key)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn('li_submit_text', [t['name'] for t in resp.json()['result']['tools']])
        self.assertEqual(self.post(payload, url='/li_sales/mcp/not-a-valid-key').status_code, 401)
        self.assertEqual(self.post(payload, url='/li_sales/mcp/%s' % self.inactive_key).status_code, 401)

    def test_auth(self):
        payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
        self.assertEqual(self.post(payload).status_code, 401)
        self.assertEqual(self.post(payload, key='not-a-valid-key').status_code, 401)
        resp = self.post(payload, key=self.key[:-2] + 'zz')
        self.assertEqual(resp.status_code, 401)
        self.assertIn('Bearer', resp.headers.get('WWW-Authenticate', ''))
        self.assertEqual(self.post(payload, key=self.inactive_key).status_code, 401)
        self.assertEqual(self.post(payload, key=self.expired_key).status_code, 401)
        self.assertEqual(self.post(payload, key=self.key).status_code, 200)
        self.assertTrue(self.token_rec.last_used)
        # only a hash is stored
        self.assertNotIn(self.key, self.token_rec.token_hash)

    def test_token_not_usable_elsewhere(self):
        tech = self.tech_user
        # XML-RPC: neither the technical login nor any other login accepts the token as a password
        body = ("<?xml version='1.0'?><methodCall><methodName>authenticate</methodName><params>"
                "<param><value><string>%s</string></value></param>"
                "<param><value><string>%s</string></value></param>"
                "<param><value><string>%s</string></value></param>"
                "<param><value><struct></struct></value></param></params></methodCall>")
        for login in (tech.login, 'admin'):
            resp = self.url_open('/xmlrpc/2/common', data=body % (self.env.cr.dbname, login, self.key),
                                 headers={'Content-Type': 'text/xml'})
            self.assertIn('<boolean>0</boolean>', resp.text)
        # JSON-RPC session login
        resp = self.url_open('/web/session/authenticate', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {'db': self.env.cr.dbname, 'login': tech.login, 'password': self.key}}),
            headers={'Content-Type': 'application/json'})
        self.assertIn('error', resp.json())
        # Bearer on a regular JSON-RPC route is not accepted either
        resp = self.url_open('/web/dataset/call_kw/res.partner/search_read', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {'model': 'res.partner', 'method': 'search_read', 'args': [], 'kwargs': {'limit': 1}}}),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % self.key})
        self.assertIn('error', resp.json())

    def test_get_is_405(self):
        resp = self.url_open('/li_sales/mcp', headers={'Authorization': 'Bearer %s' % self.key})
        self.assertEqual(resp.status_code, 405)

    def test_initialize_and_notification(self):
        body = self.rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                       'clientInfo': {'name': 'test', 'version': '1'}})
        result = body['result']
        self.assertEqual(result['protocolVersion'], '2025-03-26')
        self.assertEqual(result['capabilities'], {'tools': {'listChanged': False}})
        self.assertIn('Always start with li_get_work', result['instructions'])
        self.assertIn('If li_confirm_send says wait', result['instructions'])
        self.assertEqual(result['serverInfo']['name'], 'odoo-linkedin-sales')
        body = self.rpc('initialize', {'protocolVersion': '1999-01-01'})
        self.assertEqual(body['result']['protocolVersion'], '2025-06-18')
        resp = self.post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, key=self.key)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.text, '')
        self.assertEqual(self.rpc('ping')['result'], {})

    def test_unknown_method(self):
        body = self.rpc('sampling/createMessage')
        self.assertEqual(body['error']['code'], -32601)

    def test_tools_list(self):
        tools = self.rpc('tools/list')['result']['tools']
        names = {t['name'] for t in tools}
        self.assertIn('li_get_work', names)
        self.assertNotIn('search_read', names)
        by_name = {t['name']: t for t in tools}
        self.assertTrue(by_name['li_overview']['annotations']['readOnlyHint'])
        self.assertFalse(by_name['li_report_result']['annotations']['destructiveHint'])
        self.assertEqual(by_name['li_confirm_send']['inputSchema']['required'], ['work_id'])

    def test_tools_call_result_shape_and_log(self):
        last_log = self.env['li.mcp.log'].search([], order='id desc', limit=1).id or 0
        result = self.tool('li_overview')
        self.assertFalse(result['isError'])
        self.assertEqual(result['content'][0]['type'], 'text')
        self.assertRegex(result['content'][0]['text'], r'^2 profiles, \d+ personas \(\d+ active\)\. Today: ')
        self.assertNotIn('{', result['content'][0]['text'])
        self.assertIn('profiles', result['structuredContent'])
        bad = self.tool('li_confirm_send')
        self.assertTrue(bad['isError'])
        self.assertIn('work_id is required', bad['content'][0]['text'])
        logs = self.env['li.mcp.log'].search([('tool', 'in', ('li_overview', 'li_confirm_send')),
                                              ('id', '>', last_log)])
        self.assertEqual(set(logs.mapped('ok')), {True, False})
        self.assertEqual(logs.mapped('user_id'), self.tech_user)
        self.assertEqual(logs.mapped('token_id'), self.token_rec)

    def test_full_invite_cycle(self):
        persona = self._make_persona('HTTP persona', con_send_window_from=0.0, con_send_window_to=24.0,
                                     con_delay_min=0, con_delay_max=0)
        persona.action_connection_run()
        work = self.tool('li_get_work', linkedin_profile='taha')
        self.assertFalse(work['isError'], work)
        items = work['structuredContent']['items']
        search = [i for i in items if i['type'] == 'search_prospects'][0]
        self.assertEqual(search['linkedin_profile'], 'taha')
        added = self.tool('li_add_prospects', work_id=search['work_id'], linkedin_profile='taha',
                          people=[{'name': 'Ali Raza', 'headline': 'Founder, Brand X',
                                   'linkedin_url': 'https://www.linkedin.com/in/ali-raza/', 'username': 'ali-raza'}])
        self.assertEqual(added['structuredContent']['created'], 1)
        invite = [i for i in self.tool('li_get_work', linkedin_profile='taha')['structuredContent']['items'] if i['type'] == 'invite'][0]
        self.assertEqual(invite['prospect']['username'], 'ali-raza')
        go = self.tool('li_confirm_send', work_id=invite['work_id'])
        self.assertTrue(go['structuredContent']['go'])
        self.assertEqual(go['content'][0]['text'], 'go')
        wrong = self.tool('li_report_result', work_id=invite['work_id'], status='connected',
                          linkedin_profile='rep1', retry_safe=True)
        self.assertTrue(wrong['isError'])
        done = self.tool('li_report_result', work_id=invite['work_id'], status='connected',
                         linkedin_profile='taha', retry_safe=True)
        self.assertFalse(done['isError'], done)
        prospect = self.env['li.prospect'].search([('linkedin_username', '=', 'ali-raza')])
        self.assertEqual(prospect.stage, 'invited')
        self.assertTrue(self.env['li.event'].search_count([('prospect_id', '=', prospect.id),
                                                           ('event_type', '=', 'invite_sent')]))
        self.assertIn('Connection request sent to Ali Raza', persona.message_ids[0].body)
        finish = self.tool('li_finish_run', summary='done')
        self.assertFalse(finish['isError'])
