""""Send connections / messages now" and "read replies now" from a Claude chat,
for built-in engine profiles.

li_send_now checks each persona of the profile (Connection Agent state, today's
limit, send window, queue, notes still to write) and starts the background
sender at once instead of waiting for its next turn. The sending itself stays
with the engine and with every rule of the background worker (one invite at a
time, the random delay gap, the limits). li_sending_status answers "did it
send?". Both calls take a moment: they only read Odoo and schedule the job.
"""
from datetime import datetime, time, timedelta

from odoo import _, models
from odoo.exceptions import AccessError, UserError

from .li_common import (
    NOTE_MAX_CHARS, WRITE_ORDER, format_hour, iso_utc, linkedin_username, local_now, normalize_profile_url,
    one_paragraph, safe_zone, unfilled_placeholders, utc_now,
)
from .li_mcp_tools import ToolError

SEND_ACTIONS = ('invite', 'message', 'followup', 'handoff')
SEND_NOW_SESSION = timedelta(hours=3)


class LiSendNow(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    def _engine_profile(self, linkedin_profile):
        profile = self._profile_for(linkedin_profile, required=True)
        if profile.execution_mode != 'engine':
            raise ToolError('LinkedIn profile "%s" uses Claude in Chrome: call li_get_work and send the invites in '
                            'Chrome as its items say.' % profile.account_key)
        return profile

    def _pick_personas(self, profile, persona):
        personas = profile.persona_ids
        if persona:
            wanted = str(persona).strip()
            personas = personas.filtered(lambda p: str(p.id) == wanted or wanted.lower() in (p.name or '').lower())
            if not personas:
                raise ToolError('No persona "%s" on %s. Personas: %s' % (
                    persona, profile.account_key, ', '.join(profile.persona_ids.mapped('name')) or 'none'))
        return personas

    def _blocked_profile(self, profile):
        """Why the engine cannot send for this profile now, or None."""
        if profile.connection_state != 'connected':
            return 'the LinkedIn profile is %s%s' % (profile.connection_state.replace('_', ' '), (
                ': press Reconnect LinkedIn on the profile in Odoo' if profile.connection_state != 'restricted'
                else ': LinkedIn restricted the account'))
        if profile.interface_language == 'other':
            return 'LinkedIn is not set to English: set it to English, then press Test connection'
        if not profile.engine_wanted:
            return 'the engine is stopped: press Start engine on the profile in Odoo'
        if profile.bg_paused_until and profile.bg_paused_until > utc_now():
            return 'LinkedIn asked to slow down; sending resumes at %s UTC' % iso_utc(profile.bg_paused_until)
        return None

    def _next_window(self, persona, agent):
        """The next local start of the send window on a target working day."""
        now = local_now(persona.target_timezone)
        for days in range(0, 8):
            day = (now + timedelta(days=days)).date()
            start = datetime.combine(day, time(0)).replace(tzinfo=now.tzinfo) + timedelta(hours=agent.send_window_from)
            if persona._is_working_day(start) and (days or start > now):
                return start.strftime('%a %d %b %H:%M') + ' ' + persona.target_timezone
        return False

    def _persona_send_plan(self, persona, start_agents):
        agent = persona.connection_agent_id
        row = {'persona': persona.name, 'persona_id': persona.id, 'daily_limit': agent.daily_limit,
               'agent_state': agent.state}
        if agent.state != 'running':
            if agent.paused_until and agent.paused_until > utc_now():
                row['status'] = 'paused until %s UTC (%s)' % (iso_utc(agent.paused_until), agent.pause_reason or '')
                return row
            if not start_agents:
                row['status'] = 'Connection Agent is %s: not started (ask the user, then call again with ' \
                                'start_agents true)' % agent.state
                return row
            try:
                agent.action_run()
            except (UserError, AccessError) as exc:
                row['status'] = 'could not start the Connection Agent: %s' % exc
                return row
            row['agent_state'] = 'running'
            row['started'] = True
        WorkItem = self.env['li.work.item']
        left = max(self._quota_left(persona, 'connection'), 0)
        sent_today = WorkItem._quota_used_today(persona, 'connection')
        queued = self.env['li.prospect'].search([
            ('persona_id', '=', persona.id), ('stage', '=', 'queued'), ('needs_check', '=', False),
            ('is_taken_over', '=', False), ('do_not_contact', '=', False)])
        with_text = set(WorkItem.search([('prospect_id', 'in', queued.ids), ('work_type', '=', 'invite'),
                                         ('state', 'in', ('queued', 'sending'))]).mapped('prospect_id').ids)
        if agent.send_note:
            # a note is written by Claude first, unless LinkedIn refused notes for that person
            ready = len(queued.filtered(lambda p: p.id in with_text or p.invite_without_note))
            waiting_notes = len(queued) - ready
        else:
            ready, waiting_notes = len(queued), 0
        in_window, _reason = self._window(persona, agent)
        row.update({'sent_today': sent_today, 'left_today': left, 'queued_prospects': len(queued),
                    'ready_to_send': ready, 'waiting_for_notes': waiting_notes,
                    'send_window': '%s–%s %s' % (format_hour(agent.send_window_from),
                                                 format_hour(agent.send_window_to), persona.target_timezone),
                    'in_window_now': in_window})
        if left <= 0:
            row['status'] = 'daily limit reached (%s sent today)' % sent_today
        elif not in_window:
            row['status'] = 'outside the send window; next window %s' % self._next_window(persona, agent)
        elif not queued:
            row['status'] = 'no prospects queued: Odoo searches LinkedIn first (job titles, keywords, locations), ' \
                            'then sends'
        elif not ready:
            row['status'] = 'waiting for notes: call li_get_work, write the invite_note items with li_submit_text, ' \
                            'then call li_send_now again'
        else:
            row['status'] = 'sending up to %s invite(s), one every %s–%s s (about %s min for all)%s' % (
                min(left, ready), agent.delay_min, agent.delay_max,
                max(1, round(min(left, ready) * ((agent.delay_min + agent.delay_max) / 2 + 30) / 60)),
                ' (%s more wait for notes)' % waiting_notes if waiting_notes else '')
        row['will_send'] = bool(left > 0 and in_window and (ready or not queued))
        return row

    def _messages_to_write(self, persona):
        """Prospects whose next step, follow-up or handoff is due and has no text yet
        (the same rules as the writing items of li_get_work)."""
        Prospect = self.env['li.prospect']
        busy_states = ('released', 'queued', 'sending')
        prospects = Prospect.search([
            ('persona_id', '=', persona.id), ('do_not_contact', '=', False), ('needs_check', '=', False),
            '|', ('handoff_pending', '=', True),
            '&', ('is_taken_over', '=', False), ('stage', 'in', ('accepted', 'messaged', 'replied'))], limit=300)
        busy = set(self.env['li.work.item'].search([('prospect_id', 'in', prospects.ids),
                                                    ('state', 'in', busy_states)]).mapped('prospect_id').ids)
        followup = self.env['li.followup.agent']._get()
        now = utc_now()
        count = 0
        for prospect in prospects.filtered(lambda p: p.id not in busy):
            if prospect.handoff_pending:
                count += 1
                continue
            if prospect.needs_analysis or prospect.sequence_stopped:
                continue
            step = self._next_step(prospect)
            if step and self._step_due(prospect, step, now)[0]:
                count += 1
            elif followup.state == 'running' and not self._followup_block(prospect, followup):
                count += 1
        return count

    def _message_plan(self, persona, start_agents):
        """Messages, follow-ups and handoffs of one persona: written, to write, and whether they go now."""
        agent = persona.chat_agent_id
        row = {'persona': persona.name, 'persona_id': persona.id, 'daily_limit': agent.daily_limit,
               'agent_state': agent.state}
        if agent.state != 'running':
            if agent.paused_until and agent.paused_until > utc_now():
                row['status'] = 'paused until %s UTC (%s)' % (iso_utc(agent.paused_until), agent.pause_reason or '')
                return row
            if not start_agents:
                row['status'] = 'Chat Agent is %s: not started (ask the user, then call again with start_agents ' \
                                'true)' % agent.state
                return row
            try:
                agent.action_run()
            except (UserError, AccessError) as exc:
                row['status'] = 'could not start the Chat Agent: %s' % exc
                return row
            row.update(agent_state='running', started=True)
        WorkItem = self.env['li.work.item']
        Prospect = self.env['li.prospect']
        now = utc_now()
        left = max(self._quota_left(persona, 'chat'), 0)
        ready = WorkItem.search_count([('persona_id', '=', persona.id), ('state', 'in', ('queued', 'sending')),
                                       ('work_type', 'in', ('message', 'followup', 'handoff'))])
        to_analyse = Prospect.search_count([('persona_id', '=', persona.id), ('needs_analysis', '=', True),
                                            ('is_taken_over', '=', False)])
        to_write = self._messages_to_write(persona)
        in_window, _reason = self._window(persona, agent)
        row.update({'sent_today': self.env['li.work.item']._quota_used_today(persona, 'chat'), 'left_today': left,
                    'ready_to_send': ready, 'replies_to_analyse': to_analyse, 'messages_to_write': to_write,
                    'send_window': '%s–%s %s' % (format_hour(agent.send_window_from),
                                                 format_hour(agent.send_window_to), persona.target_timezone),
                    'in_window_now': in_window})
        todo = []
        if to_analyse:
            todo.append('%s repl%s to analyse' % (to_analyse, 'y' if to_analyse == 1 else 'ies'))
        if to_write:
            todo.append('%s message(s) to write' % to_write)
        todo_text = ' (first: %s – call li_get_work, answer the items, then li_send_now again)' % \
            ', '.join(todo) if todo else ''
        if not ready:
            row['status'] = ('nothing written yet%s' % todo_text) if todo else 'no message due'
        elif left <= 0:
            row['status'] = 'daily limit reached (%s sent today); %s waiting for tomorrow' % (row['sent_today'], ready)
        elif not in_window:
            row['status'] = 'outside the send window; %s message(s) go from %s' % (
                ready, self._next_window(persona, agent))
        else:
            row['status'] = 'sending: %s message(s) now, each after a fresh read of the conversation%s' % (
                min(left, ready), todo_text)
        row['will_send'] = bool(ready and left > 0 and in_window)
        return row

    def _tool_li_send_now(self, linkedin_profile, persona=None, start_agents=False, what='all'):
        profile = self._engine_profile(linkedin_profile)
        blocked = self._blocked_profile(profile)
        if blocked:
            return {'started': False, 'linkedin_profile': profile.account_key,
                    'message': 'Nothing sent for %s: %s.' % (profile.account_key, blocked)}
        personas = self._pick_personas(profile, persona)
        if not personas:
            return {'started': False, 'linkedin_profile': profile.account_key,
                    'message': '%s has no persona yet: create one in Odoo first.' % profile.account_key}
        what = what or 'all'
        if what not in ('all', 'invites', 'messages'):
            raise ToolError('what must be all, invites or messages')
        plans = [self._persona_send_plan(p, start_agents) for p in personas] if what != 'messages' else []
        messages = [self._message_plan(p, start_agents) for p in personas] if what != 'invites' else []
        started = any(p.get('will_send') for p in plans + messages)
        if started:
            profile.sudo().send_now_until = utc_now() + SEND_NOW_SESSION
            self.env.ref('linkedin_sales_automation.cron_background_work').sudo()._trigger()
        lines = ['%s invites: %s' % (p['persona'], p['status']) for p in plans]
        lines += ['%s messages: %s' % (p['persona'], p['status']) for p in messages]
        return {
            'started': started, 'linkedin_profile': profile.account_key, 'personas': plans, 'messages': messages,
            'message': ('Odoo started sending for %s: the first one goes out within about a minute, then one at a '
                        'time with the random delay gap, so a batch takes several minutes. Fewer sent right away is '
                        'normal; check with li_sending_status after a few minutes. '
                        % profile.account_key if started else 'Nothing to send right now for %s. '
                        % profile.account_key) + ' | '.join(lines) + (
                            ' Texts still to write: ' + WRITE_ORDER if what in ('messages', 'all') else ''),
        }

    def _tool_li_invite_person(self, linkedin_url, linkedin_profile=None, persona=None, name=None, note=None):
        """Invite one person the user names, through a persona's queue and its rules."""
        username = linkedin_username(linkedin_url)
        if not username:
            raise ToolError('Give a LinkedIn profile link like https://www.linkedin.com/in/<name>/')
        Profile = self.env['li.profile']
        profiles = self._profile_for(linkedin_profile) if linkedin_profile else Profile.search([])
        if not profiles:
            raise ToolError('No LinkedIn profile in Odoo yet.')
        if len(profiles) > 1 and len(profiles.filtered('persona_ids')) == 1:
            profiles = profiles.filtered('persona_ids')          # the only profile with personas
        if len(profiles) > 1 and not persona:
            raise ToolError('Several LinkedIn profiles: say which one with linkedin_profile (%s).'
                            % ', '.join(profiles.mapped('account_key')))
        profile = profiles[:1] if not persona else (profiles.persona_ids.filtered(
            lambda p: str(p.id) == str(persona).strip() or str(persona).strip().lower() in (p.name or '').lower())
            .linkedin_profile_id[:1] or profiles[:1])
        if username == linkedin_username(profile.linkedin_url):
            return {'ok': False, 'message': '%s is the LinkedIn account of %s itself: LinkedIn does not allow '
                                            'inviting yourself.' % (username, profile.account_key)}
        personas = self._pick_personas(profile, persona)
        if len(personas) != 1:
            raise ToolError('Say which persona to use (persona): %s' % ', '.join(personas.mapped('name')))
        url = normalize_profile_url(linkedin_url)
        Prospect = self.env['li.prospect']
        if Prospect.search_count([('linkedin_username', '=', username),
                                  '|', ('do_not_contact', '=', True), ('stage', '=', 'do_not_contact')]):
            return {'ok': False, 'message': '%s is on the do-not-contact list: no invite.' % username}
        prospect = Prospect.search([('persona_id', '=', personas.id), ('linkedin_username', '=', username)], limit=1)
        if prospect and prospect.stage != 'queued':
            return {'ok': False, 'prospect_id': prospect.id,
                    'message': '%s is already a prospect of %s at stage %s: no new invite.' % (
                        prospect.name, personas.name, prospect.stage)}
        note = one_paragraph(note) if note else ''
        if note and (len(note) > NOTE_MAX_CHARS or unfilled_placeholders(note)):
            raise ToolError('The note must hold at most %s characters and no placeholders.' % NOTE_MAX_CHARS)
        if not prospect:
            prospect = Prospect.sudo().create({
                'name': (name or '').strip() or username.replace('-', ' ').title(),
                'persona_id': personas.id, 'linkedin_url': url, 'stage': 'queued'})
            prospect.message_post(body=_('Added by Claude at the user\'s request for an invite.'),
                                  author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        agent = personas.connection_agent_id
        if profile.execution_mode == 'chrome':
            return {'ok': True, 'prospect_id': prospect.id,
                    'message': '%s queued on %s. Call li_get_work for %s: the invite item comes with the rules.' % (
                        prospect.name, personas.name, profile.account_key)}
        WorkItem = self.env['li.work.item']
        open_item = WorkItem.search([('prospect_id', '=', prospect.id), ('state', 'in', ('released', 'queued',
                                                                                        'sending'))], limit=1)
        if note and not open_item:
            self._queue_send('invite', prospect, text=note, with_note=True)
        elif agent.send_note and not note and not open_item and not prospect.invite_without_note:
            return {'ok': True, 'started': False, 'prospect_id': prospect.id, 'needs_note': True,
                    'message': '%s queued; this persona sends invites with a note: call li_invite_person again '
                               'with note (at most %s characters), or li_get_work to write it.' % (
                                   prospect.name, NOTE_MAX_CHARS)}
        result = self._tool_li_send_now(profile.account_key, persona=str(personas.id), what='invites')
        result.update(ok=True, prospect_id=prospect.id,
                      message='%s queued on %s. %s' % (prospect.name, personas.name, result['message']))
        return result

    def _tool_li_check_inbox_now(self, linkedin_profile):
        """Read the LinkedIn inbox and the changed conversations now."""
        profile = self._engine_profile(linkedin_profile)
        blocked = self._blocked_profile(profile)
        if blocked:
            return {'started': False, 'message': 'Inbox not read for %s: %s.' % (profile.account_key, blocked)}
        profile.sudo().last_inbox_check = False
        self.env.ref('linkedin_sales_automation.cron_background_work').sudo()._trigger()
        return {'started': True, 'linkedin_profile': profile.account_key,
                'message': 'Odoo is reading the LinkedIn inbox of %s now (about 1–3 minutes). Then call li_get_work: '
                           'new replies come as analyse items, answers as message items; write them and call '
                           'li_send_now with what messages. %s' % (profile.account_key, WRITE_ORDER)}

    def _window_open_at(self, persona, when):
        """True when `when` (naive UTC) is inside the Connection Agent's window on a working day."""
        from .li_common import in_window, to_local
        agent = persona.connection_agent_id
        local = to_local(when, persona.target_timezone)
        return persona._is_working_day(local) and in_window(local, agent.send_window_from, agent.send_window_to)

    def _tool_li_sending_status(self, linkedin_profile, persona=None):
        profile = self._engine_profile(linkedin_profile)
        personas = self._pick_personas(profile, persona)
        WorkItem = self.env['li.work.item']
        rows = []
        for persona_rec in personas:
            tz = persona_rec.target_timezone
            day_start = datetime.combine(local_now(tz).date(), time(0), tzinfo=safe_zone(tz))
            day_start = day_start.astimezone(safe_zone('UTC')).replace(tzinfo=None)
            sent = WorkItem.search([('persona_id', '=', persona_rec.id), ('state', '=', 'done'),
                                    ('work_type', '=', 'invite'), ('date_done', '>=', day_start)],
                                   order='date_done asc')
            messages = WorkItem.search([('persona_id', '=', persona_rec.id), ('state', '=', 'done'),
                                        ('work_type', 'in', ('message', 'followup', 'handoff')),
                                        ('date_done', '>=', day_start)], order='date_done asc')
            failed = WorkItem.search([('persona_id', '=', persona_rec.id), ('state', '=', 'failed'),
                                      ('work_type', 'in', SEND_ACTIONS), ('date_done', '>=', day_start)],
                                     order='date_done asc')
            rows.append({
                'persona': persona_rec.name,
                'not_sent_today': [{'name': i.prospect_id.name, 'at': iso_utc(i.date_done), 'type': i.work_type,
                                    'status': i.result_status or 'failed',
                                    'why': (i.error or '')[:200], 'flagged_for_check': bool(i.prospect_id.needs_check)}
                                   for i in failed],
                'messages_today': [{'name': i.prospect_id.name, 'at': iso_utc(i.date_done), 'type': i.work_type,
                                    'text': (i.text_sent or '')[:160]} for i in messages],
                'invites_today': [{'name': i.prospect_id.name, 'at': iso_utc(i.date_done), 'status': i.result_status,
                                   'with_note': bool(i.text_sent)} for i in sent],
                'left_today': max(self._quota_left(persona_rec, 'connection'), 0),
                'queued_to_send': WorkItem.search_count([('persona_id', '=', persona_rec.id),
                                                         ('state', 'in', ('queued', 'sending'))]),
                'queued_prospects': self.env['li.prospect'].search_count([('persona_id', '=', persona_rec.id),
                                                                          ('stage', '=', 'queued')]),
                'agent_state': persona_rec.connection_agent_id.state,
            })
        errors = self.env['li.engine.action'].search([('linkedin_profile_id', '=', profile.id), ('state', '=', 'error'),
                                                      ('date', '>', utc_now() - timedelta(hours=2))], limit=5)
        cron = self.env.ref('linkedin_sales_automation.cron_background_work').sudo()
        total = sum(len(r['invites_today']) for r in rows)
        in_progress = not self._blocked_profile(profile) and self._bg_can_send_more(profile.sudo())
        next_send = False
        if in_progress:
            # the engine comes back when the delay gap ends; nothing goes out after the window closes
            ready = (profile.last_send_at + timedelta(seconds=profile.send_gap_seconds or 0)
                     if profile.last_send_at else utc_now())
            next_send = max(ready, utc_now())
            if not any(self._window_open_at(p, next_send) for p in personas):
                in_progress, next_send = False, False
        next_windows = sorted({w for w in (self._next_window(p, p.connection_agent_id) for p in personas
                                            if p.connection_agent_id.state == 'running') if w})
        not_sent = sum(len(r['not_sent_today']) for r in rows)
        return {
            'linkedin_profile': profile.account_key, 'engine': profile.engine_state,
            'sending_in_progress': bool(in_progress), 'next_send_around': iso_utc(next_send) if next_send else False,
            'last_successful_action': iso_utc(profile.last_success_at), 'next_background_run': iso_utc(cron.nextcall),
            'personas': rows,
            'recent_errors': [{'at': iso_utc(e.date), 'action': e.action, 'status': e.status,
                               'detail': (e.detail or '')[:200]} for e in errors],
            'message': '%s: %s invite(s) and %s message(s) sent today%s%s%s.' % (
                profile.account_key, total, sum(len(r['messages_today']) for r in rows),
                '; %s not sent (%s)' % (not_sent, '; '.join('%s: %s %s' % (f['name'], f['status'], f['why'][:80])
                                                         for r in rows for f in r['not_sent_today'])[:400])
                if not_sent else '',
                '; still sending, next one around %s UTC' % iso_utc(next_send)[11:16] if in_progress else
                '; nothing more goes out now%s' % (' (next send window %s)' % next_windows[0] if next_windows else ''),
                '; ' + '; '.join('%s: %s left, %s queued' % (
                    r['persona'], r['left_today'], r['queued_prospects']) for r in rows) if rows else ''),
        }
