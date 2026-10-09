from odoo import fields
from odoo.tests import freeze_time, tagged

from .common import LiTransactionCase
from ..models.li_mcp_tools import ToolError

T0 = '2026-10-12 10:00:00'  # Monday


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestChatAgent(LiTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.meeting_link = 'https://cal.example.com/taha/20min'

    def _persona(self, name='Chat persona', profile=None, **vals):
        values = dict(
            con_send_window_from=0.0, con_send_window_to=24.0, con_delay_min=0, con_delay_max=0,
            chat_send_window_from=0.0, chat_send_window_to=24.0, chat_first_message_delay=4,
            chat_pivot_criteria='Confirms they sell online and want stock sync, or asks for a call or pricing.',
            chat_pivot_min_step=2,
            chat_handoff_message='Happy to show you how this works on a 20-min call: {meeting_link}',
            chat_meeting_link=self.meeting_link,
            chat_step_ids=[
                (0, 0, {'sequence': 1, 'name': 'Intro', 'trigger': 'after_accept', 'is_question': False,
                        'objective': 'Thank them, mention their brand',
                        'template': 'Hi {first_name}, thanks for connecting!'}),
                (0, 0, {'sequence': 2, 'name': 'Platform', 'trigger': 'after_reply', 'is_question': True,
                        'objective': 'Which platform and ERP?', 'template': 'Which platform do you sell on?'}),
                (0, 0, {'sequence': 3, 'name': 'Pain point', 'trigger': 'after_reply', 'is_question': True,
                        'objective': 'Biggest stock headache?', 'template': 'What is the biggest stock issue?'}),
            ])
        values.update(vals)
        persona = self._make_persona(name, profile=profile, **values)
        persona.action_chat_run()
        return persona

    def _accepted(self, persona, name='Ali Raza', username='ali-raza', company='Brand X'):
        return self.env['li.prospect'].create({
            'name': name, 'company': company, 'title': 'Founder', 'persona_id': persona.id,
            'linkedin_url': 'https://www.linkedin.com/in/%s/' % username,
            'stage': 'accepted', 'date_accepted': fields.Datetime.now(),
        })

    def _items(self, work_type, **kw):
        return [i for i in self.work_all(**kw)['items'] if i['type'] == work_type]

    def _release_all(self):
        self.env['li.work.item'].search([('state', '=', 'released')])._close('cancelled')

    def _send(self, item, text, connector='taha'):
        go = self.call('li_confirm_send', work_id=item['work_id'], text=text)
        self.assertTrue(go['go'], go)
        return self.call('li_report_result', work_id=item['work_id'], status='sent', text_sent=text,
                         linkedin_profile=connector, retry_safe=True)

    def _thread(self, prospect, messages, connector='taha'):
        return self.call('li_record_conversation', linkedin_profile=connector, prospect_id=prospect.id,
                         messages=[{'sender_name': s, 'text': t} for s, t in messages])

    # ------------------------------------------------------------------
    def test_step_one_waits_for_delay_and_window(self):
        with freeze_time(T0):
            persona = self._persona(chat_send_window_from=10.0, chat_send_window_to=18.0)
            self._accepted(persona)
            self.assertFalse(self._items('message'))
        with freeze_time('2026-10-12 13:59:00'):
            self.assertFalse(self._items('message'), 'first_message_delay is 4 h')
        with freeze_time('2026-10-12 14:01:00'):
            items = self._items('message')
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['step']['number'], 1)
            self.assertEqual(items[0]['draft'], 'Hi Ali, thanks for connecting!')
            self._release_all()
        with freeze_time('2026-10-12 18:30:00'):
            self.assertFalse(self._items('message'), 'outside the chat send window')

    def test_after_reply_step_needs_recorded_and_analysed_reply(self):
        with freeze_time(T0):
            persona = self._persona(chat_first_message_delay=0)
            prospect = self._accepted(persona)
            step1 = self._items('message')[0]
            self._send(step1, 'Hi Ali, thanks for connecting! Love what Brand X does.')
            self.assertEqual(prospect.stage, 'messaged')
            self.assertFalse(self._items('message'), 'step 2 waits for a reply')
            self._release_all()
            self._thread(prospect, [('Taha Sohail', 'Hi Ali, thanks for connecting! Love what Brand X does.'),
                                    ('Ali Raza', 'Thanks Taha! We sell on Shopify.')])
            self.assertEqual(prospect.stage, 'replied')
            self.assertTrue(prospect.needs_analysis)
            work = self.work_all()['items']
            self.assertFalse([i for i in work if i['type'] == 'message'], 'not before the analysis')
            analyse = [i for i in work if i['type'] == 'analyse'][0]
            self.assertEqual(analyse['current_step']['name'], 'Intro')
            self.assertEqual([s['name'] for s in analyse['remaining_question_steps']], ['Platform', 'Pain point'])
            self.assertIn('stock sync', analyse['pivot_criteria'])
            self.assertFalse(analyse['pivot_allowed_now'])
            self.assertEqual(analyse['answers_so_far'], {})
            self._release_all()
            analyse = self._items('analyse')[0]
            result = self.call('li_record_analysis', work_id=analyse['work_id'], sentiment='positive', pivot=False,
                               answers={'Platform': 'Shopify'}, summary='Sells on Shopify.')
            self.assertNotIn('{', self.env['li.mcp.tools']._summarize('li_record_analysis', result))
            step2 = self._items('message')
            self.assertEqual(len(step2), 1)
            self.assertEqual(step2[0]['step']['name'], 'Platform')
            self.assertEqual(step2[0]['answers_so_far'], {'Platform': 'Shopify'})

    @freeze_time(T0)
    def test_conversation_dedup_full_then_partial(self):
        persona = self._persona()
        prospect = self._accepted(persona)
        thread = [
            ('Taha Sohail', 'Hi Ali, thanks for connecting!'),
            ('Ali Raza', 'Hi! ok'),
            ('Ali Raza', 'We sell on Shopify'),
            ('Ali Raza', 'ok'),
            ('Ali Raza', 'ok'),
            ('Ali Raza', 'Stock never matches the warehouse.'),
        ]
        # our first message was written by hand here (no agent sent it): takeover expected, recorded once
        first = self._thread(prospect, thread)
        self.assertEqual(first['new_replies'], 5)
        count = len(prospect.message_ids_li)
        events = self.env['li.event'].search_count([('prospect_id', '=', prospect.id),
                                                    ('event_type', '=', 'reply_received')])
        self.assertEqual(count, 6)
        self.assertEqual(events, 1)
        again = self._thread(prospect, thread)
        self.assertEqual((again['new_replies'], again['new_manual_messages']), (0, 0))
        partial = self._thread(prospect, thread[-3:])
        self.assertEqual((partial['new_replies'], partial['new_manual_messages']), (0, 0))
        self.assertEqual(len(prospect.message_ids_li), count)
        self.assertEqual(self.env['li.event'].search_count([('prospect_id', '=', prospect.id),
                                                            ('event_type', '=', 'reply_received')]), events)
        # timestamps are optional and fuzzy values are tolerated
        self.call('li_record_conversation', linkedin_profile='taha', prospect_id=prospect.id,
                  messages=[{'sender_name': 'Ali Raza', 'text': 'ok', 'sent_at': '2h'},
                            {'sender_name': 'Ali Raza', 'text': 'ok', 'sent_at': 'Mon'},
                            {'sender_name': 'Ali Raza', 'text': 'ok'}])
        self.assertEqual(len(prospect.message_ids_li), count + 1, 'a third "ok" is a new message')
        self.assertIn('1 new reply', self.env['li.mcp.tools']._summarize('li_record_conversation', {
            'message': 'Ali Raza: 1 new reply.'}))

    @freeze_time(T0)
    def test_formatting_differences_do_not_trigger_takeover(self):
        persona = self._persona(chat_first_message_delay=0)
        prospect = self._accepted(persona)
        sent = 'Hi Ali, thanks for connecting! Love what Brand X does 🙂'
        self._send(self._items('message')[0], sent)
        result = self._thread(prospect, [
            ('Taha  Sohail', '  hi ali,   thanks for connecting!  Love what Brand X does'),
            ('Ali Raza', 'Thanks!'),
        ])
        self.assertFalse(prospect.is_taken_over, result)
        self.assertEqual(result['new_manual_messages'], 0)
        # a confirmed send whose report never arrived is still recognised as ours
        self.call('li_record_analysis', work_id=self._items('analyse')[0]['work_id'], sentiment='neutral',
                  pivot=False, summary='Polite.')
        step2 = self._items('message')[0]
        self.call('li_confirm_send', work_id=step2['work_id'], text='Which platform do you sell on, Ali?')
        self._thread(prospect, [('Taha Sohail', 'Which platform do you sell on, Ali ?!')])
        self.assertFalse(prospect.is_taken_over)
        # anything else from our account is a person writing by hand
        result = self._thread(prospect, [('Taha Sohail', 'Let me call you tomorrow morning.')])
        self.assertTrue(prospect.is_taken_over)
        self.assertEqual(prospect.takeover_reason, 'human_message')
        self.assertEqual(result['new_manual_messages'], 1)

    @freeze_time(T0)
    def test_human_message_takeover_keeps_other_prospects(self):
        persona = self._persona(chat_first_message_delay=0)
        ali = self._accepted(persona)
        sara = self._accepted(persona, 'Sara Khan', 'sara-khan', 'Brand Y')
        items = self._items('message')
        self.assertEqual(len(items), 2)
        ali_item = [i for i in items if i['prospect']['id'] == ali.id][0]
        self._thread(ali, [('Taha Sohail', 'Hey Ali, Taha here, saw your post!')])
        self.assertTrue(ali.is_taken_over)
        answer = self.call('li_confirm_send', work_id=ali_item['work_id'], text='Hi Ali, thanks for connecting!')
        self.assertFalse(answer['go'])
        sara_item = [i for i in items if i['prospect']['id'] == sara.id][0]
        self.assertTrue(self.call('li_confirm_send', work_id=sara_item['work_id'],
                                  text='Hi Sara, thanks for connecting!')['go'])

    @freeze_time(T0)
    def test_opt_out_and_negative(self):
        persona = self._persona(chat_first_message_delay=0)
        ali = self._accepted(persona)
        sara = self._accepted(persona, 'Sara Khan', 'sara-khan')
        for prospect in (ali, sara):
            self._thread(prospect, [(prospect.name, 'Not for me.')])
        analyses = {i['prospect']['id']: i for i in self._items('analyse')}
        self.call('li_record_analysis', work_id=analyses[ali.id]['work_id'], sentiment='opt_out', pivot=False,
                  summary='Asked not to be contacted.')
        self.call('li_record_analysis', work_id=analyses[sara.id]['work_id'], sentiment='negative', pivot=False,
                  summary='Not interested.')
        self.assertEqual((ali.stage, ali.do_not_contact), ('not_interested', True))
        self.assertEqual((sara.stage, sara.do_not_contact), ('not_interested', False))
        self.assertFalse(self._items('message'))
        # never contacted again by any persona
        other = self._persona('Other persona', profile=self.profile2)
        other.action_connection_run()
        search = [i for i in self.work_all(linkedin_profile='rep1')['items']
                  if i['type'] == 'search_prospects'][0]
        result = self.call('li_add_prospects', work_id=search['work_id'], people=[
            {'name': 'Ali Raza', 'username': 'ali-raza'}, {'name': 'Sara Khan', 'username': 'sara-khan'}])
        self.assertEqual(result['do_not_contact'], 1)
        self.assertEqual(result['contacted_elsewhere'], 1)

    @freeze_time(T0)
    def test_pivot_lead_handoff_and_single_lead_per_url(self):
        persona = self._persona(chat_first_message_delay=0, salesperson_id=self.rep.id)
        prospect = self._accepted(persona)
        self._send(self._items('message')[0], 'Hi Ali, thanks for connecting!')
        self._thread(prospect, [('Taha Sohail', 'Hi Ali, thanks for connecting!'),
                                ('Ali Raza', 'Can you send me your price?')])
        # pivot_min_step = 2: not allowed at step 1
        result = self.call('li_record_analysis', work_id=self._items('analyse')[0]['work_id'], sentiment='positive',
                           pivot=True, pivot_reason='asked for pricing', summary='Wants pricing early.')
        self.assertIn('not allowed before step 2', result['message'])
        self.assertFalse(prospect.crm_lead_id)
        step2 = self._items('message')[0]
        self._send(step2, 'Sure. Which platform do you sell on, Ali?')
        self._thread(prospect, [('Ali Raza', 'Shopify. Stock never matches the warehouse, can we get a call?')])
        result = self.call('li_record_analysis', work_id=self._items('analyse')[0]['work_id'], sentiment='positive',
                           pivot=True, pivot_reason='asked for a call', answers={'Platform': 'Shopify'},
                           summary='Shopify brand with stock sync issues, wants a call.')
        lead = prospect.crm_lead_id
        self.assertTrue(lead)
        self.assertEqual(result['crm_lead_id'], lead.id)
        self.assertEqual(lead.name, 'Brand X – Odoo (LinkedIn)')
        self.assertEqual((lead.contact_name, lead.partner_name, lead.function), ('Ali Raza', 'Brand X', 'Founder'))
        self.assertEqual(lead.website, 'https://www.linkedin.com/in/ali-raza/')
        self.assertEqual((lead.li_prospect_id, lead.li_persona_id), (prospect, persona))
        self.assertEqual(lead.user_id, self.rep)
        self.assertIn('LinkedIn AI', lead.tag_ids.mapped('name'))
        self.assertIn('ERP', lead.tag_ids.mapped('name'))
        self.assertEqual(lead.source_id.name, 'LinkedIn Automation')
        self.assertEqual(lead.medium_id.name, 'LinkedIn')
        description = str(lead.description)
        for fragment in ('Shopify brand with stock sync issues', 'Platform', 'Shopify', 'can we get a call',
                         'Which platform do you sell on'):
            self.assertIn(fragment, description)
        self.assertEqual(prospect.stage, 'warm')
        self.assertTrue(prospect.is_taken_over)
        self.assertEqual(prospect.takeover_reason, 'pivot')
        self.assertTrue(lead.activity_ids.filtered(lambda a: a.user_id == self.rep))
        self.assertEqual(self.env['li.event'].search_count([('crm_lead_id', '=', lead.id),
                                                            ('event_type', '=', 'warm_lead')]), 1)
        # handoff item with the meeting link, then nothing more for this prospect
        handoff = self._items('handoff')
        self.assertEqual(len(handoff), 1)
        self.assertIn(self.meeting_link, handoff[0]['text'])
        self._send(handoff[0], handoff[0]['text'])
        self.assertFalse(prospect.handoff_pending)
        self.assertFalse(self._items('message'))
        # the same person pivots on another persona: logged on the existing lead
        other = self._persona('Second persona', profile=self.profile2, chat_pivot_min_step=0)
        twin = self._accepted(other, 'Ali Raza', 'ali-raza')
        self.call('li_record_conversation', linkedin_profile='rep1', prospect_id=twin.id,
                  messages=[{'sender_name': 'Ali Raza', 'text': 'Also interested in bookkeeping, call me.'}])
        analyse = self._items('analyse', linkedin_profile='rep1')[0]
        self.call('li_record_analysis', work_id=analyse['work_id'], sentiment='positive', pivot=True,
                  pivot_reason='asked for a call', summary='Wants a call.')
        self.assertEqual(twin.crm_lead_id, lead)
        self.assertEqual(self.env['crm.lead'].with_context(active_test=False).search_count(
            [('website', '=', 'https://www.linkedin.com/in/ali-raza/')]), 1)
        self.assertIn('Pivot reached again', lead.message_ids[0].body)

    @freeze_time(T0)
    def test_wrong_connector_refused_for_conversation(self):
        persona = self._persona()
        prospect = self._accepted(persona)
        with self.assertRaisesRegex(ToolError, 'Wrong LinkedIn connector'):
            self._thread(prospect, [('Ali Raza', 'Hello')], connector='rep1')
        self.assertFalse(prospect.message_ids_li)

    @freeze_time(T0)
    def test_check_inbox_item(self):
        persona = self._persona()
        prospect = self._accepted(persona)
        inbox = self._items('check_inbox')
        self.assertEqual(len(inbox), 1)
        self.assertEqual([p['id'] for p in inbox[0]['tracked_prospects']], [prospect.id])
        self.call('li_record_conversation', linkedin_profile='taha', work_id=inbox[0]['work_id'],
                  prospect_id=prospect.id, messages=[{'sender_name': 'Ali Raza', 'text': 'Hi there'}])
        self.assertEqual(self.env['li.work.item'].browse(inbox[0]['work_id']).state, 'done')
        self.assertFalse(self._items('check_inbox'), 'next inbox check after the interval')

    @freeze_time(T0)
    def test_manual_push_to_crm(self):
        persona = self._persona()
        prospect = self._accepted(persona)
        prospect.with_user(self.rep).action_push_to_crm()
        self.assertTrue(prospect.crm_lead_id)
        self.assertEqual(prospect.stage, 'warm')
        self.assertTrue(prospect.is_taken_over)
