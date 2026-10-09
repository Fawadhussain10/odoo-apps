import json
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from odoo import fields
from odoo.sql_db import db_connect
from odoo.tools import config
from odoo.tests import freeze_time, tagged

from .common import LiTransactionCase
from .test_engine_manager import FAKE_ENGINE, READY
from .test_engine_parse import THREAD
from ..models.li_engine_parse import inbox_preview

MONDAY_10_UTC = '2026-10-12 10:00:00'      # Monday


def thread_data(text):
    return {'data': {'url': 'https://www.linkedin.com/messaging/thread/2-abc/', 'sections': {'conversation': text}}}


def search_data(*people):
    lines, refs = [], []
    for username, name, headline in people:
        lines += [name, '• 2nd', headline, 'Lahore']
        refs.append({'kind': 'person', 'url': '/in/%s/' % username, 'text': name})
    return {'data': {'url': 'https://www.linkedin.com/search/results/people/',
                     'sections': {'search_results': '\n'.join(lines)}, 'references': {'search_results': refs}}}


class BackgroundCase(LiTransactionCase):
    """Engine profiles against the fake engine (a real process answering MCP on
    127.0.0.1); helpers shared by the background, writing and post tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp(prefix='li-bg-test-')
        Manager = type(cls.env['li.engine.manager'])
        Profile = type(cls.env['li.profile'])
        cls.startClassPatcher(patch.object(Manager, '_root', lambda self: Path(cls.tmp)))

        def fake_command(self, port, headless):
            return [sys.executable, FAKE_ENGINE, '--transport', 'streamable-http', '--host', '127.0.0.1',
                    '--port', str(port), '--user-data-dir', str(self._profile_dir()), '--no-auto-import']
        cls.startClassPatcher(patch.object(Profile, '_engine_command', fake_command))
        cls.startClassPatcher(patch.object(Manager, '_check_ready', lambda self: dict(READY)))
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_param('li_sales.bg_jitter_max', 0)
        (cls.profile | cls.profile2).write({'execution_mode': 'engine'})
        cls.Tools = cls.env['li.mcp.tools']

    def setUp(self):
        super().setUp()
        self.addCleanup(self._stop_all)

    def _stop_all(self):
        for profile in (self.profile | self.profile2).exists():
            profile._engine_kill()
            shutil.rmtree(profile._session_dir(), ignore_errors=True)

    # ------------------------------------------------------------------
    def _start(self, profile=None):
        profile = profile or self.profile
        self.assertTrue(profile._engine_start())
        return profile

    def _script(self, profile=None, **answers):
        path = (profile or self.profile)._session_dir() / 'fake-script.json'
        script = json.loads(path.read_text()) if path.exists() else {}
        for tool, queue in answers.items():
            script.setdefault(tool, []).extend(queue)
        path.write_text(json.dumps(script))

    def _calls(self, profile=None, tool=None):
        path = (profile or self.profile)._session_dir() / 'fake-calls.jsonl'
        calls = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [c for c in calls if not tool or c['tool'] == tool]

    def _run(self):
        return self.Tools._cron_background_work()

    def _persona(self, name='Engine persona', profile=None, run=('connection',), **vals):
        values = dict(con_send_window_from=0.0, con_send_window_to=24.0, con_delay_min=0, con_delay_max=0,
                      chat_send_window_from=0.0, chat_send_window_to=24.0, chat_first_message_delay=0,
                      chat_pivot_criteria='Asks for a call.', chat_pivot_min_step=2,
                      chat_step_ids=[(0, 0, {'sequence': 1, 'name': 'Intro', 'trigger': 'after_accept',
                                             'is_question': False, 'template': 'Hi {first_name}!'}),
                                     (0, 0, {'sequence': 2, 'name': 'Platform', 'trigger': 'after_reply',
                                             'template': 'Which platform?'})])
        values.update(vals)
        persona = self._make_persona(name, profile=profile, **values)
        if 'connection' in run:
            persona.action_connection_run()
        if 'chat' in run:
            persona.action_chat_run()
        return persona

    def _prospect(self, persona, username='ali-raza', name='Ali Raza', **vals):
        return self.env['li.prospect'].create(dict({
            'name': name, 'persona_id': persona.id, 'linkedin_url': 'https://www.linkedin.com/in/%s/' % username,
        }, **vals))

    def _accepted(self, persona, **vals):
        # the engine has read the profile already, unless a test says otherwise
        vals.setdefault('profile_text', 'Founder at Brand X\nAbout\nI run a fashion brand on Shopify.')
        vals.setdefault('profile_read_at', fields.Datetime.now())
        return self._prospect(persona, stage='accepted', date_accepted=fields.Datetime.now(), **vals)

    def _actions(self, profile=None, **domain):
        dom = [('linkedin_profile_id', '=', (profile or self.profile).id)] + [(k, '=', v) for k, v in domain.items()]
        return self.env['li.engine.action'].search(dom)

    def _chat_prospect(self, thread_text=None):
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona)
        if thread_text is not None:
            self._script(get_conversation=[thread_data(thread_text)])
        return persona, prospect



@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestBackgroundWork(BackgroundCase):
    """The background worker of built-in engine profiles."""

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_search_queues_prospects(self):
        self._start()
        persona = self._persona(job_titles='Founder', include_keywords='shopify')
        self._script(search_people=[search_data(('ali-raza', 'Ali Raza', 'Founder at Brand X'),
                                                ('sara-khan', 'Sara Khan', 'CEO at Shopify brand'))])
        self._run()
        call = self._calls(tool='search_people')[0]
        self.assertEqual(call['args']['keywords'], 'Founder shopify')
        prospects = self.env['li.prospect'].search([('persona_id', '=', persona.id)])
        self.assertEqual(sorted(prospects.mapped('linkedin_username')), ['ali-raza', 'sara-khan'])
        self.assertEqual(prospects.filtered(lambda p: p.linkedin_username == 'ali-raza').headline,
                         'Founder at Brand X')
        action = self._actions(action='search')
        self.assertEqual((action.reads, action.state), (1, 'ok'))
        self.assertIn('2 queued', action.detail)
        self.assertEqual(self.profile.reads_today, 1)

    # ------------------------------------------------------------------
    # Invites
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_invite_without_note_is_sent_in_background(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._run()
        connect = self._calls(tool='connect_with_person')
        self.assertEqual(connect, [{'tool': 'connect_with_person', 'args': {'linkedin_username': 'ali-raza'}}])
        self.assertEqual(prospect.stage, 'invited')
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.result_status, item.quota_consumed), ('done', 'sent', True))
        self.assertTrue(self.env['li.event'].search([('prospect_id', '=', prospect.id),
                                                     ('event_type', '=', 'invite_sent')]))
        # one send per run and the delay gap between sends
        self._prospect(persona, 'sara-khan', 'Sara Khan')
        persona.connection_agent_id.write({'delay_min': 60, 'delay_max': 60})
        self.profile.send_gap_seconds = 60
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)
        with freeze_time('2026-10-12 10:01:01'):
            self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 2)

    @freeze_time(MONDAY_10_UTC)
    def test_invite_with_note_waits_for_the_text(self):
        self._start()
        persona = self._persona(con_send_note=True, con_note_instructions='Mention their brand.')
        prospect = self._prospect(persona)
        self._run()
        self.assertFalse(self._calls(tool='connect_with_person'))
        self.Tools._queue_send('invite', prospect, text='Hi Ali, love what Brand X does.', with_note=True)
        self._run()
        self.assertEqual(self._calls(tool='connect_with_person')[0]['args'],
                         {'linkedin_username': 'ali-raza', 'note': 'Hi Ali, love what Brand X does.'})
        note = prospect.message_ids_li.filtered(lambda m: m.kind == 'note')
        self.assertEqual(note.body, 'Hi Ali, love what Brand X does.')

    @freeze_time(MONDAY_10_UTC)
    def test_custom_note_limit_resends_without_note(self):
        self._start()
        persona = self._persona(con_send_note=True, con_note_instructions='Short.')
        prospect = self._prospect(persona)
        self.Tools._queue_send('invite', prospect, text='Hi Ali!', with_note=True)
        self._script(connect_with_person=[{'data': {'status': 'custom_note_limit_reached', 'note_sent': False,
                                                    'message': 'Upgrade to Premium to send unlimited notes'}}])
        self._run()
        self.assertTrue(prospect.invite_without_note)
        self.assertEqual(prospect.stage, 'queued')
        self._run()
        calls = self._calls(tool='connect_with_person')
        self.assertEqual([c['args'].get('note') for c in calls], ['Hi Ali!', None])
        self.assertEqual(prospect.stage, 'invited')

    @freeze_time(MONDAY_10_UTC)
    def test_weekly_invite_limit_pauses_connection_agents(self):
        self._start()
        persona = self._persona()
        self._prospect(persona)
        self._prospect(persona, 'sara-khan', 'Sara Khan')
        self._script(connect_with_person=[{'data': {'status': 'send_failed', 'message':
                                                    "You've reached the weekly invitation limit"}}])
        self._run()
        agent = persona.connection_agent_id
        self.assertEqual(agent.state, 'paused')
        self.assertEqual(agent.paused_until, fields.Datetime.to_datetime('2026-10-19 00:00:00'))
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)

    @freeze_time(MONDAY_10_UTC)
    def test_invites_not_recorded_pause_the_account_for_a_day(self):
        self._start()
        persona = self._persona()
        first = self._prospect(persona)
        second = self._prospect(persona, 'sara-khan', 'Sara Khan')
        third = self._prospect(persona, 'omar-ali', 'Omar Ali')
        refused = {'data': {'status': 'send_failed',
                            'message': 'Submitted the invite dialog but the profile still exposes Connect.'}}
        self._script(connect_with_person=[refused, refused, refused])
        agent = persona.connection_agent_id
        self._run()                                   # once: an ordinary failure, retried
        self.assertEqual((agent.state, self.profile.invites_not_recorded), ('running', 1))
        self._run()                                   # the same person again: still the person
        self.assertEqual((agent.state, self.profile.invites_not_recorded), ('running', 1))
        first.needs_check = True                      # out of the queue: the next person is tried
        self._run()
        self.assertEqual(agent.state, 'paused')       # two different people: the account
        self.assertEqual(agent.paused_until, fields.Datetime.now() + timedelta(hours=24))
        self.assertIn('invitation limit', agent.pause_reason)
        self.assertEqual((second.stage, second.needs_check, second.send_attempts), ('queued', False, 0))
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 3)   # nothing more is tried
        # a day later the agent runs again; a recorded invite clears the count
        with freeze_time('2026-10-13 10:01:00'):
            self.env['li.connection.agent']._resume_due()
            self.assertEqual(agent.state, 'running')
            self._run()
            self.assertEqual(second.stage, 'invited')
            self.assertEqual(self.profile.invites_not_recorded, 0)
        self.assertEqual(third.stage, 'queued')

    @freeze_time(MONDAY_10_UTC)
    def test_invite_needing_an_email_address_is_the_person_not_the_account(self):
        self._start()
        persona = self._persona()
        first = self._prospect(persona)
        second = self._prospect(persona, 'sara-khan', 'Sara Khan')
        refused = {'data': {'status': 'send_failed',
                            'message': 'Submitted the invite dialog but the profile still exposes Connect.'}}
        asks_email = {'data': {'status': 'email_required', 'text': 'To verify this member knows you, enter their email',
                               'retry_safe': True}}
        self._script(connect_with_person=[refused, refused], check_invite_dialog=[asks_email, asks_email])
        self._run()
        self._run()
        self.assertEqual(self._calls(tool='check_invite_dialog')[0]['args'], {'linkedin_username': 'ali-raza'})
        self.assertEqual((first.stage, second.stage), ('followed', 'followed'))    # no Connect: followed instead
        self.assertEqual(self.profile.invites_not_recorded, 0)
        self.assertEqual(persona.connection_agent_id.state, 'running')
        self.assertEqual(self._actions(action='invite_check')[0].reads, 1)

    @freeze_time(MONDAY_10_UTC)
    def test_weekly_limit_notice_from_linkedin(self):
        # the engine adds LinkedIn's own pop-up text to a send that was not recorded
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'data': {'status': 'send_failed', 'message': (
            'Submitted the invite dialog but the profile still exposes Connect. LinkedIn says: Your invitation to '
            'Muhammad was not sent because you have reached the weekly limit for connection invitations. Please '
            'try again next week')}}])
        self._run()
        agent = persona.connection_agent_id
        self.assertEqual(agent.state, 'paused')
        self.assertEqual(agent.paused_until, fields.Datetime.to_datetime('2026-10-19 00:00:00'))   # next Monday
        self.assertEqual(self._calls(tool='check_invite_dialog'), [])
        self.assertEqual((prospect.stage, prospect.needs_check, prospect.send_attempts), ('queued', False, 0))
        self.assertEqual(self.profile.invites_not_recorded, 0)

    @freeze_time(MONDAY_10_UTC)
    def test_invite_dialog_stating_the_weekly_limit(self):
        self._start()
        persona = self._persona()
        self._prospect(persona)
        self._script(connect_with_person=[{'data': {'status': 'send_failed', 'message': 'still exposes Connect.'}}],
                     check_invite_dialog=[{'data': {'status': 'dialog', 'retry_safe': True,
                                                    'text': "You've reached the weekly invitation limit"}}])
        self._run()
        agent = persona.connection_agent_id
        self.assertEqual(agent.paused_until, fields.Datetime.to_datetime('2026-10-19 00:00:00'))

    @freeze_time(MONDAY_10_UTC)
    def test_no_connect_follows_instead(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'data': {'status': 'follow_only', 'message': 'Follow only profile.'}}])
        self._run()
        self.assertEqual(self._calls(tool='follow_person')[0]['args'], {'linkedin_username': 'ali-raza'})
        self.assertEqual(prospect.stage, 'followed')
        self.assertFalse(prospect.needs_check)
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.result_status, item.quota_consumed), ('done', 'followed', False))
        self.assertTrue(self.env['li.event'].search([('prospect_id', '=', prospect.id), ('event_type', '=', 'followed')]))
        self.assertEqual(self._actions(action='follow').state, 'ok')

    @freeze_time(MONDAY_10_UTC)
    def test_no_connect_without_follow_is_flagged(self):
        self._start()
        persona = self._persona(con_follow_if_no_connect=False)
        prospect = self._prospect(persona)
        other = self._prospect(persona, 'sara-khan', 'Sara Khan')
        self._script(connect_with_person=[{'data': {'status': 'connect_unavailable'}}])
        self._run()
        self.assertFalse(self._calls(tool='follow_person'))
        self.assertTrue(prospect.needs_check)
        persona.con_follow_if_no_connect = True
        self.profile.last_send_at = False
        self._script(connect_with_person=[{'data': {'status': 'connect_unavailable'}}],
                     follow_person=[{'data': {'status': 'follow_unavailable', 'retry_safe': True}}])
        self._run()
        self.assertTrue(other.needs_check)                     # neither Connect nor Follow: a person checks
        self.assertEqual(other.stage, 'queued')

    @freeze_time(MONDAY_10_UTC)
    def test_unknown_outcome_is_never_retried(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'data': {'status': 'outcome_unknown', 'retry_safe': False}}])
        self._run()
        self.assertTrue(prospect.needs_check)
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.retry_safe, item.quota_consumed), ('failed', False, True))
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)

    @freeze_time(MONDAY_10_UTC)
    def test_send_timeout_is_unknown_outcome(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        # Odoo's test mode raises request timeouts to 10 s at least
        self._script(connect_with_person=[{'sleep': 11, 'data': {'status': 'connected'}}])
        with patch.object(type(self.Tools), '_bg_call_timeout', lambda self: 2):
            self._run()
        self.assertTrue(prospect.needs_check)
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.result_status, item.retry_safe), ('failed', 'unknown', False))
        self.assertEqual(self._actions(action='invite').status, 'timeout')

    def test_interrupted_send_becomes_unknown(self):
        persona = self._persona()
        prospect = self._prospect(persona)
        item = self.Tools._queue_send('invite', prospect)
        item.write({'state': 'sending', 'confirmed': True,
                    'date_confirmed': fields.Datetime.now() - timedelta(minutes=20)})
        self._run()
        self.assertEqual((item.state, item.result_status, item.retry_safe), ('failed', 'unknown', False))
        self.assertTrue(prospect.needs_check)

    # ------------------------------------------------------------------
    # Messages: re-read the thread right before sending
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_message_is_sent_after_fresh_read(self):
        self._start()
        persona, prospect = self._chat_prospect('')
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        item = self.Tools._queue_send('message', prospect, text='Hi Ali, thanks for connecting!', step=step)
        self._run()
        self.assertEqual(self._calls(tool='get_conversation')[0]['args'], {'linkedin_username': 'ali-raza'})
        self.assertEqual(self._calls(tool='send_message')[0]['args'],
                         {'linkedin_username': 'ali-raza', 'message': 'Hi Ali, thanks for connecting!',
                          'confirm_send': True})
        self.assertEqual((item.state, prospect.stage, prospect.current_step_id), ('done', 'messaged', step))
        self.assertEqual(self._actions(action='thread').reads, 1)

    @freeze_time(MONDAY_10_UTC)
    def test_stale_text_is_discarded_when_a_reply_arrived(self):
        self._start()
        persona, prospect = self._chat_prospect()
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        self.env['li.message'].create({'prospect_id': prospect.id, 'direction': 'out', 'kind': 'message',
                                       'body': 'Hi Ali, thanks for connecting!', 'ai_generated': True,
                                       'sender_name': 'Taha Sohail', 'state': 'sent'})
        prospect.write({'stage': 'messaged', 'current_step_id': step.id, 'awaiting_reply': True})
        nxt = persona.chat_agent_id.step_ids.sorted('sequence')[1]
        item = self.Tools._queue_send('message', prospect, text='Which platform do you use?', step=nxt)
        # the prospect wrote twice since the text was written
        self._script(get_conversation=[thread_data(THREAD)])
        self.profile.my_display_name = 'Taha Sohail'
        prospect.last_inbound_date = fields.Datetime.now()       # an earlier reply made step 2 due
        prospect.awaiting_reply = False
        self._run()
        self.assertFalse(self._calls(tool='send_message'))
        self.assertEqual(item.state, 'cancelled')
        self.assertTrue(item.discarded_stale)
        self.assertEqual(prospect.stage, 'replied')
        self.assertTrue(prospect.needs_analysis)

    @freeze_time(MONDAY_10_UTC)
    def test_manual_message_takes_over_before_send(self):
        self._start()
        persona, prospect = self._chat_prospect('Taha Sohail sent the following message at 9:00 AM\nTaha Sohail\n'
                                                'Hey Ali, Taha here — call tomorrow?')
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        item = self.Tools._queue_send('message', prospect, text='Hi Ali, thanks for connecting!', step=step)
        self._run()
        self.assertFalse(self._calls(tool='send_message'))
        self.assertTrue(prospect.is_taken_over)
        self.assertEqual(prospect.takeover_reason, 'human_message')
        self.assertEqual((item.state, item.discarded_stale), ('cancelled', True))

    @freeze_time(MONDAY_10_UTC)
    def test_line_breaks_become_spaces(self):
        """The engine refuses control characters (nothing may press Enter in the message box): every
        line break or tab becomes one space, the text is never refused for it."""
        self._start()
        persona, prospect = self._chat_prospect('')
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        item = self.Tools._queue_send('message', prospect, text='Hi Ali,\nthanks!\r\n\n\tSee you', step=step)
        self.assertEqual(item.text_confirmed, 'Hi Ali, thanks! See you')
        item.text_confirmed = 'Hi Ali,\nthanks!'                # e.g. edited by hand in the queue
        self._run()
        self.assertEqual(self._calls(tool='send_message')[0]['args']['message'], 'Hi Ali, thanks!')
        self.assertEqual(item.state, 'done')

    @freeze_time(MONDAY_10_UTC)
    def test_enter_to_send_asks_the_owner(self):
        self._start()
        persona, prospect = self._chat_prospect('')
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        self._script(send_message=[{'data': {'status': 'enter_to_send_enabled', 'sent': False, 'retry_safe': True}}])
        item = self.Tools._queue_send('message', prospect, text='Hi Ali!', step=step)
        self._run()
        self.assertEqual((item.state, item.send_attempts), ('queued', 1))
        self.assertTrue(self.profile.activity_ids.filtered(lambda a: 'Click Send' in a.summary))

    # ------------------------------------------------------------------
    # Inbox, threads, Activity Agent
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_inbox_reads_only_changed_threads(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        persona, prospect = self._chat_prospect()
        quiet = self._accepted(persona, username='sara-khan', name='Sara Khan')
        inbox = {'data': {'sections': {'inbox': 'Ali Raza\n10:20 AM\nWhat do you do exactly?\n'
                                                'Sara Khan\nOct 1\nYou: Hello'},
                          'references': {'inbox': [{'kind': 'conversation', 'url': '/messaging/thread/2-abc==/',
                                                    'text': 'Ali Raza'}]}}}
        quiet.inbox_preview_hash = inbox_preview(inbox['data'], 'Sara Khan')
        self._script(get_inbox=[inbox], get_conversation=[thread_data(THREAD)])
        self._run()
        self.assertEqual(len(self._calls(tool='get_inbox')), 1)
        threads = self._calls(tool='get_conversation')
        self.assertEqual(threads, [{'tool': 'get_conversation', 'args': {'thread_id': '2-abc=='}}])
        self.assertEqual(prospect.li_thread_id, '2-abc==')
        self.assertEqual(prospect.stage, 'replied')
        self.assertEqual(prospect.message_ids_li.filtered(lambda m: m.direction == 'in').mapped('body'),
                         ['Thanks Taha.', 'What do you do exactly?'])
        self.assertTrue(prospect.is_taken_over)            # "Hi Ali..." was not sent by an agent
        self.assertFalse(quiet.thread_check_needed)
        # within the inbox interval nothing is read again
        self._run()
        self.assertEqual(len(self._calls(tool='get_inbox')), 1)

    @freeze_time(MONDAY_10_UTC)
    def test_reply_of_taken_over_prospect_creates_activity(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        activity = self.env['li.activity.agent']._get()
        activity.action_run()
        persona, prospect = self._chat_prospect()
        prospect._take_over(user=self.rep)
        prospect.write({'thread_check_needed': True, 'li_thread_id': '2-abc'})
        self._script(get_conversation=[thread_data(
            'Ali Raza sent the following message at 11:00 AM\nAli Raza\nCan we talk tomorrow?')])
        self._run()
        self.assertTrue(prospect.reply_activity_id)
        self.assertEqual(prospect.reply_activity_id.user_id, self.rep)

    @freeze_time(MONDAY_10_UTC)
    def test_interface_text_never_takes_a_prospect_over(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        persona, prospect = self._chat_prospect()
        Message = self.env['li.message']
        Message.create({'prospect_id': prospect.id, 'direction': 'out', 'kind': 'message', 'ai_generated': True,
                        'body': 'Hi Ali, thanks for connecting!'})
        prospect.write({'thread_check_needed': True, 'li_thread_id': '2-abc', 'stage': 'messaged'})
        self._script(get_conversation=[thread_data(
            'Taha Sohail sent the following message at 10:51 PM\nTaha Sohail\nHi Ali, thanks for connecting!\n'
            'Your online status is visible. You can change this in your settings. Manage\nDismiss')])
        self._run()
        self.assertFalse(prospect.is_taken_over)
        self.assertEqual(prospect.message_ids_li.mapped('body'), ['Hi Ali, thanks for connecting!'])

    def test_repair_removes_stored_interface_text(self):
        persona = self._persona(run=('chat',))
        taken, replied = self._accepted(persona), self._accepted(persona, username='sara-khan', name='Sara Khan')
        Message = self.env['li.message']
        mk = lambda prospect, direction, kind, body, ai=False: Message.create({
            'prospect_id': prospect.id, 'direction': direction, 'kind': kind, 'body': body, 'ai_generated': ai})
        mk(taken, 'out', 'message', 'Hi Ali, thanks for connecting!', ai=True)
        mk(taken, 'out', 'manual', 'Your online status is visible. You can change this in your settings. Manage')
        mk(taken, 'out', 'manual', 'Dismiss')
        taken._take_over(user=self.rep, reason='human_message')
        mk(replied, 'in', 'reply', 'Thanks, Taha')
        mk(replied, 'in', 'reply', 'Reply to conversation with "Thanks Sara"')
        mk(replied, 'in', 'reply', 'Thanks Sara')
        self.assertEqual(self.env['li.prospect']._li_repair_ui_messages(), 4)
        self.assertEqual(taken.message_ids_li.mapped('body'), ['Hi Ali, thanks for connecting!'])
        self.assertFalse(taken.is_taken_over)
        self.assertEqual(replied.message_ids_li.mapped('body'), ['Thanks, Taha'])
        self.assertEqual(self.env['li.prospect']._li_repair_ui_messages(), 0)

    # ------------------------------------------------------------------
    # Prospect profiles
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_profile_is_read_before_the_chat_agent_writes(self):
        self._start()
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona, profile_text=False, profile_read_at=False)
        work = lambda: self.Tools._tool_li_get_work(linkedin_profile=self.profile.account_key)['items']
        self.assertEqual([i for i in work() if i['type'] == 'message'], [])       # waits for the profile
        self._script(get_person_profile=[{'data': {'sections': {
            'main_profile': 'Ali Raza\n\n  HR Manager at Brand X  \nAbout\nI look after people and payroll.'}}}])
        self._run()
        self.assertEqual(self._calls(tool='get_person_profile')[0]['args'], {'linkedin_username': 'ali-raza'})
        self.assertEqual(prospect.profile_text, 'Ali Raza\nHR Manager at Brand X\nAbout\nI look after people and payroll.')
        self.assertEqual(self._actions(action='person').reads, 1)
        item = [i for i in work() if i['type'] == 'message'][0]
        self.assertIn('HR Manager at Brand X', item['prospect']['profile'])
        self.assertIn('read who this person is in prospect.profile', item['instructions'])
        self.assertIn('judge its nature', item['instructions'])
        self._run()
        self.assertEqual(len(self._calls(tool='get_person_profile')), 1)          # read once per person
        # the same order reaches Claude wherever it starts from
        self.assertIn('prospect.profile', self.Tools._tool_li_overview()['before_writing'])
        from odoo.addons.linkedin_sales_automation.models.li_mcp_tools import TOOLS
        tools = {t['name']: t['description'] for t in TOOLS}
        for name in ('li_get_work', 'li_submit_text', 'li_check_inbox_now'):
            self.assertIn('judge its nature', tools[name])
        self.assertIn('prospect.profile', tools['li_record_analysis'])

    @freeze_time(MONDAY_10_UTC)
    def test_profile_that_cannot_be_read_does_not_block_the_chat_agent(self):
        self._start()
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona, profile_text=False, profile_read_at=False)
        empty = {'data': {'sections': {}}}
        self._script(get_person_profile=[empty, empty])
        self._run()
        with freeze_time('2026-10-12 10:03:00'):
            self._run()
        self.assertEqual((prospect.profile_read_tries, bool(prospect.profile_read_at)), (2, False))
        items = self.Tools._tool_li_get_work(linkedin_profile=self.profile.account_key)['items']
        self.assertTrue([i for i in items if i['type'] == 'message'])             # written from headline and title

    @freeze_time(MONDAY_10_UTC)
    def test_invite_keeps_the_profile_the_engine_read(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'data': {'status': 'connected', 'message': 'Connection request sent.',
                                                    'profile': 'Ali Raza\nFounder at Brand X\nLahore'}}])
        self._run()
        self.assertEqual(prospect.stage, 'invited')
        self.assertEqual(prospect.profile_text, 'Ali Raza\nFounder at Brand X\nLahore')
        self.assertTrue(prospect.profile_read_at)

    # ------------------------------------------------------------------
    # Acceptance checks
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_acceptance_checks_are_capped_and_spread(self):
        self._start()
        persona = self._persona()
        invited = [self._prospect(persona, 'p%s' % i, 'Person %s' % i, stage='invited',
                                  date_invited=fields.Datetime.now() - timedelta(days=i + 1)) for i in range(5)]
        oldest = invited[-1]
        self._script(search_people=[search_data((oldest.linkedin_username, oldest.name, 'Founder'))])
        checks = lambda: [c for c in self._calls(tool='search_people') if c['args'].get('network')]
        self._run()
        self.assertEqual(len(checks()), 3)                                  # acceptance_per_run
        self.assertEqual(checks()[0]['args'], {'keywords': 'Person 4', 'network': ['F']})
        self.assertEqual(oldest.stage, 'accepted')
        self._run()
        self.assertEqual(len(checks()), 3)                                  # spread: 60 min between batches
        with freeze_time('2026-10-12 11:01:00'):
            self._run()
        self.assertEqual(sorted(c['args']['keywords'] for c in checks()[3:]), ['Person 0', 'Person 1'])

    @freeze_time(MONDAY_10_UTC)
    def test_acceptance_from_recent_connections(self):
        self._start()
        persona = self._persona()
        invited = [self._prospect(persona, 'p%s' % i, 'Person %s' % i, stage='invited',
                                  date_invited=fields.Datetime.now() - timedelta(hours=i + 1)) for i in range(5)]
        self._script(get_recent_connections=[
            {'data': {'usernames': ['someone-else', invited[1].linkedin_username.upper(), invited[3].linkedin_username],
                      'count': 3}},
            {'data': {'usernames': [invited[0].linkedin_username, 'someone-else'], 'count': 2}}])
        lists = lambda: self._calls(tool='get_recent_connections')
        searches = lambda: [c for c in self._calls(tool='search_people') if c['args'].get('network')]
        self._run()
        self.assertEqual(len(lists()), 1)
        self.assertEqual([p.stage for p in invited], ['invited', 'accepted', 'invited', 'accepted', 'invited'])
        self.assertIn('recent connections', invited[1].message_ids[0].body)
        self.assertEqual(searches(), [])                 # the list worked: no per-person searches
        self._run()
        self.assertEqual(len(lists()), 1)                # every 15 minutes, not every run
        with freeze_time('2026-10-12 10:16:00'):
            self._run()
        self.assertEqual(len(lists()), 2)
        self.assertEqual(invited[0].stage, 'accepted')
        action = self.env['li.engine.action'].search([('action', '=', 'acceptance')], limit=1)
        self.assertEqual(action.reads, 1)

    @freeze_time(MONDAY_10_UTC)
    def test_acceptance_list_needs_invited_prospects(self):
        self._start()
        self._persona()
        self._run()
        self.assertEqual(self._calls(tool='get_recent_connections'), [])

    # ------------------------------------------------------------------
    # Budget, time, locks
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_read_budget(self):
        self._start()
        self.env['ir.config_parameter'].sudo().set_param('li_sales.read_budget', 2)
        persona = self._persona()
        for i in range(3):
            self._prospect(persona, 'p%s' % i, 'Person %s' % i, stage='invited',
                           date_invited=fields.Datetime.now() - timedelta(days=1))
        self._run()
        # 80% of 2 pages for background reading: the inbox read, then nothing more
        self.assertEqual([c['tool'] for c in self._calls()], ['get_inbox'])
        self.assertEqual(self.profile.reads_today, 1)

    @freeze_time(MONDAY_10_UTC)
    def test_no_call_without_time_left(self):
        self._start()
        self._prospect(self._persona())
        with patch.object(type(self.Tools), '_bg_time_limit', lambda self: 10):
            self._run()
        self.assertFalse(self._calls())

    @freeze_time(MONDAY_10_UTC)
    def test_profile_in_use_is_skipped(self):
        self._start()
        self._prospect(self._persona())
        with db_connect(self.env.cr.dbname).cursor() as other:     # another Odoo worker
            other.execute('SELECT pg_advisory_lock(%s, %s)', (74218302, self.profile.id))
            try:
                self._run()
            finally:
                other.execute('SELECT pg_advisory_unlock(%s, %s)', (74218302, self.profile.id))
        self.assertFalse(self._calls())
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)

    # ------------------------------------------------------------------
    # Account-level errors
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_session_expired_pauses_that_profile_only(self):
        self._start()
        self._start(self.profile2)
        persona = self._persona()
        other = self._persona('Other account', profile=self.profile2)
        prospect = self._prospect(persona)
        self._prospect(other, 'sara-khan', 'Sara Khan')
        self._script(connect_with_person=[{'error': 'Session expired. Run with --login to create a new browser '
                                                    'profile.'}])
        self._run()
        self.assertEqual(self.profile.connection_state, 'reconnect_needed')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual(prospect.stage, 'queued')
        self.assertFalse(prospect.needs_check)                 # nothing reached LinkedIn
        self.assertEqual(self.profile2.connection_state, 'connected')
        self.assertEqual(other.connection_agent_id.state, 'running')
        self.assertEqual(len(self._calls(self.profile2, 'connect_with_person')), 1)
        self.assertTrue(self.profile.activity_ids.filtered(lambda a: 'Reconnect' in a.summary))
        # its engine is stopped until Reconnect LinkedIn; the other one keeps running
        self.assertEqual((self.profile.engine_state, self.profile.engine_wanted), ('stopped', False))
        self.assertEqual(self.profile2.engine_state, 'running')

    @freeze_time(MONDAY_10_UTC)
    def test_engine_waiting_for_login_means_reconnect_needed(self):
        self._start()
        persona = self._persona()
        self._script(search_people=[{'error': 'A LinkedIn login window is open and login is still in progress. '
                                              'This is not a failure. Complete the sign-in in the browser, then '
                                              'call this exact tool again in about 30 seconds to resume.'}])
        self._run()
        self.assertEqual(self.profile.connection_state, 'reconnect_needed')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual(self.profile.engine_state, 'stopped')

    def test_run_stays_under_the_cron_limit(self):
        with patch.dict(config.options, {'limit_time_real_cron': -1, 'limit_time_real': 120}):
            self.assertEqual(self.Tools._bg_time_limit(), 105)
        with patch.dict(config.options, {'limit_time_real_cron': 600, 'limit_time_real': 120}):
            self.assertEqual(self.Tools._bg_time_limit(), 240)
        with patch.dict(config.options, {'limit_time_real_cron': 0, 'limit_time_real': 0}):
            self.assertEqual(self.Tools._bg_time_limit(), 240)

    @freeze_time(MONDAY_10_UTC)
    def test_restricted_account_stops_engine(self):
        self._start()
        persona = self._persona()
        self._prospect(persona)
        self._script(connect_with_person=[{'error': 'LinkedIn has restricted access to this account and asks '
                                                    'for identity verification.'}])
        self._run()
        self.assertEqual(self.profile.connection_state, 'restricted')
        self.assertEqual(persona.connection_agent_id.state, 'paused')
        self.assertEqual((self.profile.engine_state, self.profile.engine_wanted), ('stopped', False))

    @freeze_time(MONDAY_10_UTC)
    def test_rate_limit_backs_off(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'error': 'Rate limit detected. Wait 600 seconds before trying again.'}])
        self._run()
        self.assertEqual(self.profile.bg_paused_until, fields.Datetime.to_datetime('2026-10-12 10:10:00'))
        self.assertEqual(prospect.stage, 'queued')
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.confirmed), ('queued', False))
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)
        with freeze_time('2026-10-12 10:10:01'):
            self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 2)
        self.assertEqual(prospect.stage, 'invited')

    def test_chrome_profiles_are_left_alone(self):
        self.profile.execution_mode = 'chrome'
        self._prospect(self._persona())
        self.assertEqual(self._run(), 0)
