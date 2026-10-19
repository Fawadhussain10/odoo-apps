import base64
import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import freeze_time, tagged

from .test_background import MONDAY_10_UTC, BackgroundCase, thread_data
from ..models.li_mcp_tools import ToolError

PNG = base64.b64encode(bytes.fromhex(
    '89504e470d0a1a0a0000000d4948445200000001000000010806000000'
    '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082'))

ENGLISH_PROFILE = ('Harvey Reid\nFounder at Example Ltd\nLondon, England, United Kingdom\nContact info\n'
                   '500+ connections\nOpen to\nAdd profile section\nMore\nAbout\nI help brands sell more.')
FRENCH_PROFILE = ('Harvey Reid\nFondateur chez Example Ltd\nLondres, Angleterre, Royaume-Uni\nCoordonnées\n'
                  '500+ relations\nDisponible pour\nAjouter une section\nPlus\nInfos\nJ\'aide les marques.')


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestWritingItems(BackgroundCase):
    """Built-in engine profiles: Claude only writes; Odoo queues and sends."""

    def _items(self, kind=None, account='taha'):
        items = self.call('li_get_work', linkedin_profile=account)['items']
        return [i for i in items if not kind or i['type'] == kind]

    @freeze_time(MONDAY_10_UTC)
    def test_writing_items_carry_context_and_no_browser_steps(self):
        persona = self._persona(run=('connection', 'chat'), con_send_note=True,
                                con_note_instructions='Mention their brand.')
        queued = self._prospect(persona, company='Brand X')
        accepted = self._accepted(persona, username='sara-khan', name='Sara Khan')
        self.env['li.post'].create({'name': 'Stock sync', 'linkedin_profile_id': self.profile.id,
                                    'idea': 'Why stock sync matters'})
        items = self._items()
        kinds = {i['type'] for i in items}
        self.assertTrue({'invite_note', 'message', 'post_draft'} <= kinds, kinds)
        note = [i for i in items if i['type'] == 'invite_note'][0]
        self.assertEqual(note['prospect']['id'], queued.id)
        self.assertEqual(note['report_with'], 'li_submit_text')
        self.assertIn('Mention their brand.', note['instructions'])
        self.assertIn('One paragraph, no line breaks.', note['instructions'])
        message = [i for i in items if i['type'] == 'message'][0]
        self.assertEqual(message['prospect']['id'], accepted.id)
        self.assertIn('conversation', message)
        self.assertEqual(message['persona']['name'], persona.name)
        for item in items:
            self.assertNotIn('Chrome', item['instructions'])
            self.assertNotIn('li_confirm_send', item['instructions'])
        # handed out once: the same prospect does not come back while the item is open
        self.assertFalse([i for i in self._items() if i['type'] in ('invite_note', 'message')])
        # writing items reserve no quota
        self.assertFalse(self.env['li.work.item'].search([('writing', '=', True), ('quota_consumed', '=', True)]))

    @freeze_time(MONDAY_10_UTC)
    def test_submit_text_queues_and_engine_sends(self):
        self._start()
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona)
        item = self._items('message')[0]
        result = self.call('li_submit_text', work_id=item['work_id'], text='Hi Ali,\nthanks for connecting!')
        self.assertTrue(result['queued'])
        self.assertEqual(result['send_window'], 'now')
        work = self.env['li.work.item'].browse(item['work_id'])
        self.assertEqual((work.state, work.text_confirmed), ('queued', 'Hi Ali, thanks for connecting!'))
        self._script(get_conversation=[thread_data('')])
        self._run()
        self.assertEqual(self._calls(tool='send_message')[0]['args']['message'], 'Hi Ali, thanks for connecting!')
        self.assertEqual((work.state, prospect.stage), ('done', 'messaged'))
        with self.assertRaisesRegex(ToolError, 'done'):
            self.call('li_submit_text', work_id=item['work_id'], text='again')

    @freeze_time(MONDAY_10_UTC)
    def test_queued_text_can_be_replaced_until_it_is_sent(self):
        self._start()
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona)
        item = self._items('message')[0]
        self.assertIn('"Salam" and their first name when their name is a Muslim name', item['instructions'])
        self.call('li_submit_text', work_id=item['work_id'], text='Salam Ali, thanks for connecting!')
        work = self.env['li.work.item'].browse(item['work_id'])
        # li_sending_status lists the queued text with its work_id
        status = self.call('li_sending_status', linkedin_profile='taha')
        queued = status['personas'][0]['queued_texts']
        self.assertEqual([(q['work_id'], q['name'], q['text']) for q in queued],
                         [(work.id, 'Ali Raza', 'Salam Ali, thanks for connecting!')])
        # an invalid correction leaves the queued text as it was
        with self.assertRaisesRegex(ToolError, 'Not changed: fill the placeholders'):
            self.call('li_submit_text', work_id=work.id, text='Hi {first_name}!')
        self.assertEqual(work.text_confirmed, 'Salam Ali, thanks for connecting!')
        result = self.call('li_submit_text', work_id=work.id, text='Hi Ali,\nthanks for connecting!')
        self.assertTrue(result['replaced'])
        self.assertEqual((work.state, work.text_confirmed), ('queued', 'Hi Ali, thanks for connecting!'))
        self.assertIn('Salam Ali, thanks for connecting!', prospect.message_ids[0].body)
        self._script(get_conversation=[thread_data('')])
        self._run()
        self.assertEqual([c['args']['message'] for c in self._calls(tool='send_message')],
                         ['Hi Ali, thanks for connecting!'])
        self.assertEqual(work.state, 'done')
        self.assertFalse(self.call('li_sending_status', linkedin_profile='taha')['personas'][0]['queued_texts'])
        with self.assertRaisesRegex(ToolError, 'done'):
            self.call('li_submit_text', work_id=work.id, text='Hello Ali')

    @freeze_time(MONDAY_10_UTC)
    def test_text_being_sent_cannot_be_replaced(self):
        persona = self._persona(run=('chat',))
        self._accepted(persona)
        item = self._items('message')[0]
        self.call('li_submit_text', work_id=item['work_id'], text='Hi Ali, thanks for connecting!')
        self.env['li.work.item'].browse(item['work_id']).state = 'sending'
        with self.assertRaisesRegex(ToolError, 'being sent right now'):
            self.call('li_submit_text', work_id=item['work_id'], text='Hello Ali, thanks for connecting!')

    @freeze_time(MONDAY_10_UTC)
    def test_history_comes_first_and_a_repeat_is_refused(self):
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona)
        Message = self.env['li.message']
        Message.create({'prospect_id': prospect.id, 'direction': 'out', 'kind': 'message', 'ai_generated': True,
                        'state': 'sent', 'body': 'Hi Ali, thanks for connecting! Always good to meet founders.'})
        Message.create({'prospect_id': prospect.id, 'direction': 'in', 'kind': 'reply',
                        'body': 'Thanks. We run on Shopify and spreadsheets.'})
        prospect.write({'last_sentiment': 'positive', 'ai_summary': 'Runs on Shopify.'})
        item = self._items('message')[0]
        # the item says where the conversation stands, and tells Claude to read all of it first
        self.assertEqual(item['situation']['last_message_from'], 'prospect')
        self.assertEqual(item['situation']['their_last_reply'], 'Thanks. We run on Shopify and spreadsheets.')
        self.assertEqual((item['situation']['messages_from_us'], item['situation']['summary_so_far']),
                         (1, 'Runs on Shopify.'))
        self.assertIn('read the whole conversation', item['instructions'])
        self.assertIn('Never repeat a sentence', item['instructions'])
        # a text we already sent to this person is not queued again
        with self.assertRaisesRegex(ToolError, 'repeats a message already sent to Ali Raza'):
            self.call('li_submit_text', work_id=item['work_id'],
                      text='Hi Ali, thanks for connecting!  Always good to meet founders')
        result = self.call('li_submit_text', work_id=item['work_id'],
                           text='Good to know, Ali. Which part of the spreadsheets takes your team the most time?')
        self.assertTrue(result['queued'])

    @freeze_time(MONDAY_10_UTC)
    def test_prospect_who_writes_first_is_answered_soon(self):
        persona = self._persona(run=('chat',), chat_first_message_delay=2)
        prospect = self._accepted(persona)
        self.assertEqual(self._items('message'), [])                    # normally: 2 hours after accept
        self.env['li.message'].create({'prospect_id': prospect.id, 'direction': 'in', 'kind': 'reply',
                                       'body': 'Hi, what exactly do you offer for Odoo?'})
        prospect.write({'last_inbound_date': fields.Datetime.now(), 'needs_analysis': True})
        step = persona.chat_step_ids.sorted('sequence')[0]
        self.assertEqual(self.Tools._step_due(prospect, step, fields.Datetime.now() + timedelta(hours=1)),
                         (False, 'reply not analysed yet'))             # Claude analyses their message first
        prospect.needs_analysis = False
        with freeze_time('2026-10-12 10:05:00'):
            self.assertEqual(self._items('message'), [])                # 10 minutes after their message
        with freeze_time('2026-10-12 10:11:00'):
            item = self._items('message')[0]
        self.assertTrue(item['situation']['prospect_wrote_first'])
        self.assertIn('wrote to us before our first message', item['instructions'])
        self.assertIn('Do not send the template as if they had not written', item['instructions'])

    def _replied(self, persona, text, **vals):
        """A prospect who got step 1 and answered it (analysed)."""
        prospect = self._accepted(persona, **vals)
        Message = self.env['li.message']
        Message.create({'prospect_id': prospect.id, 'direction': 'out', 'kind': 'message', 'ai_generated': True,
                        'state': 'sent', 'body': 'Hi Ali, thanks for connecting!',
                        'date': fields.Datetime.now() - timedelta(hours=3)})
        Message.create({'prospect_id': prospect.id, 'direction': 'in', 'kind': 'reply', 'body': text,
                        'date': fields.Datetime.now() - timedelta(hours=1)})
        prospect.write({'stage': 'replied', 'current_step_id': persona.chat_step_ids.sorted('sequence')[0].id,
                        'last_outbound_date': fields.Datetime.now() - timedelta(hours=3),
                        'last_inbound_date': fields.Datetime.now() - timedelta(hours=1),
                        'awaiting_reply': False, 'needs_analysis': False})
        return prospect

    @freeze_time(MONDAY_10_UTC)
    def test_answer_only_keeps_the_questionnaire_step_open(self):
        self._start()
        persona = self._persona(run=('chat',))
        prospect = self._replied(persona, 'Thanks. What exactly do you do for Odoo users?')
        first, second = persona.chat_step_ids.sorted('sequence')[:2]
        item = self._items('message')[0]
        self.assertEqual(item['step']['name'], second.name)
        self.assertIn('Decide what their last message needs', item['instructions'])
        self.assertIn('step_done', item['instructions'])
        self.call('li_submit_text', work_id=item['work_id'], step_done=False,
                  text='We implement and support Odoo for growing companies, Ali: setup, accounting and custom apps.')
        self._script(get_conversation=[thread_data('')])
        self._run()
        self.assertEqual(prospect.current_step_id, first)              # step 2 was not asked: still open
        self.assertEqual(prospect.stage, 'messaged')
        self.assertTrue(prospect.awaiting_reply)
        self.assertEqual(self._items('message'), [])                   # their turn
        # they answer: the same step comes back
        self.env['li.message'].create({'prospect_id': prospect.id, 'direction': 'in', 'kind': 'reply',
                                       'body': 'Good to know.'})
        prospect.write({'last_inbound_date': fields.Datetime.now(), 'awaiting_reply': False, 'stage': 'replied'})
        self.assertEqual(self._items('message')[0]['step']['name'], second.name)

    @freeze_time(MONDAY_10_UTC)
    def test_question_is_answered_now_even_when_the_next_step_waits(self):
        self._start()
        persona = self._persona(run=('chat',))
        first, second = persona.chat_step_ids.sorted('sequence')[:2]
        second.wait_days = 1                                           # next step: a day after their reply
        prospect = self._replied(persona, 'What are the services you are offering?')
        item = self._items('message')[0]                               # not tomorrow: now
        self.assertNotIn('step', item)
        self.assertIn('expects an answer now', item['instructions'])
        self.assertIn('Do not ask the next questionnaire question', item['instructions'])
        self.call('li_submit_text', work_id=item['work_id'],
                  text='We implement, customise and support Odoo, Ali. Would any of that help you right now?')
        self._script(get_conversation=[thread_data('')])
        self._run()
        self.assertEqual(len(self._calls(tool='send_message')), 1)     # really sent, although it has no step
        self.assertEqual(prospect.current_step_id, first)              # the questionnaire did not move
        self.assertTrue(prospect.awaiting_reply)
        self.assertEqual(self._items('message'), [])

    @freeze_time(MONDAY_10_UTC)
    def test_plain_answer_waits_for_the_step_unless_the_analysis_says_reply_now(self):
        persona = self._persona(run=('chat',))
        persona.chat_step_ids.sorted('sequence')[1].wait_days = 1
        prospect = self._replied(persona, 'We use spreadsheets for everything.')
        self.assertEqual(self._items('message'), [])                   # an answer, no question: the step waits
        prospect.answer_due = True                                     # li_record_analysis reply_now=true
        self.assertIn('expects an answer now', self._items('message')[0]['instructions'])

    @freeze_time(MONDAY_10_UTC)
    def test_not_interested_gets_one_warm_closing_message(self):
        self._start()
        persona = self._persona(run=('chat',))
        prospect = self._replied(persona, 'I am fine, I do not need anything.')
        prospect.write({'stage': 'not_interested', 'sequence_stopped': True, 'closing_pending': True})
        item = self._items('message')[0]
        self.assertIn('Write one warm last message', item['instructions'])
        self.call('li_submit_text', work_id=item['work_id'],
                  text='Good to hear, Ali. Best of luck with your projects, and we are around if you ever need Odoo help.')
        self._script(get_conversation=[thread_data('')])
        self._run()
        self.assertEqual(len(self._calls(tool='send_message')), 1)
        self.assertEqual((prospect.stage, prospect.closing_pending, prospect.awaiting_reply),
                         ('not_interested', False, False))
        self.assertEqual(self._items('message'), [])                   # one closing message, never a second

    @freeze_time(MONDAY_10_UTC)
    def test_reply_after_not_interested_is_analysed_and_closed_only_once(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        persona = self._persona(run=('chat',))
        prospect = self._replied(persona, 'I am fine, I do not need anything.')
        prospect.write({'stage': 'not_interested', 'sequence_stopped': True, 'closing_pending': True})
        item = self._items('message')[0]
        self.call('li_submit_text', work_id=item['work_id'], text='Good to hear, Ali. Best of luck with it all.')
        closing = self.env['li.work.item'].browse(item['work_id'])
        # they write again before the closing message went out: it is dropped and the reply is analysed
        self.Tools._record_thread(self.profile, prospect, [
            {'sender_name': 'Ali Raza', 'text': 'Actually, what would it cost for ten users?'}])
        self.assertEqual((closing.state, closing.discarded_stale), ('cancelled', True))
        self.assertEqual((prospect.stage, prospect.closing_pending, prospect.sequence_stopped,
                          prospect.needs_analysis), ('replied', False, False, True))
        analyse = self._items('analyse')[0]
        self.assertEqual(analyse['prospect']['id'], prospect.id)
        # still not interested: closed again, with the closing message that was never sent
        self.call('li_record_analysis', work_id=analyse['work_id'], sentiment='negative', pivot=False,
                  summary='Asked the price out of curiosity, no need.')
        self.assertEqual((prospect.stage, prospect.closing_pending), ('not_interested', True))
        item = self._items('message')[0]
        self.call('li_submit_text', work_id=item['work_id'], text='No problem at all, Ali. All the best.')
        self._script(get_conversation=[thread_data('')])
        self._run()
        self.assertEqual(len(self._calls(tool='send_message')), 1)
        self.assertFalse(prospect.closing_pending)
        # they answer the closing message: heard and analysed, but never thanked a second time
        self.Tools._record_thread(self.profile, prospect, [{'sender_name': 'Ali Raza', 'text': 'Thanks, you too!'}])
        self.assertEqual((prospect.stage, prospect.needs_analysis), ('replied', True))
        analyse = self._items('analyse')[0]
        self.call('li_record_analysis', work_id=analyse['work_id'], sentiment='negative', pivot=False,
                  summary='Polite goodbye.')
        self.assertEqual((prospect.stage, prospect.closing_pending), ('not_interested', False))
        self.assertEqual(self._items('message'), [])

    @freeze_time(MONDAY_10_UTC)
    def test_shared_file_gets_an_answer_without_waiting_for_the_step(self):
        persona = self._persona(run=('chat',))
        persona.chat_step_ids.sorted('sequence')[1].wait_days = 1
        waiting = self._replied(persona, 'We use spreadsheets for everything.')
        self.assertEqual(self._items('message'), [])                   # a plain answer: the step waits its day
        waiting.unlink()
        prospect = self._replied(persona, '[Attachment] Ali Raza - Resume.pdf (185 KB)')
        item = self._items('message')[0]
        self.assertEqual(item['prospect']['id'], prospect.id)
        self.assertIn('expects an answer now', item['instructions'])
        self.assertIn('[Attachment]', item['instructions'])
        self.assertNotIn('step', item)

    @freeze_time(MONDAY_10_UTC)
    def test_free_reply_after_the_questionnaire(self):
        persona = self._persona(run=('chat',))
        prospect = self._replied(persona, 'One more thing: do you also do payroll?')
        prospect.current_step_id = persona.chat_step_ids.sorted('sequence')[-1]     # every step was sent
        item = self._items('message')[0]
        self.assertNotIn('step', item)
        self.assertIn('The questionnaire is finished', item['instructions'])
        self.assertEqual(item['situation']['their_last_reply'], 'One more thing: do you also do payroll?')
        result = self.call('li_submit_text', work_id=item['work_id'],
                           text='Yes Ali, payroll is part of what we set up in Odoo, including local rules.')
        self.assertTrue(result['queued'])
        prospect.awaiting_reply = True                                 # (set when it is sent)
        self.env['li.work.item'].browse(item['work_id'])._close('done')
        self.assertEqual(self._items('message'), [])                   # no second answer until they write

    @freeze_time(MONDAY_10_UTC)
    def test_portfolio_link_is_offered_and_remembered(self):
        self._start()
        persona = self._persona(run=('chat',))
        persona.service_id.portfolio_url = 'https://example.com/our-work'
        prospect = self._replied(persona, 'Can you send me your portfolio?')
        item = self._items('message')[0]
        self.assertEqual(item['portfolio'], {'available': True, 'link': 'https://example.com/our-work',
                                             'already_sent': False})
        persona.service_id.write({'contact_phone': '+92 300 1234567', 'contact_email': False})
        self.assertEqual(prospect._contact_payload(), {'phone': '+92 300 1234567', 'email': ''})
        self.assertEqual(item['contact'], {'phone': '', 'email': ''})          # as it was when the item was made
        self.assertIn('give contact.phone or contact.email exactly as written', item['instructions'])
        self.assertIn('Never invent a number', item['instructions'])
        self.assertIn('include portfolio.link exactly once', item['instructions'])
        self.call('li_submit_text', work_id=item['work_id'], step_done=False,
                  text='Sure Ali, here are a few projects: https://example.com/our-work')
        self._script(get_conversation=[thread_data('')])
        self._run()
        self.assertTrue(prospect.portfolio_sent_at)
        self.assertTrue(prospect._portfolio_payload()['already_sent'])

    def test_portfolio_file_gets_a_private_link(self):
        service = self.env['li.service'].create({'name': 'Advisory', 'description': 'Advice.'})
        self.assertFalse(service.portfolio_link)
        service.write({'portfolio_file': PNG, 'portfolio_filename': 'work.png'})
        first = service.portfolio_link
        self.assertRegex(first, r'/li_sales/portfolio/[\w-]{20,}$')
        service.write({'portfolio_file': PNG})                          # a new file: a new link
        self.assertNotEqual(service.portfolio_link, first)
        service.portfolio_url = 'https://example.com/portfolio'         # your own link wins
        self.assertEqual(service.portfolio_link, 'https://example.com/portfolio')
        service.write({'portfolio_url': False, 'portfolio_file': False})
        self.assertFalse(service.portfolio_link)

    @freeze_time(MONDAY_10_UTC)
    def test_submit_text_is_stale_when_the_conversation_changed(self):
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona)
        item = self._items('message')[0]
        self.env['li.message'].create({'prospect_id': prospect.id, 'direction': 'in', 'kind': 'reply',
                                       'body': 'Hello?', 'state': 'sent', 'sender_name': 'Ali Raza'})
        result = self.call('li_submit_text', work_id=item['work_id'], text='Hi Ali, thanks for connecting!')
        self.assertFalse(result['queued'])
        self.assertTrue(result['stale'])
        work = self.env['li.work.item'].browse(item['work_id'])
        self.assertEqual((work.state, work.discarded_stale), ('cancelled', True))

    @freeze_time(MONDAY_10_UTC)
    def test_submit_text_rules(self):
        persona = self._persona(con_send_note=True, con_note_instructions='Short.')
        self._prospect(persona)
        item = self._items('invite_note')[0]
        with self.assertRaisesRegex(ToolError, 'placeholders'):
            self.call('li_submit_text', work_id=item['work_id'], text='Hi {first_name}!')
        with self.assertRaisesRegex(ToolError, 'maximum is 200'):
            self.call('li_submit_text', work_id=item['work_id'], text='x' * 201)
        self.assertTrue(self.call('li_submit_text', work_id=item['work_id'], text='Hi Ali, love Brand X.')['queued'])
        # Claude in Chrome items are sent in Chrome, not submitted
        self.profile.execution_mode = 'chrome'
        self._prospect(persona, 'sara-khan', 'Sara Khan')
        invite = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'invite'][0]
        with self.assertRaisesRegex(ToolError, 'Claude in Chrome item'):
            self.call('li_submit_text', work_id=invite['work_id'], text='Hi Sara')

    @freeze_time(MONDAY_10_UTC)
    def test_handoff_and_followup_items(self):
        persona = self._persona(run=('chat',), chat_handoff_message='Happy to talk: {meeting_link}',
                                chat_meeting_link='https://cal.example.com/x')
        warm = self._accepted(persona)
        warm.write({'stage': 'warm', 'handoff_pending': True, 'is_taken_over': True, 'takeover_reason': 'pivot'})
        handoff = self._items('handoff')[0]
        self.assertIn('https://cal.example.com/x', handoff['draft'])
        self.assertTrue(self.call('li_submit_text', work_id=handoff['work_id'],
                                  text='Great talking, Ali. Book here: https://cal.example.com/x')['queued'])
        followup = self.env['li.followup.agent']._get()
        followup.step_ids.unlink()
        followup.write({'step_ids': [(0, 0, {'name': 'Nudge', 'wait_days': 2, 'template': 'Any thoughts?'})]})
        followup.action_run()
        quiet = self._accepted(persona, username='sara-khan', name='Sara Khan')
        step = persona.chat_agent_id.step_ids.sorted('sequence')
        self.env['li.message'].create({'prospect_id': quiet.id, 'direction': 'out', 'kind': 'message',
                                       'body': 'Hi Sara!', 'ai_generated': True, 'state': 'sent'})
        quiet.write({'stage': 'messaged', 'current_step_id': step[0].id, 'awaiting_reply': True,
                     'last_outbound_date': fields.Datetime.now() - timedelta(days=3)})
        items = self._items('followup')
        self.assertEqual([i['prospect']['id'] for i in items], [quiet.id])
        self.assertEqual(items[0]['followup']['name'], 'Nudge')

    def test_empty_engine_work_explains_itself(self):
        result = self.call('li_get_work', linkedin_profile='taha')
        self.assertFalse(result['items'])
        summary = self.tools._summarize('li_get_work', result)
        self.assertIn('Nothing to write for taha', summary)
        self.assertIn('Odoo keeps searching', summary)
        overview = self.tools._summarize('li_overview', self.call('li_overview'))
        self.assertIn('taha (built-in engine, connected)', overview)

    @freeze_time(MONDAY_10_UTC)
    def test_finish_run_records_the_run(self):
        persona = self._persona(run=('chat',))
        self._accepted(persona)
        item = self._items('message')[0]
        self.call('li_submit_text', work_id=item['work_id'], text='Hi Ali, thanks for connecting!')
        result = self.call('li_finish_run', summary='1 message written', errors=['search page slow'])
        run = self.env['li.claude.run'].browse(result['run_id'])
        self.assertEqual((run.written, run.errors), (1, 1))
        self.assertEqual(run.linkedin_profile_ids, self.profile)
        self.assertIn('search page slow', run.error_text)
        self.assertIn('Run recorded: 1 written', self.tools._summarize('li_finish_run', result))

    # ------------------------------------------------------------------
    # LinkedIn language
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_language_check_pauses_reading_when_not_english(self):
        self._start()
        persona = self._persona()
        self._prospect(persona)
        self._script(get_my_profile=[{'data': {'url': 'https://www.linkedin.com/in/taha-test/',
                                               'sections': {'main_profile': FRENCH_PROFILE}}}])
        self.profile.with_user(self.manager).action_test_connection()
        self.assertEqual(self.profile.interface_language, 'other')
        self.assertTrue(self.profile.activity_ids.filtered(lambda a: 'English' in a.summary))
        self._run()
        self.assertEqual([c['tool'] for c in self._calls()], ['get_my_profile'])     # nothing else read or sent
        self._script(get_my_profile=[{'data': {'url': 'https://www.linkedin.com/in/taha-test/',
                                               'sections': {'main_profile': ENGLISH_PROFILE}}}])
        self.profile.action_test_connection()
        self.assertEqual(self.profile.interface_language, 'en')
        self.assertFalse(self.profile.activity_ids.filtered(lambda a: 'English' in a.summary))
        self._run()
        self.assertTrue(self._calls(tool='connect_with_person'))

    def test_language_detection(self):
        from ..models.li_engine_parse import interface_language
        self.assertEqual(interface_language(ENGLISH_PROFILE), 'en')
        self.assertEqual(interface_language(FRENCH_PROFILE), 'other')
        self.assertEqual(interface_language('Harvey Reid\nFounder'), '')

    def test_connect_records_the_language(self):
        result = {'structuredContent': {'sections': {'main_profile': FRENCH_PROFILE}}, 'content': []}
        self.profile._apply_interface_language(result)
        self.assertEqual(self.profile.interface_language, 'other')


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestPosts(BackgroundCase):

    def _idea(self, **vals):
        return self.env['li.post'].create(dict({'name': 'Stock sync', 'linkedin_profile_id': self.profile.id,
                                                'idea': 'Why stock sync matters for Shopify brands'}, **vals))

    def _draft(self, post):
        item = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'post_draft'][0]
        self.assertEqual(item['post']['post_id'], post.id)
        self.call('li_submit_post_draft', work_id=item['work_id'], text='Stock that is wrong costs sales.\n\nHere is why.')
        return item

    def test_idea_draft_approve(self):
        post = self._idea()
        self._draft(post)
        self.assertEqual(post.state, 'draft')
        self.assertIn('\n\n', post.text)                  # posts keep their line breaks
        self.assertTrue(post.activity_ids.filtered(lambda a: a.user_id == self.rep))
        other_rep = self.env['res.users'].create({'name': 'Rep 2', 'login': 'li_rep2', 'groups_id': [
            (6, 0, [self.env.ref('linkedin_sales_automation.group_li_user').id])]})
        with self.assertRaises(Exception):                 # not the owner: does not even see it
            post.with_user(other_rep).action_approve()
        post.with_user(self.rep).action_approve()
        self.assertEqual((post.state, post.approved_by), ('approved', self.rep))
        with self.assertRaisesRegex(UserError, 'cannot be changed'):
            post.with_user(self.rep).text = 'changed after approval'
        with self.assertRaisesRegex(ToolError, '3000'):
            idea = self._idea(name='Long')
            item = [i for i in self.call('li_get_work', linkedin_profile='taha')['items']
                    if i['type'] == 'post_draft' and i['post']['post_id'] == idea.id][0]
            self.call('li_submit_post_draft', work_id=item['work_id'], text='x' * 3001)

    @freeze_time(MONDAY_10_UTC)
    def test_engine_publishes_at_the_scheduled_time_then_reads_stats(self):
        self._start()
        post = self._idea(scheduled_at='2026-10-12 12:00:00', image=PNG)
        self._draft(post)
        post.with_user(self.manager).action_approve()
        self.assertEqual(post.state, 'scheduled')
        self._run()
        self.assertFalse(self._calls(tool='create_post'))
        with freeze_time('2026-10-12 12:00:30'):
            self._run()
        call = self._calls(tool='create_post')[0]
        self.assertEqual(call['args']['text'], post.text)
        self.assertTrue(call['args']['image_path'].endswith('.png'))
        self.assertFalse(list((self.profile._session_dir().parent.parent.parent / 'incoming').glob('*post*')))
        self.assertEqual(post.state, 'published')
        self.assertIn('urn:li:activity:7000000000000000001', post.post_url)
        with freeze_time('2026-10-12 13:00:00'):
            self._run()
        self.assertEqual((post.reactions, post.comments, post.reposts), (42, 5, 2))
        self.assertEqual(self._actions(action='post_stats').reads, 1)
        with freeze_time('2026-10-15 13:00:00'):          # weekly, not more
            self._run()
        self.assertEqual(len(self._calls(tool='get_post_stats')), 1)

    @freeze_time(MONDAY_10_UTC)
    def test_engine_publish_unknown_outcome_is_never_retried(self):
        self._start()
        post = self._idea()
        self._draft(post)
        post.with_user(self.manager).action_approve()
        self._script(create_post=[{'data': {'status': 'outcome_unknown', 'retry_safe': False,
                                            'message': 'Post was pressed but LinkedIn did not confirm.'}}])
        self._run()
        self.assertEqual(post.state, 'failed')
        self.assertIn('check LinkedIn', post.error)
        self._run()
        self.assertEqual(len(self._calls(tool='create_post')), 1)

    @freeze_time(MONDAY_10_UTC)
    def test_engine_publish_refusal_goes_back_to_the_queue(self):
        self._start()
        post = self._idea()
        self._draft(post)
        post.with_user(self.manager).action_approve()
        self._script(create_post=[{'data': {'status': 'composer_unavailable', 'retry_safe': True,
                                            'message': 'LinkedIn did not show the box.'}}])
        self._run()
        self.assertEqual((post.state, post.publish_attempts), ('approved', 1))
        self._run()
        self.assertEqual(post.state, 'published')

    def test_interrupted_publish_is_unknown(self):
        post = self._idea(text='Hello', state='publishing')
        post.sudo().publish_started = fields.Datetime.now() - timedelta(minutes=20)
        self._run()
        self.assertEqual(post.state, 'failed')

    @freeze_time(MONDAY_10_UTC)
    def test_chrome_publishes_with_a_publish_post_item(self):
        self.profile.execution_mode = 'chrome'
        post = self._idea()
        self._draft(post)
        post.with_user(self.manager).action_approve()
        item = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'publish_post'][0]
        self.assertIn('Start a post', item['instructions'])
        self.assertTrue(self.call('li_confirm_send', work_id=item['work_id'])['go'])
        self.assertEqual(post.state, 'publishing')
        self.call('li_report_result', work_id=item['work_id'], linkedin_profile='taha', status='published',
                  post_url='https://www.linkedin.com/feed/update/urn:li:activity:1/')
        self.assertEqual((post.state, post.post_url), ('published', 'https://www.linkedin.com/feed/update/urn:li:activity:1/'))
        stats = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'post_stats'][0]
        self.call('li_report_result', work_id=stats['work_id'], linkedin_profile='taha', status='ok', reactions=7,
                  comments=2, reposts=1)
        self.assertEqual((post.reactions, post.comments, post.reposts), (7, 2, 1))

    @freeze_time(MONDAY_10_UTC)
    def test_chrome_publish_unknown_outcome(self):
        self.profile.execution_mode = 'chrome'
        post = self._idea()
        self._draft(post)
        post.with_user(self.manager).action_approve()
        item = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'publish_post'][0]
        self.call('li_confirm_send', work_id=item['work_id'])
        self.call('li_report_result', work_id=item['work_id'], linkedin_profile='taha', status='failed',
                  error='page froze after Post')
        self.assertEqual(post.state, 'failed')
        self.assertFalse([i for i in self.call('li_get_work', linkedin_profile='taha')['items']
                          if i['type'] == 'publish_post'])

    def test_post_stats_parser(self):
        from ..models.li_post import parse_post_stats
        self.assertEqual(parse_post_stats('Ali Raza and 41 others\n5 comments\n2 reposts'), (42, 5, 2))
        self.assertEqual(parse_post_stats('1,204 reactions · 1.2K comments · 1 repost'), (1204, 1200, 1))
        self.assertEqual(parse_post_stats('No reactions yet'), (0, 0, 0))


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestConnectorUrl(BackgroundCase):

    def test_wizard_shows_the_connector_url(self):
        wizard = self.env['li.mcp.token.wizard'].create({'name': 'Claude'})
        wizard.action_generate()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url').rstrip('/')
        self.assertEqual(wizard.connector_url, '%s/li_sales/mcp/%s' % (base, wizard.plain_token))
        wizard.action_done()
        self.assertFalse(wizard.connector_url)

    def test_token_is_hidden_in_the_request_log(self):
        import logging
        from ..controllers.mcp import _HideConnectorToken
        record = logging.LogRecord('werkzeug', logging.INFO, __file__, 1, '%s - - "%s" %s', (
            '127.0.0.1', 'POST /li_sales/mcp/AbC123secret HTTP/1.1', '200'), None)
        _HideConnectorToken().filter(record)
        self.assertNotIn('AbC123secret', record.getMessage())
        self.assertIn('/li_sales/mcp/***', record.getMessage())
        self.assertTrue(json.dumps(record.args))
