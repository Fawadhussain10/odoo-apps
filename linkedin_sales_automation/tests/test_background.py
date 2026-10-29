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


def sent_list(*usernames, complete=True, text=''):
    """LinkedIn's Sent invitations page as the engine returns it."""
    return {'data': {'usernames': list(usernames), 'count': len(usernames), 'complete': complete,
                     'page_text': text or 'Manage invitations Sent'}}


DIRECT_OK = {'data': {'status': 'connected', 'message': 'Invitation submitted (More menu). LinkedIn confirmed it.',
                      'confirmed': True, 'linkedin_notice': 'Invitation sent to Ali.', 'invite_dialog': '',
                      'route': 'More menu', 'direct': True}}


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
        persona = self._persona(job_titles='Founder', include_keywords='shopify', fit_check=False)
        self._script(search_people_filtered=[search_data(('ali-raza', 'Ali Raza', 'Founder at Brand X'),
                                                         ('sara-khan', 'Sara Khan', 'Co-Founder of a Shopify brand'))])
        self._run()
        call = self._calls(tool='search_people_filtered')[0]
        # LinkedIn's Title filter, 2nd/3rd-degree people, first page
        self.assertEqual(call['args'], {'keywords': 'Founder shopify', 'title': 'Founder', 'network': ['S', 'O'],
                                        'page': 1})
        prospects = self.env['li.prospect'].search([('persona_id', '=', persona.id)])
        self.assertEqual(sorted(prospects.mapped('linkedin_username')), ['ali-raza', 'sara-khan'])
        self.assertEqual(set(prospects.mapped('stage')), {'queued'})
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
        # a day later the agent runs again; only an invite verified as pending clears the count
        with freeze_time('2026-10-13 10:01:00'):
            self.env['li.connection.agent']._resume_due()
            self.assertEqual(agent.state, 'running')
            self._run()
            self.assertEqual(second.stage, 'invited')
            self.assertEqual(self.profile.invites_not_recorded, 2)
        self.assertEqual(third.stage, 'queued')
        self._script(get_sent_invitations=[sent_list('sara-khan')])
        with freeze_time('2026-10-13 10:12:00'):
            self._run()
            self.assertTrue(second.invite_verified_at)
            self.assertEqual(self.profile.invites_not_recorded, 0)

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
    def test_connect_hidden_in_the_more_menu_is_used_before_following(self):
        self._start()
        persona = self._persona()
        hidden = self._prospect(persona)
        self._script(connect_with_person=[{'data': {'status': 'follow_only', 'message': 'Follow only profile.'}}],
                     send_invite_direct=[DIRECT_OK])
        self._run()
        self.assertEqual(self._calls(tool='send_invite_direct')[0]['args'], {'linkedin_username': 'ali-raza'})
        self.assertEqual(hidden.stage, 'invited')                              # connected, not merely followed
        self.assertEqual(self._calls(tool='follow_person'), [])
        self.assertTrue(any('More menu' in (a.detail or '') for a in self._actions(action='invite')))

    def test_followed_people_get_one_more_try_for_connect(self):
        persona = self._persona()
        followed = self._prospect(persona, stage='followed')
        self.env['ir.config_parameter'].sudo().search([('key', '=', 'li_sales.followed_requeued')]).unlink()
        self.assertEqual(self.env['li.prospect']._li_requeue_followed_once(), 1)
        self.assertEqual(followed.stage, 'queued')
        followed.stage = 'followed'
        self.assertEqual(self.env['li.prospect']._li_requeue_followed_once(), 0)     # once only
        self.assertEqual(followed.stage, 'followed')

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
        self._script(send_message=[{'data': {'status': 'enter_to_send_enabled', 'sent': False, 'retry_safe': True}}],
                     use_click_to_send=[{'data': {'status': 'option_unavailable', 'retry_safe': True}}])
        item = self.Tools._queue_send('message', prospect, text='Hi Ali!', step=step)
        self._run()
        self.assertEqual((item.state, item.send_attempts), ('queued', 1))
        self.assertTrue(self.profile.activity_ids.filtered(lambda a: 'Click Send' in a.summary))

    @freeze_time(MONDAY_10_UTC)
    def test_enter_to_send_is_switched_and_the_text_goes_out(self):
        self._start()
        persona, prospect = self._chat_prospect('')
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        self._script(send_message=[{'data': {'status': 'enter_to_send_enabled', 'sent': False, 'retry_safe': True,
                                             'url': 'https://www.linkedin.com/messaging/compose/?x=1'}},
                                   {'data': {'status': 'sent', 'sent': True, 'retry_safe': False}}],
                     use_click_to_send=[{'data': {'status': 'click_to_send', 'retry_safe': True}}])
        item = self.Tools._queue_send('message', prospect, text='Hi Ali!', step=step)
        self._run()
        self.assertEqual(self._calls(tool='use_click_to_send')[0]['args'],
                         {'url': 'https://www.linkedin.com/messaging/compose/?x=1'})
        self.assertEqual((item.state, item.send_attempts, item.error), ('queued', 0, False))
        self.assertFalse(self.profile.activity_ids.filtered(lambda a: 'Click Send' in a.summary))
        self.assertEqual(persona.chat_agent_id.consecutive_errors, 0)
        with freeze_time('2026-10-12 10:20:00'):
            self._run()
        self.assertEqual(item.state, 'done')
        self.assertEqual([c['args']['message'] for c in self._calls(tool='send_message')], ['Hi Ali!', 'Hi Ali!'])

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
        self.assertEqual(self.env['li.prospect']._li_repair_ui_messages(force=True), 4)
        self.assertEqual(taken.message_ids_li.mapped('body'), ['Hi Ali, thanks for connecting!'])
        self.assertFalse(taken.is_taken_over)
        self.assertEqual(replied.message_ids_li.mapped('body'), ['Thanks, Taha'])
        self.assertEqual(self.env['li.prospect']._li_repair_ui_messages(force=True), 0)

    # ------------------------------------------------------------------
    # Invite verification
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_invite_is_verified_ten_minutes_later(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._run()
        self.assertEqual(prospect.stage, 'invited')
        self._run()
        self.assertEqual(self._calls(tool='get_sent_invitations'), [])         # not settled yet
        self._script(get_sent_invitations=[sent_list('someone-else', 'Ali-Raza')])
        with freeze_time('2026-10-12 10:11:00'):
            self._run()
        self.assertEqual(len(self._calls(tool='get_sent_invitations')), 1)
        self.assertTrue(prospect.invite_verified_at)                           # on LinkedIn's Sent list
        self.assertEqual(prospect.stage, 'invited')
        self.assertEqual(self._calls(tool='check_connection_state'), [])
        with freeze_time('2026-10-12 10:14:00'):
            self._run()
        self.assertEqual(len(self._calls(tool='get_sent_invitations')), 1)     # once per invite

    @freeze_time(MONDAY_10_UTC)
    def test_verify_invites_accepted_meanwhile_and_empty_list(self):
        self._start()
        persona = self._persona()
        mk = lambda key, name: self._prospect(persona, key, name, stage='invited',
                                              date_invited=fields.Datetime.now() - timedelta(hours=2))
        accepted, refused = mk('sara-khan', 'Sara Khan'), mk('omar-ali', 'Omar Ali')
        # LinkedIn says there is no pending invitation at all; Sara is found among the connections
        self._script(get_sent_invitations=[sent_list(text='You have no sent invitations')],
                     get_recent_connections=[{'data': {'usernames': ['Sara-Khan', 'someone'], 'count': 2}}],
                     check_connection_state=[self.CONNECT_SHOWN])
        self.assertEqual(self.Tools._cron_verify_invites(), 3)     # list, connections, Omar's own profile
        self.assertEqual((accepted.stage, refused.stage), ('accepted', 'queued'))

    @freeze_time(MONDAY_10_UTC)
    def test_verify_invites_asks_each_profile_when_connections_are_unreadable(self):
        self._start()
        persona = self._persona()
        mk = lambda key, name: self._prospect(persona, key, name, stage='invited',
                                              date_invited=fields.Datetime.now() - timedelta(hours=2))
        accepted, refused = mk('sara-khan', 'Sara Khan'), mk('omar-ali', 'Omar Ali')
        self._script(get_sent_invitations=[sent_list('someone-else')],
                     check_connection_state=[self.CONNECTED_SHOWN, self.CONNECT_SHOWN])
        self.assertEqual(self.Tools._cron_verify_invites(), 4)     # list, connections (empty), two profiles
        self.assertEqual(self._calls(tool='search_people_filtered'), [])
        self.assertEqual((accepted.stage, refused.stage), ('accepted', 'queued'))

    @freeze_time(MONDAY_10_UTC)
    def test_verify_invites_falls_back_to_the_profile_when_the_list_is_unreadable(self):
        self._start()
        persona = self._persona()
        mk = lambda key, name: self._prospect(persona, key, name, stage='invited',
                                              date_invited=fields.Datetime.now() - timedelta(hours=2))
        looks_pending, offered = mk('sara-khan', 'Sara Khan'), mk('omar-ali', 'Omar Ali')
        self._script(get_sent_invitations=[sent_list(complete=False, text='Something else')],
                     check_connection_state=[{'data': {'status': 'pending'}}, {'data': {'status': 'connectable'}}])
        self.Tools._cron_verify_invites()
        # "pending" read from the profile buttons is not proof: checked again later
        self.assertEqual((looks_pending.stage, bool(looks_pending.invite_verified_at)), ('invited', False))
        self.assertEqual(offered.stage, 'queued')

    @freeze_time(MONDAY_10_UTC)
    def test_cut_off_sent_list_never_proves_an_invite_is_missing(self):
        # LinkedIn shows the newest 10 first: an older real invitation is not on that page
        self._start()
        persona = self._persona()
        mk = lambda key, name: self._prospect(persona, key, name, stage='invited',
                                              date_invited=fields.Datetime.now() - timedelta(days=2))
        older, never_sent, unclear = mk('ali-raza', 'Ali Raza'), mk('sara-khan', 'Sara Khan'), mk('omar-ali', 'Omar Ali')
        newest_ten = sent_list(*['recent-%s' % i for i in range(10)])
        top = lambda button: 'Ali Raza\n· 3rd\nFounder\nLahore\nMessage\n%s\nMore\nAbout\nI run a brand.' % button
        self._script(
            get_sent_invitations=[newest_ten],
            check_connection_state=[
                {'data': {'status': 'pending', 'top_text': top('Pending')}},
                {'data': {'status': 'pending', 'top_text': top('Connect')}},     # the engine misreads this one
                {'data': {'status': 'pending', 'top_text': 'Ali Raza\nFollow\nMore\nAbout'}}])
        agent = persona.connection_agent_id
        self.Tools._cron_verify_invites()
        self.assertEqual(self._calls(tool='get_recent_connections'), [])       # absence proved nothing
        self.assertTrue(older.invite_verified_at)                              # its profile shows "Pending"
        self.assertEqual(older.stage, 'invited')
        self.assertEqual(never_sent.stage, 'queued')                           # its profile shows "Connect"
        self.assertEqual((unclear.stage, bool(unclear.invite_verified_at), unclear.invite_verify_tries),
                         ('invited', False, 1))                                # neither word: asked again later
        self.assertEqual(agent.state, 'running')

    @freeze_time(MONDAY_10_UTC)
    def test_invite_nobody_can_judge_is_left_to_a_person_after_three_tries(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona, stage='invited', date_invited=fields.Datetime.now() - timedelta(hours=2),
                                  invite_verify_tries=3)
        self.assertEqual(self.Tools._cron_verify_invites(), 0)                 # no more page reads for it
        self.assertEqual(prospect.stage, 'invited')
        self.assertFalse(self.Tools._bg_invites_on_probation(self.profile))    # and it does not hold invites back

    @freeze_time(MONDAY_10_UTC)
    def test_engine_pending_and_the_profile_shows_pending(self):
        # the engine is right: the invitation exists (sent by hand, or by an earlier run)
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'data': {
            'status': 'pending', 'message': 'Already pending.',
            'profile': 'Ali Raza\n· 3rd\nFounder\nMessage\nPending\nMore\nAbout\nI run a brand.'}}])
        self._run()
        self.assertEqual(prospect.stage, 'invited')
        self.assertTrue(prospect.invite_verified_at)
        self.assertEqual(self._calls(tool='send_invite_direct'), [])           # nothing is sent a second time
        self.assertEqual(self._calls(tool='get_sent_invitations'), [])         # and no page read was needed

    def test_earlier_profile_only_verifications_are_checked_again_once(self):
        persona = self._persona()
        prospect = self._prospect(persona, stage='invited', date_invited=fields.Datetime.now(),
                                  invite_verified_at=fields.Datetime.now())
        self.env['ir.config_parameter'].sudo().search([('key', '=', 'li_sales.invite_verify_sent_list')]).unlink()
        self.assertEqual(self.env['li.prospect']._li_reverify_invites(), 1)
        self.assertFalse(prospect.invite_verified_at)
        prospect.invite_verified_at = fields.Datetime.now()
        self.assertEqual(self.env['li.prospect']._li_reverify_invites(), 0)
        self.assertTrue(prospect.invite_verified_at)

    @freeze_time(MONDAY_10_UTC)
    def test_engine_says_pending_but_nothing_was_ever_sent(self):
        # the engine misreads some profiles as "already pending" and sends nothing
        self._start()
        persona = self._persona()
        misread = self._prospect(persona)
        really_pending = self._prospect(persona, 'sara-khan', 'Sara Khan')
        pending = {'data': {'status': 'pending', 'message': 'An invitation is already pending.'}}
        self._script(connect_with_person=[pending, pending], send_invite_direct=[DIRECT_OK],
                     get_sent_invitations=[sent_list('someone-else'), sent_list('sara-khan', 'someone-else')])
        self._run()
        # not on LinkedIn's Sent list: Odoo sends it through the invite link
        self.assertEqual(self._calls(tool='send_invite_direct')[0]['args'], {'linkedin_username': 'ali-raza'})
        self.assertEqual(misread.stage, 'invited')
        self.assertTrue(any('sent through the invite link' in (a.detail or '')
                            for a in self._actions(action='invite')))
        with freeze_time('2026-10-12 10:02:00'):
            self._run()
        # on the list: it really was pending already, nothing is sent twice
        self.assertEqual(len(self._calls(tool='send_invite_direct')), 1)
        self.assertEqual(really_pending.stage, 'invited')
        self.assertTrue(really_pending.invite_verified_at)

    @freeze_time(MONDAY_10_UTC)
    def test_invite_that_fails_for_one_person_does_not_pause_the_account(self):
        self._start()
        persona = self._persona()
        mk = lambda key, name: self._prospect(persona, key, name, stage='invited',
                                              date_invited=fields.Datetime.now() - timedelta(hours=2))
        needs_email, odd = mk('sara-khan', 'Sara Khan'), mk('omar-ali', 'Omar Ali')
        fine = mk('zara-noor', 'Zara Noor')
        self._script(
            get_sent_invitations=[sent_list('zara-noor'), sent_list('zara-noor')],
            get_recent_connections=[{'data': {'usernames': ['old-friend'], 'count': 1}}] * 2,
            check_connection_state=[self.CONNECT_SHOWN] * 3,           # their profiles offer Connect again
            check_invite_dialog=[
                {'data': {'status': 'email_required', 'text': 'Enter their email to connect'}},
                {'data': {'status': 'dialog', 'text': 'How do you know Omar?'}},
                {'data': {'status': 'dialog', 'text': 'How do you know Omar?'}}])
        agent = persona.connection_agent_id
        self.Tools._cron_verify_invites()
        self.assertTrue(fine.invite_verified_at)
        # LinkedIn wants her email address: a person decides, the account is not blamed
        self.assertEqual((needs_email.stage, needs_email.needs_check), ('queued', True))
        self.assertIn('email address', needs_email.needs_check_reason)
        # an unexplained miss for one person: back in the queue, what LinkedIn showed is kept
        self.assertEqual((odd.stage, odd.needs_check, odd.send_attempts), ('queued', False, 1))
        self.assertIn('How do you know Omar?', self._actions(action='invite_check')[0].detail)
        self.assertEqual(agent.state, 'running')                       # one odd person does not pause invites
        # the same person missed again: flagged for a person, and the queue moves on
        odd.write({'stage': 'invited', 'date_invited': fields.Datetime.now() - timedelta(hours=1)})
        self.Tools._cron_verify_invites()
        self.assertEqual((odd.stage, odd.needs_check), ('queued', True))
        self.assertIn('did not record 2 invitations', odd.needs_check_reason)
        self.assertEqual(agent.state, 'running')

    @freeze_time(MONDAY_10_UTC)
    def test_verify_invites_scheduled_action_works_through_a_backlog(self):
        self._start()
        persona = self._persona()
        invited = [self._prospect(persona, 'p%s' % i, 'Person %s' % i, stage='invited',
                                  date_invited=fields.Datetime.now() - timedelta(days=2, minutes=i)) for i in range(6)]
        self._script(get_sent_invitations=[sent_list('p1', 'p4', 'other')],
                     get_recent_connections=[{'data': {'usernames': ['old-friend', 'colleague'], 'count': 2}}],
                     check_connection_state=[self.CONNECT_SHOWN] * 4)
        cron = self.env.ref('linkedin_sales_automation.cron_verify_invites')
        self.assertEqual((cron.interval_number, cron.interval_type), (5, 'minutes'))
        # LinkedIn's Sent list, the newest connections, then the profile of each of the four not found
        self.assertEqual(self.Tools._cron_verify_invites(), 6)
        self.assertEqual(self._calls(tool='search_people_filtered'), [])
        self.assertEqual(sorted(p.stage for p in invited), ['invited'] * 2 + ['queued'] * 4)
        self.assertEqual(len([p for p in invited if p.invite_verified_at]), 2)
        self.assertEqual(self.Tools._cron_verify_invites(), 0)                 # nothing left to check

    @freeze_time(MONDAY_10_UTC)
    def test_invite_linkedin_never_recorded_goes_back_to_the_queue(self):
        # the engine said "sent", LinkedIn shows Connect again: nothing was sent
        self._start()
        persona = self._persona()
        first = self._prospect(persona)
        second = self._prospect(persona, 'sara-khan', 'Sara Khan')
        agent = persona.connection_agent_id
        self._run()
        with freeze_time('2026-10-12 10:02:00'):
            self._run()
        self.assertEqual((first.stage, second.stage), ('invited', 'invited'))
        self.assertEqual(self.env['li.event'].search_count([('event_type', '=', 'invite_sent')]), 2)
        # LinkedIn's Sent list has other people, not these two; neither is a connection
        self._script(get_sent_invitations=[sent_list('someone-else')],
                     check_connection_state=[self.CONNECT_SHOWN] * 2)
        with freeze_time('2026-10-12 10:13:00'):
            self._run()
        self.assertEqual((first.stage, second.stage), ('queued', 'queued'))
        self.assertEqual(len(self._calls(tool='check_connection_state')), 2)   # each profile confirms: Connect again
        self.assertFalse(first.date_invited)
        self.assertEqual(self.env['li.event'].search_count([('event_type', '=', 'invite_sent')]), 0)
        self.assertEqual(self.env['li.work.item'].search_count([('quota_consumed', '=', True)]), 0)
        self.assertEqual(agent.state, 'paused')
        self.assertIn('not recording invitations', agent.pause_reason)
        self.assertIn('did not record the invitation', first.message_ids[0].body)
        # a day later: one invite at a time until LinkedIn shows one as pending again
        with freeze_time('2026-10-13 10:14:00'):
            self.env['li.connection.agent']._resume_due()
            self._run()
            self.assertEqual(len(self._calls(tool='connect_with_person')), 3)
        with freeze_time('2026-10-13 10:16:00'):
            self._run()
            self.assertEqual(len(self._calls(tool='connect_with_person')), 3)   # waits for the verification
        self._script(get_sent_invitations=[sent_list('ali-raza', 'sara-khan')])
        with freeze_time('2026-10-13 10:25:00'):
            self._run()                                                        # now on LinkedIn's Sent list
            self.assertEqual(self.profile.invites_not_recorded, 0)
        with freeze_time('2026-10-13 10:27:00'):
            self._run()
            self.assertEqual(len(self._calls(tool='connect_with_person')), 4)   # normal sending again

    def test_prospect_fields_are_filled_and_misplaced_headlines_go_back(self):
        persona = self._persona()
        Prospect = self.env['li.prospect']
        mk = lambda key, **vals: Prospect.create(dict(
            {'name': key.title(), 'persona_id': persona.id, 'linkedin_url': 'https://www.linkedin.com/in/%s/' % key},
            **vals))
        plain = mk('plain', headline='Founder at Odoo Concepts', location='Pakistan')
        swapped = mk('swapped', location='CEO at Odoo Steer', profile_text=(
            'Swapped\n· 2nd\nODOO EXPERT\nIslamabad, Pakistan\n·\nContact info\nPAF College'))
        no_page = mk('nopage', location='Founder and CEO at Deploy Systems')
        typed = mk('typed', headline='CEO at Brand X', title='Chief of everything', company='My own name')
        self.assertEqual(Prospect._li_repair_prospect_fields(force=True) >= 4, True)
        self.assertEqual((plain.title, plain.company, plain.location), ('Founder', 'Odoo Concepts', 'Pakistan'))
        self.assertEqual((swapped.headline, swapped.location, swapped.title, swapped.company),
                         ('CEO at Odoo Steer', 'Islamabad, Pakistan', 'CEO', 'Odoo Steer'))
        self.assertEqual((no_page.headline, no_page.location, no_page.title, no_page.company),
                         ('Founder and CEO at Deploy Systems', False, 'Founder and CEO', 'Deploy Systems'))
        self.assertEqual((typed.title, typed.company), ('Chief of everything', 'My own name'))    # kept

    def test_search_line_values_are_replaced_from_the_profile_page(self):
        persona = self._persona()
        Prospect = self.env['li.prospect']
        page = ('Kamran Qureshi\n· 1st\nResident Manager, SJABEED Enterprises, Abu Dhabi\n'
                'Abu Dhabi Emirate, United Arab Emirates\n·\nContact info\nS J Abeed Enterprises')
        wrong = Prospect.create({'name': 'Kamran Qureshi', 'persona_id': persona.id,
                                 'linkedin_url': 'https://www.linkedin.com/in/kamran-q/', 'headline': 'See open roles',
                                 'title': 'See open roles', 'location': 'Sara Eid • 2nd', 'profile_text': page})
        right = Prospect.create({'name': 'Sara Eid', 'persona_id': persona.id,
                                 'linkedin_url': 'https://www.linkedin.com/in/sara-eid/',
                                 'headline': 'Human Resources Director', 'location': 'Dubai, United Arab Emirates',
                                 'profile_text': 'Sara Eid\n· 2nd\nHuman Resources Director\n'
                                                 'Dubai, United Arab Emirates\n·\nContact info'})
        self.assertTrue(Prospect._li_repair_search_line_fields(force=True) >= 2)
        self.assertEqual((wrong.headline, wrong.location),
                         ('Resident Manager, SJABEED Enterprises, Abu Dhabi', 'Abu Dhabi Emirate, United Arab Emirates'))
        self.assertTrue(wrong.title.startswith('Resident Manager'))           # not "See open roles" any more
        self.assertEqual((right.headline, right.location), ('Human Resources Director', 'Dubai, United Arab Emirates'))
        self.assertEqual(Prospect._li_repair_search_line_fields(), 0)          # once
        # the profile page read while the invite was pending is marked out of date once they accepted
        right.write({'profile_read_at': '2026-10-17 06:20:58', 'date_accepted': '2026-10-17 12:19:02',
                     'stage': 'accepted'})
        self.assertIn('connected since 2026-10-17 12:19 UTC', right._payload()['connection'])
        self.assertIn('out of date', right._payload()['connection'])
        self.assertEqual(wrong._payload()['connection'], 'not connected')

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
        self._script(search_people_filtered=[{'error': 'A LinkedIn login window is open and login is still in progress. '
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

    # ------------------------------------------------------------------
    # Closed people who reply later, thread priority and cap
    # ------------------------------------------------------------------
    def _reply_thread(self, name, text):
        return thread_data('%s sent the following message at 11:00 AM\n%s\n%s' % (name, name, text))

    def test_closed_people_who_reply_later_are_heard(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        persona = self._persona(run=('chat',))
        silent = self._prospect(persona, stage='no_response')
        refused = self._prospect(persona, 'sara-khan', 'Sara Khan', stage='not_interested', sequence_stopped=True,
                                 closing_pending=True)
        withdrawn = self._prospect(persona, 'omar-malik', 'Omar Malik', stage='withdrawn')
        quiet = self._prospect(persona, 'zara-ali', 'Zara Ali', stage='no_response')
        blocked = self._prospect(persona, 'bilal-aziz', 'Bilal Aziz', stage='not_interested', do_not_contact=True)
        closing = self.Tools._queue_send('message', refused, text='Good to hear, Sara. Best of luck.')
        closing.closing = True
        rows = [('Ali Raza', '2-a'), ('Sara Khan', '2-s'), ('Omar Malik', '2-o'), ('Zara Ali', '2-z'),
                ('Bilal Aziz', '2-b')]
        inbox = {'data': {'sections': {'inbox': '\n'.join('%s\n11:00 AM\nA new line' % n for n, _t in rows)},
                          'references': {'inbox': [{'kind': 'conversation', 'url': '/messaging/thread/%s/' % t,
                                                    'text': n} for n, t in rows]}}}
        quiet.inbox_preview_hash = inbox_preview(inbox['data'], 'Zara Ali')        # nothing new in her thread
        sara = self._reply_thread('Sara Khan', 'Actually, what would it cost?')
        self._script(get_inbox=[inbox], get_conversation=[
            sara,                                   # the fresh read before her closing message would go out
            sara,                                   # now a conversation in progress: opened before the closed ones
            self._reply_thread('Ali Raza', 'Sorry for the late answer, tell me more.'),
            self._reply_thread('Omar Malik', 'Hi, I just saw your request.')])
        self._run()
        # only the three changed threads were opened: the quiet one and the do-not-contact one cost nothing
        self.assertEqual([c['args'] for c in self._calls(tool='get_conversation')],
                         [{'linkedin_username': 'sara-khan'}, {'thread_id': '2-s'}, {'thread_id': '2-a'},
                          {'thread_id': '2-o'}])
        self.assertEqual(self._calls(tool='send_message'), [])
        self.assertEqual((silent.stage, silent.needs_analysis), ('replied', True))
        self.assertEqual((refused.stage, refused.needs_analysis, refused.closing_pending, refused.sequence_stopped),
                         ('replied', True, False, False))
        self.assertEqual(closing.state, 'cancelled')                   # the pending closing message is dropped
        self.assertEqual((withdrawn.stage, withdrawn.needs_analysis), ('replied', True))
        self.assertTrue(withdrawn.date_accepted)
        self.assertEqual(quiet.stage, 'no_response')
        self.assertFalse(blocked.thread_check_needed)
        self.assertEqual(len(self.env['li.event'].search([('event_type', '=', 'reply_received'),
                                                          ('persona_id', '=', persona.id)])), 3)

    def test_changed_threads_open_by_priority_and_are_capped_per_run(self):
        self._start()
        self.profile.write({'my_display_name': 'Taha Sohail', 'last_inbox_check': fields.Datetime.now()})
        self.env['ir.config_parameter'].sudo().set_param('li_sales.threads_per_run', 2)
        persona = self._persona(run=('chat',))
        read = {'profile_text': 'Founder', 'profile_read_at': fields.Datetime.now(), 'thread_check_needed': True}
        self._prospect(persona, 'p-closed', 'Closed One', stage='no_response', li_thread_id='t-closed', **read)
        self._prospect(persona, 'p-new', 'New One', stage='accepted', li_thread_id='t-accepted', **read)
        self._prospect(persona, 'p-active', 'Active One', stage='replied', li_thread_id='t-replied', **read)
        self._run()
        self.assertEqual([c['args']['thread_id'] for c in self._calls(tool='get_conversation')],
                         ['t-replied', 't-accepted'])                  # the closed one waits for the next run
        self._run()
        self.assertEqual([c['args']['thread_id'] for c in self._calls(tool='get_conversation')],
                         ['t-replied', 't-accepted', 't-closed'])

    def test_failed_thread_read_is_tried_again(self):
        self._start()
        self.profile.write({'my_display_name': 'Taha Sohail', 'last_inbox_check': fields.Datetime.now()})
        persona, prospect = self._chat_prospect()
        prospect.write({'thread_check_needed': True, 'li_thread_id': '2-abc'})
        self._script(get_conversation=[{'error': 'Tool get_conversation timed out after 60 seconds'},
                                       self._reply_thread('Ali Raza', 'Can we talk tomorrow?')])
        self._run()
        self.assertEqual((prospect.thread_check_needed, prospect.thread_read_tries, prospect.stage),
                         (True, 1, 'accepted'))                        # still marked: nothing is lost
        self._run()
        self.assertEqual((prospect.thread_check_needed, prospect.thread_read_tries, prospect.stage),
                         (False, 0, 'replied'))
        self.assertEqual(prospect.message_ids_li.mapped('body'), ['Can we talk tomorrow?'])

    @freeze_time(MONDAY_10_UTC)
    def test_no_conversation_found_sends_a_first_message(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        persona, prospect = self._chat_prospect()
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        # nobody has written yet: LinkedIn has no conversation, which is what Claude wrote from
        self._script(get_conversation=[{'error': 'Could not find a conversation for ali-raza.'}])
        item = self.Tools._queue_send('message', prospect, text='Hi Ali, thanks for connecting!', step=step)
        self._run()
        self.assertEqual([c['args']['message'] for c in self._calls(tool='send_message')],
                         ['Hi Ali, thanks for connecting!'])
        self.assertEqual(item.state, 'done')
        self.assertFalse(prospect.needs_check)

    @freeze_time(MONDAY_10_UTC)
    def test_no_conversation_found_is_never_empty_when_odoo_has_messages(self):
        self._start()
        self.profile.my_display_name = 'Taha Sohail'
        persona, prospect = self._chat_prospect()
        step = persona.chat_agent_id.step_ids.sorted('sequence')[0]
        self.env['li.message'].create({'prospect_id': prospect.id, 'direction': 'out', 'kind': 'manual',
                                       'state': 'sent', 'body': 'Hello Ali', 'sender_name': 'Taha Sohail'})
        # the lookup by name misses a conversation Odoo knows exists (no thread id saved)
        self._script(get_conversation=[{'error': 'Could not find a conversation for ali-raza.'}])
        item = self.Tools._queue_send('message', prospect, text='Hi Ali, thanks for connecting!', step=step)
        self._run()
        self.assertFalse(self._calls(tool='send_message'))                 # never sent blind
        self.assertEqual((item.state, item.cancel_reason),
                         ('cancelled', 'the conversation could not be read before sending'))
        self.assertTrue(prospect.needs_check)
        self.assertIn('Odoo has 1 message(s) with them', prospect.needs_check_reason)
        self._run()
        self.assertEqual(len(self._calls(tool='get_conversation')), 1)      # no read again while flagged

    def test_thread_that_keeps_failing_is_left_alone_after_five_tries(self):
        self._start()
        self.profile.write({'my_display_name': 'Taha Sohail', 'last_inbox_check': fields.Datetime.now()})
        persona, prospect = self._chat_prospect()
        gone = self._accepted(persona, username='sara-khan', name='Sara Khan', thread_check_needed=True)
        prospect.write({'thread_check_needed': True, 'li_thread_id': '2-abc', 'thread_read_tries': 4})
        self._script(get_conversation=[{'error': 'Something went wrong on the page'},
                                       {'error': 'Profile not found'}])
        self._run()
        self.assertEqual((prospect.thread_check_needed, prospect.thread_read_tries), (False, 0))
        self.assertFalse(gone.thread_check_needed)                     # a profile that no longer exists

    # ------------------------------------------------------------------
    # Connect before Follow, never Follow while an invitation may exist
    # ------------------------------------------------------------------
    FOLLOW_ONLY = {'data': {'status': 'follow_only', 'message': 'Follow only profile.'}}

    def _time_for(self, answers):
        """_bg_time_for answering from a list, then False."""
        answers = list(answers)
        return patch.object(type(self.Tools), '_bg_time_for',
                            lambda self, deadline, calls=1: answers.pop(0) if answers else False)

    @freeze_time(MONDAY_10_UTC)
    def test_nobody_is_followed_when_time_is_short_for_the_connect_routes(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[self.FOLLOW_ONLY, self.FOLLOW_ONLY])
        with self._time_for([]):
            self._run()
        self.assertEqual(self._calls(tool='send_invite_direct'), [])
        self.assertEqual(self._calls(tool='follow_person'), [])
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((prospect.stage, prospect.needs_check, item.state, item.quota_consumed),
                         ('queued', False, 'queued', False))           # skipped for this run only
        self.profile.last_send_at = False
        self._run()
        self.assertEqual(len(self._calls(tool='send_invite_direct')), 1)   # now every route is tried first
        self.assertEqual(prospect.stage, 'followed')

    @freeze_time(MONDAY_10_UTC)
    def test_follow_waits_for_the_next_run_without_trying_connect_again(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[self.FOLLOW_ONLY])
        with self._time_for([True]):                   # time for the Connect routes, none left for Follow
            self._run()
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.connect_tried, prospect.stage), ('queued', True, 'queued'))
        self.assertEqual(self._calls(tool='follow_person'), [])
        self.profile.last_send_at = False
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)
        self.assertEqual(len(self._calls(tool='send_invite_direct')), 1)
        self.assertEqual(len(self._calls(tool='follow_person')), 1)
        self.assertEqual(prospect.stage, 'followed')

    @freeze_time(MONDAY_10_UTC)
    def test_connect_routes_that_fail_never_end_in_a_follow(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        broken = {'error': 'Something went wrong on the page'}
        self._script(connect_with_person=[self.FOLLOW_ONLY] * 3, send_invite_direct=[broken] * 3)
        for attempt in (1, 2):
            self.profile.last_send_at = False
            self._run()
            item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
            self.assertEqual((item.state, item.send_attempts, prospect.stage), ('queued', attempt, 'queued'))
        self.profile.last_send_at = False
        self._run()
        self.assertEqual(self._calls(tool='follow_person'), [])
        self.assertEqual((prospect.stage, prospect.needs_check), ('queued', True))     # a person looks at it

    @freeze_time(MONDAY_10_UTC)
    def test_connect_pressed_without_proof_is_settled_by_the_sent_list(self):
        self._start()
        persona = self._persona()
        on_list = self._prospect(persona)
        not_sent = self._prospect(persona, 'sara-khan', 'Sara Khan')
        unclear = self._prospect(persona, 'omar-malik', 'Omar Malik')
        maybe = {'data': {'status': 'maybe_sent', 'route': 'More menu', 'direct': True, 'confirmed': False,
                          'message': 'Connect was pressed but LinkedIn showed nothing.'}}
        self._script(connect_with_person=[self.FOLLOW_ONLY] * 3, send_invite_direct=[maybe] * 3,
                     get_sent_invitations=[sent_list('ali-raza', 'someone-else'), sent_list('someone-else'),
                                           sent_list('someone-else', complete=False)])
        self._run()
        self.assertEqual(on_list.stage, 'invited')                     # the invitation exists: never followed
        self.assertTrue(on_list.invite_verified_at)
        self.assertEqual(self._calls(tool='follow_person'), [])
        self.profile.last_send_at = False
        self._run()
        self.assertEqual(not_sent.stage, 'followed')                   # the whole list, without them: no Connect
        self.assertEqual(len(self._calls(tool='follow_person')), 1)
        self.profile.last_send_at = False
        self._run()
        self.assertEqual((unclear.stage, unclear.needs_check), ('queued', True))   # unknown: a person checks
        self.assertEqual(len(self._calls(tool='follow_person')), 1)
        self.assertIn('unknown', unclear.needs_check_reason.lower())

    @freeze_time(MONDAY_10_UTC)
    def test_profile_that_shows_pending_is_invited_not_followed(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'data': {
            'status': 'follow_only', 'message': 'Follow only profile.',
            'profile': 'Ali Raza\nFounder at Brand X\nLahore\nPending\nMessage\nAbout\nI run a brand.'}}])
        self._run()
        self.assertEqual(self._calls(tool='send_invite_direct'), [])
        self.assertEqual(self._calls(tool='follow_person'), [])
        self.assertEqual(prospect.stage, 'invited')
        self.assertTrue(prospect.invite_verified_at)

    # ------------------------------------------------------------------
    # A file shared in the chat
    # ------------------------------------------------------------------
    def test_shared_file_is_one_message(self):
        self._start()
        self.profile.write({'my_display_name': 'Taha Sohail', 'last_inbox_check': fields.Datetime.now()})
        persona, prospect = self._chat_prospect()
        prospect.write({'thread_check_needed': True, 'li_thread_id': '2-abc'})
        self._script(get_conversation=[thread_data(
            'Ali Raza sent the following messages at 8:35 PM\nAli Raza\nHere it is.\n'
            'Ali Raza - Odoo Functional Resume.pdf\n185 KB\nDownload')])
        self._run()
        self.assertEqual(prospect.message_ids_li.mapped('body'),
                         ['Here it is.', '[Attachment] Ali Raza - Odoo Functional Resume.pdf (185 KB)'])
        # the same thread read again adds nothing
        prospect.thread_check_needed = True
        self._script(get_conversation=[thread_data(
            'Ali Raza sent the following messages at 8:35 PM\nAli Raza\nHere it is.\n'
            'Ali Raza - Odoo Functional Resume.pdf\n185 KB\nDownload')])
        self._run()
        self.assertEqual(len(prospect.message_ids_li), 2)

    def test_files_stored_as_three_messages_are_merged_once(self):
        persona = self._persona(run=('chat',))
        prospect = self._accepted(persona)
        Message = self.env['li.message']
        for body in ('Just in case, my resume:', 'Resume.pdf', '185 KB', 'Download', 'Download'):
            Message.create({'prospect_id': prospect.id, 'direction': 'in', 'kind': 'reply', 'body': body})
        self.env['ir.config_parameter'].sudo().search([('key', '=', 'li_sales.attachments_merged')]).unlink()
        self.assertEqual(self.env['li.prospect']._li_merge_attachment_messages(), 1)
        self.assertEqual(prospect.message_ids_li.sorted('id').mapped('body'),
                         ['Just in case, my resume:', '[Attachment] Resume.pdf (185 KB)', 'Download'])
        self.assertEqual(self.env['li.prospect']._li_merge_attachment_messages(), 0)       # once only

    # ------------------------------------------------------------------
    # Batch 2: read budget, invite verification, token limits, one-time repairs
    # ------------------------------------------------------------------
    CONNECT_SHOWN = {'data': {'status': 'connectable', 'seen': ['connectable', 'connectable'],
                              'top_text': 'Someone\nFounder\nConnect\nMessage\nAbout\nText'}}
    PENDING_SHOWN = {'data': {'status': 'pending', 'seen': ['pending', 'pending'],
                              'top_text': 'Someone\nFounder\nPending\nMessage\nAbout\nText'}}
    CONNECTED_SHOWN = {'data': {'status': 'already_connected', 'seen': ['already_connected'],
                                'top_text': 'Someone\n· 1st\nFounder\nMessage\nAbout\nText'}}

    def test_inbox_is_read_fast_only_in_working_hours(self):
        self.env['ir.config_parameter'].sudo().set_param('li_sales.inbox_interval', 5)
        monday = self.env['li.weekday'].search([('code', '=', 0)])
        self._persona(run=('chat',), days=monday, chat_send_window_from=9.0, chat_send_window_to=17.0)
        with freeze_time('2026-10-12 10:00:00'):                       # Monday, inside the window
            self.assertEqual(self.Tools._bg_inbox_minutes(self.profile), 15)     # never below 15 minutes
        with freeze_time('2026-10-12 22:00:00'):                       # Monday night
            self.assertEqual(self.Tools._bg_inbox_minutes(self.profile), 60)
        with freeze_time('2026-10-13 10:00:00'):                       # Tuesday: not a working day here
            self.assertEqual(self.Tools._bg_inbox_minutes(self.profile), 60)
        self.assertEqual(self.Tools._bg_inbox_minutes(self.profile2), 60)      # no persona at all

    @freeze_time('2026-10-12 22:00:00')
    def test_night_inbox_waits_an_hour(self):
        self._start()
        self.env['ir.config_parameter'].sudo().set_param('li_sales.inbox_interval', 5)
        persona = self._persona(run=('chat',), chat_send_window_from=9.0, chat_send_window_to=17.0)
        self._accepted(persona)
        self.profile.last_inbox_check = fields.Datetime.now() - timedelta(minutes=20)
        self._run()
        self.assertEqual(self._calls(tool='get_inbox'), [])
        self.profile.last_inbox_check = fields.Datetime.now() - timedelta(minutes=61)
        self._run()
        self.assertEqual(len(self._calls(tool='get_inbox')), 1)

    @freeze_time(MONDAY_10_UTC)
    def test_frequent_reads_leave_room_for_verification_profiles_and_search(self):
        self.env['ir.config_parameter'].sudo().set_param('li_sales.read_budget', 10)
        Action = self.env['li.engine.action']
        for action in ('inbox', 'thread', 'acceptance', 'inbox', 'thread', 'inbox'):
            Action.create({'linkedin_profile_id': self.profile.id, 'action': action, 'reads': 1})
        self.assertEqual(self.Tools._bg_routine_left(self.profile), 0)     # inbox, threads, acceptances: 60%
        self.assertEqual(self.Tools._bg_budget_left(self.profile), 2)      # still free for the rest
        Action.create({'linkedin_profile_id': self.profile.id, 'action': 'invite_verify', 'reads': 1})
        self.assertEqual(self.Tools._bg_budget_left(self.profile), 1)
        self._start()
        persona = self._persona(run=('chat',))
        self._accepted(persona, thread_check_needed=True)
        self._run()
        self.assertEqual(self._calls(tool='get_inbox'), [])
        self.assertEqual(self._calls(tool='get_conversation'), [])

    def test_only_invitation_rows_can_prove_the_sent_list_whole(self):
        names = ['p%s' % i for i in range(12)]
        proven = lambda **data: self.Tools._bg_sent_list(dict({'usernames': names, 'complete': True}, **data), None)[1]
        self.assertTrue(proven(total=12, rows_only=True))
        self.assertFalse(proven(total=12, rows_only=False))        # any link of the page: suggested people too
        self.assertFalse(proven(total=11, rows_only=True))         # more names than invitations: not the rows
        self.assertFalse(proven(total=30, rows_only=True))         # cut off
        self.assertTrue(proven(total=12))                          # an engine without the flag: as before

    @freeze_time(MONDAY_10_UTC)
    def test_invite_gone_from_the_list_is_judged_by_the_profile(self):
        self._start()
        persona = self._persona()
        ago = lambda **delta: fields.Datetime.now() - timedelta(**delta)
        old = self._prospect(persona, 'old-one', 'Old One', stage='invited', date_invited=ago(days=3))
        pending = self._prospect(persona, 'still-pending', 'Still Pending', stage='invited', date_invited=ago(hours=2))
        accepted = self._prospect(persona, 'now-connected', 'Now Connected', stage='invited',
                                  date_invited=ago(hours=2))
        fresh = self._prospect(persona, 'never-recorded', 'Never Recorded', stage='invited',
                               date_invited=ago(hours=2))
        self._script(get_sent_invitations=[sent_list('someone-else')],
                     check_connection_state=[self.CONNECT_SHOWN, self.PENDING_SHOWN, self.CONNECTED_SHOWN,
                                             self.CONNECT_SHOWN])
        self.Tools._cron_verify_invites()
        self.assertEqual([c['args']['linkedin_username'] for c in self._calls(tool='check_connection_state')],
                         ['old-one', 'still-pending', 'now-connected', 'never-recorded'])
        self.assertEqual(old.stage, 'queued')          # never seen on the list, however old: not "declined"
        self.assertEqual((pending.stage, bool(pending.invite_verified_at)), ('invited', True))
        self.assertEqual(accepted.stage, 'accepted')
        self.assertEqual(fresh.stage, 'queued')                        # LinkedIn never recorded it: sent again

    @freeze_time(MONDAY_10_UTC)
    def test_verified_invite_that_disappears_is_declined_not_invited_again(self):
        self._start()
        persona = self._persona()
        ago = lambda **delta: fields.Datetime.now() - timedelta(**delta)
        other = self._persona('Second persona', run=())
        seen = dict(stage='invited', date_invited=ago(days=3), invite_verified_at=ago(days=2))
        declined = self._prospect(persona, 'said-no', 'Said No', **seen)
        accepted = self._prospect(persona, 'said-yes', 'Said Yes', **seen)
        waiting = self._prospect(persona, 'still-there', 'Still There', **seen)
        self._script(get_sent_invitations=[sent_list('still-there')],
                     get_recent_connections=[{'data': {'usernames': ['said-yes'], 'count': 1}}],
                     check_connection_state=[self.CONNECT_SHOWN])
        self.Tools._cron_verify_invites()                              # no new invite: the daily comparison
        self.assertEqual((declined.stage, accepted.stage, waiting.stage), ('declined', 'accepted', 'invited'))
        self.assertEqual(len(self._calls(tool='check_connection_state')), 1)
        self.assertEqual(self.profile.invites_not_recorded, 0)         # about the person, not the account
        self.Tools._cron_verify_invites()                              # not read again within the day
        self.assertEqual(len(self._calls(tool='get_sent_invitations')), 1)
        self.assertTrue(self.env['li.event'].search([('prospect_id', '=', declined.id),
                                                     ('event_type', '=', 'invite_withdrawn')]))
        # declined once: never invited again, by any persona, not even on request
        other.connection_agent_id.skip_if_contacted = False
        counts = self.Tools._add_people(other, [{'name': 'Said No', 'linkedin_url': declined.linkedin_url}])
        self.assertEqual((counts['created'], counts['contacted_elsewhere']), (0, 1))
        answer = self.call('li_invite_person', linkedin_url=declined.linkedin_url, linkedin_profile='taha',
                           persona=str(other.id))
        self.assertFalse(answer['ok'])
        self.assertIn('declined', answer['message'])
        # a new day: the list is compared again
        with freeze_time('2026-10-13 10:01:00'):
            self.Tools._cron_verify_invites()
        self.assertEqual(len(self._calls(tool='get_sent_invitations')), 2)

    def test_limited_connector_counts_only_its_own_profiles(self):
        mine = self._persona('Mine', run=())
        theirs = self._persona('Theirs', profile=self.profile2, run=())
        Event = self.env['li.event']
        Event._log('invite_sent', 'connection', persona=mine, detail='one')
        Event._log('invite_sent', 'connection', persona=theirs, detail='two')
        Event._log('invite_sent', 'connection', persona=theirs, detail='three')
        overdue = self._prospect(theirs, stage='replied')
        activity = self.env['mail.activity'].create({
            'res_model_id': self.env['ir.model']._get_id('li.prospect'), 'res_id': overdue.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id, 'user_id': self.rep.id})
        overdue.write({'reply_activity_id': activity.id, 'reply_due_at': fields.Datetime.now() - timedelta(days=1)})
        limited = self.Tools.with_context(li_allowed_profile_ids=[self.profile.id])
        overview = limited._tool_li_overview()
        self.assertEqual([p['linkedin_profile'] for p in overview['profiles']], [self.profile.account_key])
        self.assertEqual([p['name'] for p in overview['personas']], ['Mine'])
        self.assertEqual(overview['activity_agent']['overdue_reply_activities'], 0)
        self.assertEqual(self.Tools._tool_li_overview()['activity_agent']['overdue_reply_activities'], 1)
        result = limited._tool_li_finish_run(summary='done')
        self.assertEqual([(a['linkedin_profile'], a['invites']) for a in result['accounts']],
                         [(self.profile.account_key, 1)])
        notes = lambda persona: [m for m in persona.message_ids if 'Run finished' in (m.body or '')]
        self.assertEqual((len(notes(mine)), len(notes(theirs))), (1, 0))
        run = self.env['li.claude.run'].browse(result['run_id'])
        self.assertFalse(self.profile2 in run.linkedin_profile_ids)
        # the other profile's run is its own: it still sees its two invites
        full = self.Tools.with_context(li_allowed_profile_ids=[self.profile2.id])._tool_li_finish_run(summary='x')
        self.assertEqual([(a['linkedin_profile'], a['invites']) for a in full['accounts']],
                         [(self.profile2.account_key, 2)])

    def test_repairs_run_once_not_on_every_upgrade(self):
        Prospect = self.env['li.prospect']
        persona = self._persona(run=())
        self.env['ir.config_parameter'].sudo().search([('key', 'in', (
            'li_sales.repaired_prospect_fields', 'li_sales.repaired_mojibake', 'li_sales.repaired_ui_messages'))]).unlink()
        first = self._prospect(persona, headline='CEO at Brand X')
        self.assertTrue(Prospect._li_repair_prospect_fields() >= 1)
        self.assertEqual(first.company, 'Brand X')
        second = self._prospect(persona, 'sara-khan', 'Sara Khan', headline='CTO at Other Co')
        self.assertEqual(Prospect._li_repair_prospect_fields(), 0)     # the next upgrade does not run it again
        self.assertFalse(second.company)
        self.assertTrue(Prospect._li_repair_mojibake() >= 0)
        self.assertTrue(Prospect._li_repair_ui_messages() >= 0)
        second.name = 'ZoÃ« Khan'
        self.env['li.message'].create({'prospect_id': second.id, 'direction': 'in', 'kind': 'reply',
                                       'body': 'Dismiss'})
        self.assertEqual(Prospect._li_repair_mojibake(), 0)
        self.assertEqual(Prospect._li_repair_ui_messages(), 0)
        self.assertEqual(second.name, 'ZoÃ« Khan')

    @freeze_time(MONDAY_10_UTC)
    def test_manager_may_allow_a_declined_person_to_be_invited_again(self):
        from odoo.exceptions import UserError
        self._start()
        persona = self._persona()
        other = self._persona('Second persona', run=())
        declined = self._prospect(persona, stage='declined', date_invited=fields.Datetime.now() - timedelta(days=5),
                                  invite_verified_at=fields.Datetime.now() - timedelta(days=4))
        with self.assertRaises(UserError):
            declined.with_user(self.rep).action_allow_invite_again()       # not a manager
        self.assertEqual(declined.stage, 'declined')
        declined.with_user(self.manager).action_allow_invite_again()
        self.assertEqual((declined.stage, declined.date_invited, declined.invite_verified_at),
                         ('queued', False, False))
        self.assertTrue(any('allowed a new invitation' in (m.body or '') and m.author_id == self.manager.partner_id
                            for m in declined.message_ids))                # logged, with who did it
        self.assertEqual(self.Tools._add_people(other, [{'name': 'Ali Raza', 'linkedin_url': declined.linkedin_url}])
                         ['contacted_elsewhere'], 1)                       # the usual rules apply again
        self._run()
        self.assertEqual(len(self._calls(tool='connect_with_person')), 1)  # really invited again
        self.assertEqual(declined.stage, 'invited')
        # the Connection Agent is stopped: allowed, but waiting on hold
        waiting = self._prospect(other, 'sara-khan', 'Sara Khan', stage='declined')
        waiting.with_user(self.manager).action_allow_invite_again()
        self.assertEqual(waiting.stage, 'held')
        blocked = self._prospect(other, 'omar-malik', 'Omar Malik', stage='declined', do_not_contact=True)
        with self.assertRaises(UserError):
            blocked.with_user(self.manager).action_allow_invite_again()

    @freeze_time(MONDAY_10_UTC)
    def test_verification_log_says_where_the_names_came_from(self):
        self._start()
        persona = self._persona()
        mk = lambda key, name: self._prospect(persona, key, name, stage='invited',
                                              date_invited=fields.Datetime.now() - timedelta(hours=2))
        mk('ali-raza', 'Ali Raza')
        last = lambda: self._actions(action='invite_verify').sorted('id')[-1].detail
        rows = sent_list('ali-raza', 'someone-else')
        rows['data'].update(rows_only=True, total=2)
        self._script(get_sent_invitations=[rows])
        self.Tools._cron_verify_invites()
        self.assertIn('source: invitation rows, proven whole: yes', last())
        sara = mk('sara-khan', 'Sara Khan')
        links = sent_list('someone-else', 'suggested-person')
        links['data'].update(rows_only=False, total=2)
        self._script(get_sent_invitations=[links], check_connection_state=[self.PENDING_SHOWN])
        self.Tools._cron_verify_invites()
        listed = self._actions(action='invite_verify').filtered(lambda a: 'Sent list' in (a.detail or '')).sorted('id')
        self.assertIn('source: fallback (profile checks), proven whole: no', listed[-1].detail)
        self.assertEqual(len(self._calls(tool='check_connection_state')), 1)   # and the profile was checked
        self.assertTrue(sara.invite_verified_at)
        self._prospect(persona, 'omar-malik', 'Omar Malik', stage='invited',
                       date_invited=fields.Datetime.now() - timedelta(hours=2))
        self._script(get_sent_invitations=[sent_list('omar-malik')])           # an engine that does not say
        self.Tools._cron_verify_invites()
        listed = self._actions(action='invite_verify').filtered(lambda a: 'Sent list' in (a.detail or '')).sorted('id')
        self.assertIn('source: not stated by the engine', listed[-1].detail)

    # ------------------------------------------------------------------
    # A profile that shows Connect is never followed
    # ------------------------------------------------------------------
    CONNECT_PAGE = ('Daniel Chao\n· 2nd\nArea Manager | Odoo Functional Consultant\nGreater Manresa Metropolitan Area\n'
                    'Contact info\nConnect\nMessage\nMore\nAbout\nI like technology.')

    @freeze_time(MONDAY_10_UTC)
    def test_profile_showing_connect_is_never_followed_when_odoo_cannot_press_it(self):
        # the engine misreads the profile as "pending", the Sent list has no invitation, and no route
        # opens the invite dialog although the page plainly offers Connect
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona, 'dchao', 'Daniel Chao')
        pending = {'data': {'status': 'pending', 'message': 'Already pending.', 'profile': self.CONNECT_PAGE}}
        self._script(connect_with_person=[pending] * 3,
                     get_sent_invitations=[sent_list('someone-else')] * 3)      # the whole list, without him
        for attempt in (1, 2):
            self.profile.last_send_at = False
            self._run()
            item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
            self.assertEqual((item.state, item.send_attempts, item.connect_tried, prospect.stage),
                             ('queued', attempt, False, 'queued'))
        self.profile.last_send_at = False
        self._run()
        self.assertEqual(self._calls(tool='follow_person'), [])                # never followed
        self.assertEqual(len(self._calls(tool='send_invite_direct')), 3)
        self.assertEqual((prospect.stage, prospect.needs_check), ('queued', True))
        self.assertIn('shows a Connect button', prospect.needs_check_reason)
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.result_status, item.quota_consumed), ('failed', 'connect_not_pressed', False))
        self.assertEqual(persona.connection_agent_id.state, 'running')         # about this person, not the account

    @freeze_time(MONDAY_10_UTC)
    def test_follow_only_engine_answer_with_connect_on_the_page_is_not_followed(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona, 'dchao', 'Daniel Chao')
        self._script(connect_with_person=[{'data': {'status': 'follow_only', 'message': 'Follow only profile.',
                                                    'profile': self.CONNECT_PAGE}}])
        self._run()                                    # the routes find nothing (default answer)
        self.assertEqual(self._calls(tool='follow_person'), [])
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.send_attempts, prospect.stage), ('queued', 1, 'queued'))
        # the next try gets through: invited
        self.profile.last_send_at = False
        self._script(connect_with_person=[{'data': {'status': 'follow_only', 'profile': self.CONNECT_PAGE}}],
                     send_invite_direct=[DIRECT_OK])
        self._run()
        self.assertEqual(prospect.stage, 'invited')

    def test_people_followed_although_their_profile_shows_connect_go_back_once(self):
        persona = self._persona()
        wrong = self._prospect(persona, 'dchao', 'Daniel Chao', stage='followed', profile_text=self.CONNECT_PAGE)
        right = self._prospect(persona, 'sara-khan', 'Sara Khan', stage='followed',
                               profile_text='Sara Khan\n· 3rd\nCEO\nFollow\nMessage\nMore\nAbout\nText')
        unread = self._prospect(persona, 'omar-malik', 'Omar Malik', stage='followed')
        self.env['ir.config_parameter'].sudo().search(
            [('key', '=', 'li_sales.followed_with_connect_requeued')]).unlink()
        self.assertEqual(self.env['li.prospect']._li_requeue_followed_with_connect(), 1)
        self.assertEqual((wrong.stage, right.stage, unread.stage), ('queued', 'followed', 'followed'))
        wrong.stage = 'followed'
        self.assertEqual(self.env['li.prospect']._li_requeue_followed_with_connect(), 0)   # once only

    @freeze_time(MONDAY_10_UTC)
    def test_manager_can_send_a_followed_person_back_for_another_connect_try(self):
        from odoo.exceptions import UserError
        self._start()
        persona = self._persona()
        followed = self._prospect(persona, 'ahad', 'Ahad Maaz', stage='followed',
                                  profile_text='Ahad Maaz\n· 2nd\nHead of Solutions\nFollow\nMessage\nMore\nAbout\nText')
        with self.assertRaises(UserError):
            followed.with_user(self.rep).action_try_connect_again()
        followed.with_user(self.manager).action_try_connect_again()
        self.assertEqual(followed.stage, 'queued')
        self.assertTrue(any('another try to connect' in (m.body or '') for m in followed.message_ids))
        # this time the More menu offers Connect
        self._script(connect_with_person=[self.FOLLOW_ONLY], send_invite_direct=[DIRECT_OK])
        self._run()
        self.assertEqual(followed.stage, 'invited')
        self.assertEqual(self._calls(tool='follow_person'), [])
        # and someone LinkedIn really offers no Connect for is simply followed again
        again = self._prospect(persona, 'sara-khan', 'Sara Khan', stage='followed')
        again.with_user(self.manager).action_try_connect_again()
        self.profile.last_send_at = False
        self._script(connect_with_person=[self.FOLLOW_ONLY])
        self._run()
        self.assertEqual(again.stage, 'followed')

    # ------------------------------------------------------------------
    # A slow engine
    # ------------------------------------------------------------------
    def test_engine_that_became_slow_is_restarted_by_the_watchdog(self):
        self._start()
        Action = self.env['li.engine.action']
        started = fields.Datetime.now() - timedelta(hours=5)
        self.profile.engine_started = started
        slow = lambda ms, action='inbox': Action.create({
            'linkedin_profile_id': self.profile.id, 'action': action, 'reads': 1, 'duration_ms': ms,
            'date': started + timedelta(hours=4)})
        slow(40000), slow(15000, 'acceptance'), slow(45000)
        self.assertFalse(self.profile._engine_is_slow())               # two slow inbox reads are not enough
        pid = self.profile.engine_pid
        self.env['li.profile']._cron_engine_watchdog()
        self.assertEqual(self.profile.engine_pid, pid)
        slow(61000)
        self.assertTrue(self.profile._engine_is_slow())
        self.env['li.profile']._cron_engine_watchdog()
        self.assertNotEqual(self.profile.engine_pid, pid)              # a fresh engine
        self.assertEqual(self.profile.engine_state, 'running')
        self.assertTrue(any('had become slow' in (m.body or '') for m in self.profile.message_ids))
        self.assertFalse(self.profile._engine_is_slow())               # the old reads no longer count
        self.env['li.profile']._cron_engine_watchdog()                 # and it is not restarted again

    def test_fast_reads_after_a_slow_one_do_not_restart_the_engine(self):
        self._start()
        started = fields.Datetime.now() - timedelta(hours=5)
        self.profile.engine_started = started
        for ms in (61000, 50000, 12000):
            self.env['li.engine.action'].create({
                'linkedin_profile_id': self.profile.id, 'action': 'inbox', 'reads': 1, 'duration_ms': ms,
                'date': started + timedelta(hours=4)})
        self.assertFalse(self.profile._engine_is_slow())

    @freeze_time(MONDAY_10_UTC)
    def test_engine_giving_up_at_its_time_limit_is_a_timeout_not_a_plain_failure(self):
        self._start()
        self.env['ir.config_parameter'].sudo().set_param('li_sales.engine_tool_timeout', 1)
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'sleep': 1.2, 'error': "Error calling tool 'connect_with_person'"}])
        self._run()
        action = self._actions(action='invite')
        self.assertEqual(action.status, 'timeout')
        self.assertIn('no answer within 1 seconds', action.detail)
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.result_status, item.retry_safe), ('failed', 'unknown', False))
        self.assertTrue(prospect.needs_check)                          # it may have gone out: never sent twice
        # the same words right away are an ordinary failure
        self.env['ir.config_parameter'].sudo().set_param('li_sales.engine_tool_timeout', 60)
        other = self._prospect(persona, 'sara-khan', 'Sara Khan')
        self.profile.last_send_at = False
        self._script(connect_with_person=[{'error': "Error calling tool 'connect_with_person'"}])
        self._run()
        self.assertEqual(self._actions(action='invite').sorted('id')[-1].status, 'other')
        self.assertFalse(other.needs_check)

    # ------------------------------------------------------------------
    # LinkedIn's "unusual activity" warning, minimum inbox interval
    # ------------------------------------------------------------------
    WARNING_PAGE = ('We noticed some unusual activity on your account. Over time, our systems have shown your '
                    'account has accessed a high volume of LinkedIn profile data.')

    @freeze_time(MONDAY_10_UTC)
    def test_linkedin_warning_page_pauses_the_account_for_a_day(self):
        self._start()
        persona = self._persona(run=('connection', 'chat'))
        prospect = self._prospect(persona, stage='invited', date_invited=fields.Datetime.now() - timedelta(hours=2))
        self._accepted(persona, username='sara-khan', name='Sara Khan', thread_check_needed=True)
        self._script(get_inbox=[{'data': {'sections': {'inbox': self.WARNING_PAGE}}}])
        self._run()
        self.assertEqual(self._actions(action='inbox').status, 'warning')
        self.assertEqual([c['tool'] for c in self._calls()], ['get_inbox'])     # nothing more is opened
        self.assertEqual(self.profile.bg_paused_until, fields.Datetime.now() + timedelta(hours=24))
        for agent in (persona.connection_agent_id, persona.chat_agent_id):
            self.assertEqual(agent.state, 'paused')
            self.assertIn('unusual activity', agent.pause_reason)
            self.assertEqual(agent.paused_until, fields.Datetime.now() + timedelta(hours=24))
        self.assertTrue(self.profile.activity_ids.filtered(lambda a: 'unusual activity' in (a.summary or '')))
        self.assertTrue(any('Check inbox every 30 minutes' in (m.body or '') for m in self.profile.message_ids))
        with freeze_time('2026-10-12 20:00:00'):
            self.assertEqual(self.Tools._cron_background_work(), 0)
            self.assertEqual(len(self._calls()), 1)
        with freeze_time('2026-10-13 10:01:00'):                       # a day later: by themselves again
            self.env['li.connection.agent']._resume_due()
            self.env['li.chat.agent']._resume_due()
            self.assertEqual((persona.connection_agent_id.state, persona.chat_agent_id.state), ('running', 'running'))

    @freeze_time(MONDAY_10_UTC)
    def test_warning_page_instead_of_a_send_sends_nothing_and_keeps_the_person(self):
        self._start()
        persona = self._persona()
        prospect = self._prospect(persona)
        self._script(connect_with_person=[{'data': {'status': 'unavailable', 'message': self.WARNING_PAGE}}])
        self._run()
        item = self.env['li.work.item'].search([('prospect_id', '=', prospect.id)])
        self.assertEqual((item.state, item.quota_consumed, prospect.stage, prospect.needs_check),
                         ('queued', False, 'queued', False))           # tried again after the pause
        self.assertEqual(persona.connection_agent_id.state, 'paused')

    def test_inbox_is_never_read_more_often_than_every_15_minutes(self):
        from odoo.exceptions import UserError
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('li_sales.inbox_interval', 5)
        self.assertEqual(self.Tools._inbox_interval(), 15)
        icp.set_param('li_sales.inbox_interval', 30)
        self.assertEqual(self.Tools._inbox_interval(), 30)
        settings = self.env['res.config.settings'].create({'li_inbox_interval': 5})
        with self.assertRaises(UserError):
            settings.execute()
        icp.set_param('li_sales.inbox_interval', 5)
        icp.search([('key', '=', 'li_sales.inbox_interval_min_applied')]).unlink()
        self.assertTrue(self.env['res.config.settings']._li_raise_inbox_interval())
        self.assertEqual(icp.get_param('li_sales.inbox_interval'), '15')
        icp.set_param('li_sales.inbox_interval', 5)
        self.assertFalse(self.env['res.config.settings']._li_raise_inbox_interval())     # once only

