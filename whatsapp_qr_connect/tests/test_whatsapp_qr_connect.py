# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.whatsapp_qr_connect.models.whatsapp_account import WhatsappAccount


@tagged('post_install', '-at_install')
class TestWhatsappQrConnect(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['whatsapp.account']
        cls.acc_a = Account.create({'name': 'Sales', 'state': 'connected', 'phone': '923001111111'})
        cls.acc_b = Account.create({'name': 'Support', 'state': 'connected', 'phone': '923002222222'})
        cls.acc_off = Account.create({'name': 'Unlinked'})

    def _fake_worker(self, statuses=None):
        calls = []

        def fake(account, mode, payload=None, timeout=90, **extra):
            calls.append((account, mode, payload))
            msgs = (payload or {}).get('messages', [])
            results = [{'status': (statuses or {}).get(m['to'], 'SENT'),
                        'message_id': 'ID%s' % i} for i, m in enumerate(msgs)]
            return {'ok': True, 'results': results}
        return calls, patch.object(WhatsappAccount, '_run_worker', fake)

    def test_normalize_phone(self):
        norm = self.env['whatsapp.account']._normalize_phone
        self.assertEqual(norm('+92 300-1234567'), '923001234567')
        self.assertEqual(norm('00923001234567'), '923001234567')
        self.assertIsNone(norm('123'))
        self.assertIsNone(norm(''))
        self.env['ir.config_parameter'].set_param('whatsapp_qr_connect.default_country_code', '92')
        self.assertEqual(norm('0300 1234567'), '923001234567')

    def test_default_account_used_when_none_given(self):
        self.acc_b.is_default = True
        calls, ctx = self._fake_worker()
        with ctx:
            res = self.env['whatsapp.account'].send_message('923009999999', 'hi')
        self.assertEqual(res['status'], 'SENT')
        self.assertEqual(calls[0][0], self.acc_b)
        self.assertEqual(res['account_id'], self.acc_b.id)

    def test_explicit_account(self):
        calls, ctx = self._fake_worker()
        with ctx:
            self.env['whatsapp.account'].send_message('923009999999', 'hi', account=self.acc_a)
        self.assertEqual(calls[0][0], self.acc_a)

    def test_unlinked_account_rejected(self):
        with self.assertRaises(UserError):
            self.env['whatsapp.account'].send_message('923009999999', 'hi', account=self.acc_off)

    def test_no_linked_account(self):
        self.env['whatsapp.account'].search([]).write({'state': 'draft'})
        with self.assertRaises(UserError):
            self.env['whatsapp.account'].send_message('923009999999', 'hi')

    def test_invalid_phone_and_empty_message_do_not_reach_worker(self):
        calls, ctx = self._fake_worker()
        with ctx:
            res = self.env['whatsapp.account'].send_messages([
                {'phone': '12', 'message': 'x'},
                {'phone': '923009999999', 'message': '   '},
                {'phone': '923008888888', 'message': 'ok'},
            ])
        self.assertEqual([r['status'] for r in res], ['INVALID_PHONE', 'ERROR', 'SENT'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0][2]['messages']), 1)  # one connection, one message

    def test_batch_uses_single_worker_call_and_logs(self):
        calls, ctx = self._fake_worker({'923008888888': 'NOT_WHATSAPP'})
        with ctx:
            res = self.env['whatsapp.account'].send_messages([
                {'phone': '923007777777', 'message': 'a', 'res_model': 'res.partner', 'res_id': 5},
                {'phone': '923008888888', 'message': 'b'},
            ], account=self.acc_a)
        self.assertEqual(len(calls), 1)
        self.assertEqual([r['status'] for r in res], ['SENT', 'NOT_WHATSAPP'])
        logs = self.env['whatsapp.message'].search([('account_id', '=', self.acc_a.id)],
                                                    order='id')
        self.assertEqual(logs.mapped('status'), ['SENT', 'NOT_WHATSAPP'])
        self.assertEqual(logs[0].res_model, 'res.partner')
        self.assertEqual(self.acc_a.message_count, 2)

    def test_worker_failure_is_reported(self):
        def failing(account, mode, payload=None, timeout=90, **extra):
            return {'ok': False, 'code': 'NOT_LINKED', 'error': 'gone'}
        with patch.object(WhatsappAccount, '_run_worker', failing):
            res = self.env['whatsapp.account'].send_message('923009999999', 'hi', account=self.acc_a)
            self.assertEqual(res['status'], 'NOT_LINKED')
            with self.assertRaises(UserError):
                self.env['whatsapp.account'].send_message(
                    '923009999999', 'hi', account=self.acc_a, raise_on_error=True)

    def test_action_send_message_asks_which_number_when_several(self):
        action = self.env['whatsapp.account'].action_send_message('923009999999', 'hello')
        self.assertEqual(action['res_model'], 'whatsapp.send.wizard')
        self.assertEqual(action['context']['default_phone'], '923009999999')

    def test_action_send_message_sends_directly_with_single_number(self):
        self.acc_b.state = 'draft'
        calls, ctx = self._fake_worker()
        with ctx:
            action = self.env['whatsapp.account'].action_send_message('923009999999', 'hello')
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(calls[0][0], self.acc_a)

    def test_wizard_sends_from_chosen_number(self):
        calls, ctx = self._fake_worker()
        wizard = self.env['whatsapp.send.wizard'].create({
            'account_id': self.acc_b.id, 'phone': '923009999999', 'message': 'hi'})
        with ctx:
            action = wizard.action_send()
        self.assertEqual(calls[0][0], self.acc_b)
        self.assertEqual(action['params']['type'], 'success')

    def test_open_accounts_creates_and_links_when_nothing_linked(self):
        self.env['whatsapp.account'].search([]).unlink()
        started = []
        with patch.object(WhatsappAccount, '_spawn_link_worker', lambda self: started.append(self.id)), \
                patch.object(WhatsappAccount, '_check_worker_python', lambda self: None), \
                patch.object(type(self.env.cr), 'commit', lambda self: None):
            action = self.env['whatsapp.account'].action_open_accounts()
        self.assertEqual(action['tag'], 'whatsapp_qr_connect.link_action')
        self.assertEqual(len(started), 1)
        account = self.env['whatsapp.account'].browse(action['params']['account_id'])
        self.assertEqual(account.state, 'linking')

    def test_list_header_button_call_shape(self):
        """The list button reaches the server as call_button(model, method, [[]])."""
        from odoo.api import call_kw
        started = []
        with patch.object(WhatsappAccount, '_spawn_link_worker', lambda self: started.append(self.id)), \
                patch.object(WhatsappAccount, '_check_worker_python', lambda self: None):
            action = call_kw(self.env['whatsapp.account'], 'action_new_number', [[]], {})
        self.assertEqual(action['tag'], 'whatsapp_qr_connect.link_action')
        self.assertEqual(len(started), 1)

    def test_open_accounts_lists_when_linked(self):
        action = self.env['whatsapp.account'].action_open_accounts()
        self.assertEqual(action['res_model'], 'whatsapp.account')

    def test_link_status_returns_qr_png(self):
        self.acc_off.sudo().write({'state': 'linking', 'qr_string': 'https://wa.me/settings/linked_devices#2@abc',
                                   'link_pid': os_getpid()})
        data = self.acc_off.get_link_status()
        self.assertEqual(data['state'], 'linking')
        import base64
        self.assertEqual(base64.b64decode(data['qr_image'])[:8], b'\x89PNG\r\n\x1a\n')

    def test_qr_image_does_not_need_reportlab_backend(self):
        """The server may lack rlPyCairo, so the QR must not go through
        ir.actions.report.barcode()."""
        self.acc_off.sudo().write({'state': 'linking', 'qr_string': 'https://wa.me/x#2@abc',
                                   'link_pid': os_getpid()})
        with patch.object(type(self.env['ir.actions.report']), 'barcode',
                          side_effect=AssertionError('reportlab backend used')):
            data = self.acc_off.get_link_status()
        self.assertTrue(data['qr_image'])

    def test_dead_link_worker_is_reset(self):
        self.acc_off.sudo().write({'state': 'linking', 'link_pid': 2 ** 22 - 3})
        data = self.acc_off.get_link_status()
        self.assertEqual(data['state'], 'draft')
        self.assertTrue(data['error'])

    def test_non_admin_cannot_manage_but_internal_can_send(self):
        user = self.env['res.users'].create({
            'name': 'Plain User', 'login': 'plain_wa', 'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        Account = self.env['whatsapp.account'].with_user(user)
        with self.assertRaises(AccessError):
            Account.action_new_number()
        with self.assertRaises(AccessError):
            self.acc_a.with_user(user).action_link()
        calls, ctx = self._fake_worker()
        with ctx:
            res = Account.send_message('923009999999', 'hi', account=self.acc_a.id)
        self.assertEqual(res['status'], 'SENT')
        with self.assertRaises(AccessError):
            self.acc_a.with_user(user).session_data  # noqa: B018 - protected field

    def test_portal_user_cannot_send(self):
        portal = self.env['res.users'].create({
            'name': 'Portal', 'login': 'portal_wa',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        with self.assertRaises(AccessError):
            self.env['whatsapp.account'].with_user(portal).send_message('923009999999', 'hi')


def os_getpid():
    import os
    return os.getpid()


@tagged('post_install', '-at_install')
class TestWorkerPython(TransactionCase):

    def test_unstartable_interpreter_gives_clear_message(self):
        self.env['ir.config_parameter'].set_param(
            'whatsapp_qr_connect.python_path', '/nonexistent/python')
        account = self.env['whatsapp.account'].create({'name': 'X'})
        with self.assertRaisesRegex(UserError, 'cannot be started'):
            account.action_link()
        self.assertEqual(account.state, 'draft')

    def test_interpreter_without_neonize_is_reported(self):
        # /bin/false exits non-zero for any arguments: stands in for "import fails"
        self.env['ir.config_parameter'].set_param('whatsapp_qr_connect.python_path', '/bin/false')
        account = self.env['whatsapp.account'].create({'name': 'Y'})
        with self.assertRaisesRegex(UserError, "neonize"):
            account.action_link()
        self.assertEqual(account.state, 'draft')
