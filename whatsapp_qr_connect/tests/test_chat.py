# -*- coding: utf-8 -*-
import importlib.util
import os
import time
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.whatsapp_qr_connect.models.whatsapp_account import WhatsappAccount

WORKER = os.path.join(os.path.dirname(__file__), '..', 'worker', 'whatsapp_worker.py')


@tagged('post_install', '-at_install')
class TestWhatsappChat(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['whatsapp.account'].search([]).unlink()
        cls.account = cls.env['whatsapp.account'].create(
            {'name': 'Sales', 'state': 'connected', 'phone': '923001111111'})
        cls.Chat = cls.env['whatsapp.chat']

    def _send(self, phone='923001234567', text='Hello', status='SENT'):
        def fake(account, mode, payload=None, timeout=90, **extra):
            return {'ok': True, 'results': [{'status': status, 'message_id': 'OUT1'}
                                            for _m in payload['messages']]}
        with patch.object(WhatsappAccount, '_run_worker', fake):
            return self.env['whatsapp.account'].send_message(phone, text)

    def _incoming(self, mid='IN1', phone='923001234567', body='Reply', **extra):
        item = {'phone': phone, 'name': 'Ali', 'message_id': mid, 'body': body,
                'media_type': '', 'timestamp': int(time.time())}
        item.update(extra)
        return item

    def test_sent_message_opens_a_chat(self):
        self._send()
        chat = self.Chat.search([('phone', '=', '923001234567')])
        self.assertEqual(len(chat), 1)
        self.assertEqual(chat.last_message_preview, 'Hello')
        self._send(text='Second')
        self.assertEqual(self.Chat.search_count([('phone', '=', '923001234567')]), 1)
        self.assertEqual(len(chat.message_ids), 2)

    def test_failed_send_opens_no_chat(self):
        self._send(phone='923009999999', status='NOT_WHATSAPP')
        self.assertFalse(self.Chat.search([('phone', '=', '923009999999')]))

    def test_incoming_is_stored_once_and_only_for_known_chats(self):
        self._send()
        self.assertEqual(self.account._process_incoming([
            self._incoming(), self._incoming(),                       # duplicate
            self._incoming('IN2', phone='923005555555')]), 1)          # stranger
        chat = self.Chat.search([('phone', '=', '923001234567')])
        self.assertEqual(chat.unread_count, 1)
        self.assertEqual(chat.contact_name, 'Ali')
        self.assertEqual(chat.name, 'Ali')
        self.assertFalse(self.Chat.search([('phone', '=', '923005555555')]))
        self.assertEqual(chat.last_message_preview, 'Reply')

    def test_local_format_chat_matches_international_reply(self):
        worker = self._worker()
        self.assertEqual(worker._match_known('923010400131', ['03010400131']), '03010400131')
        self.assertIsNone(worker._match_known('923010400132', ['03010400131']))
        self.assertIsNone(worker._match_known('', ['03010400131']))

    def _worker(self):
        spec = importlib.util.spec_from_file_location('wa_worker_match', WORKER)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        return worker

    def test_phone_typed_reply_is_outgoing_and_self_chat_reply_is_incoming(self):
        self._send('03001234567')
        chat = self.Chat.search([('phone', '=', '03001234567')])
        self.account._process_incoming([self._incoming('P1', phone='03001234567', from_me=True, body='from phone')])
        self.assertEqual(chat.unread_count, 0)
        self.assertEqual(chat.message_ids.filtered(lambda m: m.message_id == 'P1').direction, 'out')
        # the linked number chatting with itself: what you type there is the "reply"
        self._send('0300 1111111')
        self.account._process_incoming([self._incoming('S1', phone='03001111111', from_me=True, body='note')])
        self_chat = self.Chat.search([('phone', '=', '03001111111')])
        self.assertEqual(self_chat.unread_count, 1)

    def test_chat_is_shared_between_local_and_international_format(self):
        self._send('03001234567')
        self._send('923001234567')
        self.assertEqual(self.Chat.search_count([('account_id', '=', self.account.id)]), 1)

    def test_own_send_echo_is_not_duplicated(self):
        self._send()
        self.account._process_incoming([self._incoming('OUT1', from_me=True)])
        chat = self.Chat.search([('phone', '=', '923001234567')])
        self.assertEqual(len(chat.message_ids), 1)

    def test_reply_caught_while_sending_is_stored(self):
        self._send()

        def fake(account, mode, payload=None, timeout=90, **extra):
            self.assertEqual(payload['known'], ['923001234567'])
            return {'ok': True, 'results': [{'status': 'SENT', 'message_id': 'O2'}],
                    'messages': [self._incoming('CAUGHT')]}
        with patch.object(WhatsappAccount, '_run_worker', fake):
            self.env['whatsapp.account'].send_message('923001234567', 'again')
        chat = self.Chat.search([('phone', '=', '923001234567')])
        self.assertEqual(chat.unread_count, 1)

    def test_media_message_preview(self):
        self._send()
        self.account._process_incoming([self._incoming(body='', media_type='image')])
        chat = self.Chat.search([('phone', '=', '923001234567')])
        self.assertEqual(chat.last_message_preview, '[image]')

    def test_open_chat_marks_read_and_poll_reports_new(self):
        self._send()
        self.account._process_incoming([self._incoming()])
        chat = self.Chat.search([('phone', '=', '923001234567')])
        poll = self.Chat.poll(0)
        self.assertEqual(poll['unread'], 1)
        self.assertEqual(poll['new'][0]['chat_id'], chat.id)
        self.assertEqual(self.Chat.poll(poll['last_id'])['new'], [])
        data = chat.get_messages()
        self.assertEqual([m['direction'] for m in data['messages']], ['out', 'in'])
        self.assertEqual(chat.unread_count, 0)
        self.assertEqual(self.Chat.get_chats()['unread'], 0)

    def test_reply_sends_from_the_chat_account(self):
        self._send()
        chat = self.Chat.search([('phone', '=', '923001234567')])
        calls = []

        def fake(account, mode, payload=None, timeout=90, **extra):
            calls.append((account, payload))
            return {'ok': True, 'results': [{'status': 'SENT', 'message_id': 'R1'}]}
        with patch.object(WhatsappAccount, '_run_worker', fake):
            data = chat.send_reply('  Thanks  ')
            with self.assertRaises(UserError):
                chat.send_reply('   ')
        self.assertEqual(calls[0][0], self.account)
        self.assertEqual(calls[0][1]['messages'][0]['text'], 'Thanks')
        self.assertEqual(data['messages'][-1]['body'], 'Thanks')

    def test_receive_streams_messages_from_the_worker(self):
        self._send()
        seen = []

        def fake(account, mode, payload, timeout, on_message):
            seen.append((mode, payload))
            on_message(self._incoming('R9'))
            on_message(self._incoming('R10', body='second'))
            return {'ok': True}
        with patch.object(WhatsappAccount, '_stream_worker', fake):
            self.assertEqual(self.env['whatsapp.chat'].refresh_inbox(), {'received': 2})
        self.assertEqual(seen[0][0], 'receive')
        self.assertEqual(seen[0][1]['known'], ['923001234567'])
        # the session lock taken for listening is released again
        self.env.cr.execute("SELECT pg_try_advisory_lock(%s)", [0x57410000 + self.account.id])
        self.assertTrue(self.env.cr.fetchone()[0])

    def test_sending_asks_the_listener_to_release_the_session(self):
        with patch.object(WhatsappAccount, '_request_listener_stop', autospec=True) as stop:
            self._send()
        self.assertEqual(stop.call_args[0][0], self.account)

    def test_new_reply_is_pushed_over_the_bus(self):
        self._send()
        before = self.env['bus.bus'].sudo().search_count([])
        self.account._process_incoming([self._incoming('BUS1')])
        self.env.cr.precommit.run()
        pushed = self.env['bus.bus'].sudo().search([('id', '>', 0)], order='id desc', limit=5)
        self.assertGreater(self.env['bus.bus'].sudo().search_count([]), before)
        self.assertTrue(any('whatsapp_qr_connect.new_message' in (n.message or '') for n in pushed))

    def test_reply_with_picture_and_pdf(self):
        self._send()
        chat = self.Chat.search([('phone', '=', '923001234567')])
        calls = []

        def fake(account, mode, payload=None, timeout=90, **extra):
            calls.append(payload)
            return {'ok': True, 'results': [{'status': 'SENT', 'message_id': 'A%s' % i}
                                            for i, _m in enumerate(payload['messages'])]}
        import base64
        with patch.object(WhatsappAccount, '_run_worker', fake):
            data = chat.send_reply('Look \U0001F600', [
                {'name': 'pic.png', 'mimetype': 'image/png', 'data': base64.b64encode(self.PNG).decode()},
                {'name': 'doc.pdf', 'mimetype': 'application/pdf', 'data': base64.b64encode(b'%PDF-1.4').decode()}])
            with self.assertRaises(UserError):
                chat.send_reply('', [{'name': 'big.bin', 'mimetype': 'x/y', 'data': base64.b64encode(
                    b'x' * (16 * 1024 * 1024 + 1)).decode()}])
        msgs = calls[0]['messages']
        self.assertEqual(msgs[0]['text'], 'Look \U0001F600')        # caption on the first file
        self.assertEqual(msgs[1]['text'], '')
        self.assertTrue(all(m['attachment']['as_media'] for m in msgs))
        self.assertEqual(msgs[0]['attachment']['mimetype'], 'image/png')
        files = [m['file'] for m in data['messages'] if m['direction'] == 'out' and m['file']]
        self.assertEqual({f['mimetype'] for f in files}, {'image/png', 'application/pdf'})

    def test_receive_skips_accounts_without_chats(self):
        with patch.object(WhatsappAccount, '_stream_worker', side_effect=AssertionError('no chats')):
            self.assertEqual(self.account._receive_messages(), 0)

    def test_cron_is_installed(self):
        cron = self.env.ref('whatsapp_qr_connect.cron_whatsapp_receive')
        self.assertTrue(cron.active)

    def test_portal_user_has_no_access(self):
        portal = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'P', 'login': 'wa_portal',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        with self.assertRaises(AccessError):
            self.Chat.with_user(portal).get_chats()

    def test_only_the_chat_group_can_use_the_screen(self):
        self._send()
        Users = self.env['res.users'].with_context(no_reset_password=True)
        internal = self.env.ref('base.group_user')
        chat_group = self.env.ref('whatsapp_qr_connect.group_whatsapp_chat')
        plain = Users.create({'name': 'I', 'login': 'wa_plain', 'group_ids': [(6, 0, [internal.id])]})
        member = Users.create({'name': 'M', 'login': 'wa_member',
                               'group_ids': [(6, 0, [internal.id, chat_group.id])]})
        with self.assertRaises(AccessError):
            self.Chat.with_user(plain).get_chats()
        with self.assertRaises(AccessError):
            self.Chat.with_user(plain).poll(0)
        self.assertEqual(len(self.Chat.with_user(member).get_chats()['chats']), 1)
        # the menu is bound to the group; administrators get the group automatically
        menu = self.env.ref('whatsapp_qr_connect.menu_whatsapp_inbox_app')
        self.assertEqual(menu.group_ids, chat_group)
        self.assertIn(chat_group, self.env.ref('base.group_system').implied_ids)
        admin = Users.create({'name': 'Adm', 'login': 'wa_admin',
                              'group_ids': [(6, 0, [self.env.ref('base.group_system').id])]})
        self.assertEqual(len(self.Chat.with_user(admin).get_chats()['chats']), 1)
        # replies are pushed only to group members
        self.env['bus.bus'].sudo().search([]).unlink()
        self.account._process_incoming([self._incoming('GRP1')])
        self.env.cr.precommit.run()
        targets = ' '.join(self.env['bus.bus'].sudo().search([]).mapped('channel'))
        self.assertIn('"res.users",%d]' % member.id, targets)
        self.assertNotIn('"res.users",%d]' % plain.id, targets)

    PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
           b'\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0'
           b'\x00\x00\x00\x00IEND\xaeB`\x82')

    def test_incoming_image_is_stored_and_served(self):
        import tempfile
        self._send()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'IMG1')
            with open(path, 'wb') as fh:
                fh.write(self.PNG)
            self.account._process_incoming([self._incoming(
                'IMG1', body='look', media_type='image',
                media={'path': path, 'mimetype': 'image/png', 'filename': 'pic.png'})])
        chat = self.Chat.search([('phone', '=', '923001234567')])
        msg = chat.message_ids.filtered(lambda m: m.direction == 'in')
        self.assertEqual(msg.attachment_id.raw, self.PNG)
        self.assertEqual((msg.attachment_id.res_model, msg.attachment_id.res_id), ('whatsapp.message', msg.id))
        data = chat.get_messages()
        file = [m for m in data['messages'] if m['direction'] == 'in'][0]['file']
        self.assertEqual((file['id'], file['mimetype']), (msg.attachment_id.id, 'image/png'))
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'I2', 'login': 'wa_internal2',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('whatsapp_qr_connect.group_whatsapp_chat').id])]})
        self.assertEqual(msg.attachment_id.with_user(user).raw, self.PNG)

    def test_worker_downloads_media(self):
        try:
            from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message as E2E
        except Exception:
            self.skipTest('neonize protobuf classes unavailable in this Python')
        import tempfile
        spec = importlib.util.spec_from_file_location('wa_worker_media', WORKER)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        jid = SimpleNamespace(User='923001234567', Server='s.whatsapp.net')
        empty = SimpleNamespace(User='', Server='')
        src = SimpleNamespace(IsFromMe=False, IsGroup=False, SenderAlt=empty, Sender=jid, Chat=jid)
        info = SimpleNamespace(MessageSource=src, ID='M/1', Pushname='', Timestamp=1_700_000_000)
        msg = E2E()
        msg.imageMessage.mimetype = 'image/jpeg'
        msg.imageMessage.caption = 'c'
        client = SimpleNamespace(download_any=lambda m: b'JPEGDATA')
        with tempfile.TemporaryDirectory() as tmp:
            item = worker._incoming_from_event(
                client, SimpleNamespace(Info=info, Message=msg), {'923001234567'}, tmp)
            self.assertEqual(item['media']['mimetype'], 'image/jpeg')
            self.assertTrue(item['media']['filename'].endswith('.jpg') or item['media']['filename'].endswith('.jpeg'))
            with open(item['media']['path'], 'rb') as fh:
                self.assertEqual(fh.read(), b'JPEGDATA')
            # a failing download keeps the message, without the file
            def boom(_m):
                raise RuntimeError('x')
            item = worker._incoming_from_event(
                SimpleNamespace(download_any=boom), SimpleNamespace(Info=info, Message=msg),
                {'923001234567'}, tmp)
            self.assertIsNone(item['media'])
            self.assertEqual(item['media_type'], 'image')

    # ------------------------------------------------------------ worker event parsing
    def test_worker_parses_events(self):
        try:
            from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message as E2E
        except Exception:
            self.skipTest('neonize protobuf classes unavailable in this Python')
        spec = importlib.util.spec_from_file_location('wa_worker_test', WORKER)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)

        def event(msg, me=False, group=False, sender='923001234567', server='s.whatsapp.net'):
            jid = SimpleNamespace(User=sender, Server=server)
            empty = SimpleNamespace(User='', Server='')
            src = SimpleNamespace(IsFromMe=me, IsGroup=group, SenderAlt=empty, Sender=jid, Chat=jid)
            info = SimpleNamespace(MessageSource=src, ID='X1', Pushname='Ali', Timestamp=1_700_000_000_000)
            return SimpleNamespace(Info=info, Message=msg)

        known = {'923001234567'}
        text = worker._incoming_from_event(None, event(E2E(conversation='hi')), known)
        self.assertEqual((text['body'], text['phone'], text['timestamp']), ('hi', '923001234567', 1_700_000_000))
        ext = E2E()
        ext.extendedTextMessage.text = 'long'
        self.assertEqual(worker._incoming_from_event(None, event(ext), known)['body'], 'long')
        img = E2E()
        img.imageMessage.caption = 'look'
        got = worker._incoming_from_event(None, event(img), known)
        self.assertEqual((got['media_type'], got['body']), ('image', 'look'))
        self.assertTrue(worker._incoming_from_event(None, event(E2E(conversation='x'), me=True), known)['from_me'])
        self.assertIsNone(worker._incoming_from_event(None, event(E2E(conversation='x'), group=True), known))
        self.assertIsNone(worker._incoming_from_event(None, event(E2E(conversation='x'), sender='923009999999'), known))
        self.assertIsNone(worker._incoming_from_event(None, event(E2E()), known))   # nothing usable
