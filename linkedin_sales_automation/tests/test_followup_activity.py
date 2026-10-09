from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import freeze_time, tagged

from .common import LiTransactionCase

T0 = datetime(2026, 10, 12, 10, 0, 0)  # Monday


def at(delta):
    return freeze_time(T0 + delta)


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestFollowupActivity(LiTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.followup = cls.env.ref('linkedin_sales_automation.followup_agent_main')
        cls.followup.write({'send_window_from': 0.0, 'send_window_to': 24.0, 'max_followups': 3,
                            'on_reply': 'return_to_chat', 'daily_limit': 60})
        cls.activity_agent = cls.env.ref('linkedin_sales_automation.activity_agent_main')
        cls.activity_agent.write({'deadline_hours': 48, 'auto_done': True, 'assign_to': 'lead_salesperson'})

    def _persona(self, steps=None, **vals):
        values = dict(
            con_send_window_from=0.0, con_send_window_to=24.0, con_delay_min=0, con_delay_max=0,
            chat_send_window_from=0.0, chat_send_window_to=24.0, chat_first_message_delay=0,
            chat_pivot_criteria='Asks for a call.', chat_pivot_min_step=0,
            chat_step_ids=steps or [
                (0, 0, {'sequence': 1, 'name': 'Intro', 'trigger': 'after_accept', 'is_question': False,
                        'template': 'Hi {first_name}, thanks for connecting!'}),
                (0, 0, {'sequence': 2, 'name': 'Platform', 'trigger': 'after_reply', 'is_question': True,
                        'template': 'Which platform do you sell on?'}),
            ])
        values.update(vals)
        persona = self._make_persona('Follow-up persona', **values)
        persona.action_chat_run()
        return persona

    def _accepted(self, persona, name='Ali Raza', username='ali-raza'):
        return self.env['li.prospect'].create({
            'name': name, 'company': 'Brand X', 'persona_id': persona.id,
            'linkedin_url': 'https://www.linkedin.com/in/%s/' % username,
            'stage': 'accepted', 'date_accepted': fields.Datetime.now()})

    def _items(self, work_type, **kw):
        return [i for i in self.work_all(**kw)['items'] if i['type'] == work_type]

    def _release_all(self):
        self.env['li.work.item'].search([('state', '=', 'released')])._close('cancelled')

    def _send(self, item, text):
        self.assertTrue(self.call('li_confirm_send', work_id=item['work_id'], text=text)['go'])
        self.call('li_report_result', work_id=item['work_id'], status='sent', text_sent=text,
                  linkedin_profile='taha', retry_safe=True)

    def _thread(self, prospect, messages):
        return self.call('li_record_conversation', linkedin_profile='taha', prospect_id=prospect.id,
                         messages=[{'sender_name': s, 'text': t} for s, t in messages])

    def _intro(self, persona, prospect):
        self._release_all()
        item = [i for i in self._items('message') if i['prospect']['id'] == prospect.id][0]
        self._send(item, 'Hi %s, thanks for connecting!' % prospect.name.split()[0])

    # ------------------------------------------------------------------
    def test_partial_thread_alignment_new_ok(self):
        with at(timedelta()):
            persona = self._persona()
            prospect = self._accepted(persona)
            self._thread(prospect, [('Ali Raza', 'Hello'), ('Taha Sohail', 'Hi Ali'), ('Ali Raza', 'ok')])
            stored = len(prospect.message_ids_li)
            result = self._thread(prospect, [('Ali Raza', 'ok'), ('Ali Raza', 'ok')])
            self.assertEqual(result['new_replies'], 1)
            self.assertEqual(len(prospect.message_ids_li), stored + 1)
            # the full thread again: nothing new
            again = self._thread(prospect, [('Ali Raza', 'Hello'), ('Taha Sohail', 'Hi Ali'), ('Ali Raza', 'ok'),
                                            ('Ali Raza', 'ok')])
            self.assertEqual(again['new_replies'], 0)

    def test_followups_in_order_after_wait_then_no_response(self):
        self.followup.action_run()
        with at(timedelta()):
            persona = self._persona(steps=[(0, 0, {'sequence': 1, 'name': 'Intro', 'trigger': 'after_accept',
                                                   'is_question': False, 'template': 'Hi {first_name}!'})])
            prospect = self._accepted(persona)
            self._intro(persona, prospect)
            self.assertFalse(self._items('followup'))
        with at(timedelta(days=2, hours=23)):
            self.assertFalse(self._items('followup'), 'Gentle nudge waits 3 days')
        names = []
        for when, text in ((timedelta(days=3, minutes=1), 'Just bumping this, Ali.'),
                           (timedelta(days=8, minutes=2), 'Ali, we helped a similar brand with Odoo.'),
                           (timedelta(days=15, minutes=3), 'Happy to leave it here, Ali.')):
            with at(when - timedelta(minutes=30)):
                self.assertFalse(self._items('followup'), 'not before the step wait')
                self._release_all()
            with at(when):
                items = self._items('followup')
                self.assertEqual(len(items), 1)
                names.append(items[0]['followup']['name'])
                self._send(items[0], text)
        self.assertEqual(names, ['Gentle nudge', 'Value reminder', 'Last check-in'])
        self.assertEqual(prospect.followup_count, 3)
        self.assertEqual(self.env['li.event'].search_count([('prospect_id', '=', prospect.id),
                                                            ('event_type', '=', 'followup_sent')]), 3)
        with at(timedelta(days=30)):
            self.assertFalse(self._items('followup'), 'max_followups reached')
        with at(timedelta(days=22)):
            self.env['li.mcp.tools']._cron_close_no_response()
            self.assertEqual(prospect.stage, 'messaged', 'the last wait (7 days) has not passed')
        with at(timedelta(days=22, minutes=5)):
            self.env['li.mcp.tools']._cron_close_no_response()
            self.assertEqual(prospect.stage, 'no_response')

    def test_reply_stops_followups_and_returns_to_chat(self):
        self.followup.action_run()
        with at(timedelta()):
            persona = self._persona()
            prospect = self._accepted(persona)
            self._intro(persona, prospect)
        with at(timedelta(days=3, minutes=1)):
            self._send(self._items('followup')[0], 'Just bumping this, Ali.')
        with at(timedelta(days=4)):
            self._thread(prospect, [('Ali Raza', 'Sorry, busy week. We use Shopify.')])
            self.assertFalse(prospect.next_followup_date)
            analyse = self._items('analyse')[0]
            self.call('li_record_analysis', work_id=analyse['work_id'], sentiment='positive', pivot=False,
                      summary='Uses Shopify.')
            work = self.work_all()['items']
            self.assertFalse([i for i in work if i['type'] == 'followup'])
            message = [i for i in work if i['type'] == 'message']
            self.assertEqual(message[0]['step']['name'], 'Platform', 'the Chat Agent continues')

    def test_reply_with_on_reply_stop(self):
        self.followup.write({'on_reply': 'stop'})
        self.followup.action_run()
        with at(timedelta()):
            persona = self._persona()
            prospect = self._accepted(persona)
            self._intro(persona, prospect)
        with at(timedelta(days=3, minutes=1)):
            self._send(self._items('followup')[0], 'Just bumping this, Ali.')
        with at(timedelta(days=4)):
            self._thread(prospect, [('Ali Raza', 'We use Shopify.')])
            self.assertTrue(prospect.sequence_stopped)
            analyse = self._items('analyse')[0]
            self.call('li_record_analysis', work_id=analyse['work_id'], sentiment='positive', pivot=False,
                      summary='Uses Shopify.')
            self.assertFalse(self._items('message'))

    def test_takeover_buttons_and_rights(self):
        with at(timedelta()):
            persona = self._persona()
            prospect = self._accepted(persona)
            other = self._accepted(persona, 'Sara Khan', 'sara-khan')
            self._intro(persona, prospect)
            self._intro(persona, other)
            prospect.with_user(self.rep).action_take_over()
            self.assertTrue(prospect.is_taken_over)
            self.assertEqual(prospect.taken_over_by, self.rep)
            with self.assertRaises(UserError):
                prospect.with_user(self.rep).action_return_to_agents()
            self._thread(prospect, [('Ali Raza', 'Shopify here.')])
            self._thread(other, [('Sara Khan', 'WooCommerce here.')])
            analyses = self._items('analyse')
            self.assertEqual([a['prospect']['id'] for a in analyses], [other.id], 'agents stop for Ali only')
            prospect.with_user(self.manager).action_return_to_agents()
            self.assertFalse(prospect.is_taken_over)
            self.assertEqual(prospect.current_step_id.name, 'Intro')
            # the Chat Agent resumes from the current step once the reply is analysed
            prospect.sudo().needs_analysis = True
            self._release_all()
            analyse = [a for a in self._items('analyse') if a['prospect']['id'] == prospect.id][0]
            self.call('li_record_analysis', work_id=analyse['work_id'], sentiment='positive', pivot=False,
                      summary='Shopify.')
            message = [i for i in self._items('message') if i['prospect']['id'] == prospect.id]
            self.assertEqual(message[0]['step']['name'], 'Platform')

    def test_taken_over_prospects_stay_in_check_inbox(self):
        with at(timedelta()):
            persona = self._persona()
            prospect = self._accepted(persona)
            prospect.action_take_over()
            persona.action_chat_stop()
            self.activity_agent.action_run()
            inbox = self._items('check_inbox')
            self.assertEqual([p['id'] for p in inbox[0]['tracked_prospects']], [prospect.id])
            self._release_all()
            self.activity_agent.action_stop()
            self.assertFalse(self._items('check_inbox'))
            self.activity_agent.action_run()
            prospect.stage = 'not_interested'
            self.assertFalse(self._items('check_inbox'), 'closed prospects are not tracked')

    def test_reply_activity_no_stacking_auto_done_and_overdue(self):
        self.activity_agent.action_run()
        with at(timedelta()):
            persona = self._persona(salesperson_id=self.rep.id)
            prospect = self._accepted(persona)
            prospect.action_push_to_crm()
            lead = prospect.crm_lead_id
            self._thread(prospect, [('Ali Raza', 'Thanks, when can we talk?')])
            activity = prospect.reply_activity_id
            self.assertTrue(activity)
            self.assertEqual((activity.res_model, activity.res_id), ('crm.lead', lead.id))
            self.assertEqual(activity.user_id, self.rep)
            self.assertEqual(activity.activity_type_id,
                             self.env.ref('linkedin_sales_automation.mail_activity_type_li_reply'))
            self.assertEqual(prospect.reply_due_at, T0 + timedelta(hours=48))
            self.assertEqual(activity.date_deadline, (T0 + timedelta(hours=48)).date())
        with at(timedelta(hours=2)):
            self._thread(prospect, [('Ali Raza', 'Thanks, when can we talk?'), ('Ali Raza', 'Tomorrow works.')])
            self.assertEqual(prospect.reply_activity_id, activity, 'no stacked activity')
            self.assertEqual(len(lead.activity_ids.filtered(lambda a: a.activity_type_id == activity.activity_type_id)), 1)
            self.assertIn('Tomorrow works', str(activity.note))
            self.assertEqual(prospect.reply_due_at, T0 + timedelta(hours=48), 'the earlier deadline is kept')
        with at(timedelta(hours=5)):
            self._thread(prospect, [('Taha Sohail', 'Great, sending an invite for 3 pm.')])
            self.assertFalse(activity.exists())
            self.assertFalse(prospect.reply_activity_id)
            done = self.env['li.event'].search([('prospect_id', '=', prospect.id),
                                                ('event_type', '=', 'reply_activity_done')])
            self.assertEqual(len(done), 1)
            self.assertIn('after 5 h', done.detail)
        # next reply: new activity; overdue logged once
        with at(timedelta(hours=6)):
            self._thread(prospect, [('Ali Raza', 'Perfect, see you then.')])
            self.assertTrue(prospect.reply_activity_id)
        with at(timedelta(hours=6 + 47)):
            self.assertEqual(self.env['li.mcp.tools']._cron_reply_overdue(), 0)
        with at(timedelta(hours=6 + 49)):
            self.assertEqual(self.env['li.mcp.tools']._cron_reply_overdue(), 1)
            self.assertEqual(self.env['li.mcp.tools']._cron_reply_overdue(), 0)
            self.assertTrue(prospect.reply_overdue)
            self.assertEqual(self.env['li.event'].search_count([('prospect_id', '=', prospect.id),
                                                                ('event_type', '=', 'reply_activity_overdue')]), 1)
            self.assertIn(prospect, self.env['li.prospect'].search([('reply_overdue', '=', True)]))

    def test_activity_on_prospect_without_lead_and_agent_message_closes_it(self):
        self.activity_agent.action_run()
        with at(timedelta()):
            persona = self._persona()
            prospect = self._accepted(persona)
            self._intro(persona, prospect)
            prospect.action_take_over()
            self._thread(prospect, [('Taha Sohail', 'Hi Ali, thanks for connecting!'), ('Ali Raza', 'Hi!')])
            activity = prospect.reply_activity_id
            self.assertEqual((activity.res_model, activity.res_id), ('li.prospect', prospect.id))
            self.assertEqual(activity.user_id, prospect.taken_over_by)
        with at(timedelta(hours=1)):
            self._thread(prospect, [('Ali Raza', 'Hi!'), ('Taha Sohail', 'Glad to have you here.')])
            self.assertFalse(prospect.reply_activity_id)

    def test_followup_skips_taken_over_and_human_threads(self):
        self.followup.action_run()
        with at(timedelta()):
            persona = self._persona()
            ali = self._accepted(persona)
            sara = self._accepted(persona, 'Sara Khan', 'sara-khan')
            self._intro(persona, ali)
            self._intro(persona, sara)
            sara.action_take_over()
        with at(timedelta(days=3, minutes=1)):
            items = self._items('followup')
            self.assertEqual([i['prospect']['id'] for i in items], [ali.id])
