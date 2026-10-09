"""Work rules behind the MCP tools (sections 6 and 11).

Two execution modes per LinkedIn profile, same rules:

* Claude in Chrome: Claude does the LinkedIn clicks. Every rule is applied when
  Claude asks for work (li_get_work), right before a send (li_confirm_send)
  and when it reports a result.
* Built-in engine: Odoo does the LinkedIn work itself in the background
  (li_background.py) through the same checks and result handling below;
  Claude only writes. The browser tools refuse engine profiles.
"""
import json
import logging
import random
import re
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

from .li_common import (
    CLOSED_STAGES, NOTE_MAX_CHARS, SEND_TYPES, WORK_TYPES, format_hour, in_window, iso_utc,
    linkedin_username, local_now, normalize_profile_url, normalize_text, safe_zone, unfilled_placeholders, utc_now,
)
from .li_engine_parse import people_search_url
from .li_mcp_tools import ToolError

_logger = logging.getLogger(__name__)

WORK_ORDER = ['check_inbox', 'analyse', 'handoff', 'message', 'followup', 'check_acceptance', 'invite',
              'publish_post', 'post_stats', 'post_draft', 'search_prospects']
# engine profiles: Odoo does the LinkedIn part itself, Claude only writes
ENGINE_WORK_ORDER = ['analyse', 'w_handoff', 'w_message', 'w_followup', 'w_invite_note', 'post_draft']
REPORT_WITH = {
    'verify_account': 'li_report_result',
    'check_inbox': 'li_record_conversation',
    'check_acceptance': 'li_mark_accepted',
    'search_prospects': 'li_add_prospects',
    'invite': 'li_report_result',
    'message': 'li_report_result',
    'followup': 'li_report_result',
    'handoff': 'li_report_result',
    'analyse': 'li_record_analysis',
    'post_draft': 'li_submit_post_draft',
    'publish_post': 'li_report_result',
    'post_stats': 'li_report_result',
}
SUCCESS_STATUSES = {'sent', 'connected', 'pending', 'invited', 'success', 'ok', 'delivered'}
ALREADY_CONNECTED = {'already_connected', 'connected_already', 'first_degree'}
NOTE_LIMIT_STATUS = 'custom_note_limit_reached'
WEEKLY_LIMIT_STATUS = 'weekly_invite_limit'
SKIP_STATUSES = {'not_found': 'LinkedIn profile not found',
                 'not_invitable': 'LinkedIn offers no Connect action for this profile (follow-only or unavailable)'}
VERIFY_STATUSES = ('verified', 'wrong_account', 'not_logged_in')
VERIFY_VALID = timedelta(hours=4)
ONE_PARAGRAPH = 'One paragraph, no line breaks.'
MESSAGE_MAX_CHARS = 8000
SEARCH_COOLDOWN = timedelta(minutes=60)
MAX_SEND_FAILURES = 3
LOCK_KEY = 74218301  # pg advisory lock serialising quota decisions

GUARDRAILS = ('Never mention prices, discounts or promises that are not in the persona/service data. '
              'Stop with anyone who says no or asks to stop.')
CHAT_METHOD = (
    'Before you write, in this order: (1) read who this person is in prospect.profile (headline, current role and '
    'company, about, experience) and decide what they actually do and what would matter to them; (2) read their '
    'last reply in the conversation and judge its nature (interested, curious, neutral, busy, sceptical, an '
    'objection, a question, not interested); (3) only then write: speak to their real role and company, answer '
    'what they said, match their tone and length, and move toward the objective of this step. Never write '
    'something that does not fit their profile (for example treating an employee or a consultant as the owner or '
    'buyer); if the step\'s question does not fit this person, reshape it to what is relevant for them while '
    'keeping the objective. If prospect.profile is empty, use the headline, title and company.')
CHAT_METHOD_CHROME = ('First open the prospect\'s LinkedIn profile (linkedin_url) and read the headline, current '
                      'role, about and experience. ' + CHAT_METHOD)
BROWSER_RULES = ('Work only in the Chrome tab of LinkedIn signed in as this profile. If LinkedIn shows a sign-in '
                 'page, call li_report_error with session_expired true; if it says the account is restricted or '
                 'asks for identity verification, call li_report_error with restricted true. Then stop working on '
                 'this profile.')
SEND_STATUS_HELP = ('status: sent (sent now), already_connected (already a 1st-degree connection), pending (an '
                    'invitation was already pending), custom_note_limit_reached (LinkedIn refuses the note: free '
                    'personalised invitations used up), weekly_invite_limit (LinkedIn says the weekly invitation '
                    'limit is reached), not_found (the profile does not exist), not_invitable (no Connect action, '
                    'also not under More), followed (no Connect, you clicked Follow instead as the item allows), '
                    'restricted (account restricted), failed (with error; retry_safe true only if you are sure nothing '
                    'was sent).')


class LiMcpEngine(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------
    def _lock(self):
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_KEY,))

    def _param(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param('li_sales.%s' % key)
        try:
            return int(value) if value not in (None, False, '') else default
        except ValueError:
            return default

    def _claim_timeout(self):
        return timedelta(minutes=max(self._param('claim_timeout', 15), 1))

    def _profile_for(self, account, required=False):
        Profile = self.env['li.profile']
        if not account:
            if required:
                raise ToolError('linkedin_profile is required')
            return Profile
        profile = Profile._find_by_account(account)
        if not profile:
            raise ToolError('Unknown LinkedIn profile "%s". Known: %s' % (
                account, ', '.join(Profile.search([]).mapped('account_key'))))
        return profile

    def _check_chrome(self, profile):
        """The browser report tools serve Claude in Chrome profiles only."""
        if profile.execution_mode != 'chrome':
            raise ToolError('LinkedIn profile "%s" uses the built-in engine: Odoo does its LinkedIn work itself. '
                            'Do not open LinkedIn for it. Nothing was recorded.' % profile.account_key)

    def _get_item(self, work_id, types=None):
        item = self.env['li.work.item'].browse(int(work_id)).exists()
        if not item:
            raise ToolError('Unknown work_id %s' % work_id)
        if types and item.work_type not in types:
            raise ToolError('Work item %s is a %s item; this tool reports %s items' % (
                work_id, item.work_type, '/'.join(types)))
        return item

    def _check_connector(self, item, account, required=False):
        self._check_chrome(item.linkedin_profile_id)
        if not account:
            if required:
                raise ToolError('linkedin_profile is required')
            return
        if not item.linkedin_profile_id._account_matches(account):
            raise ToolError('Wrong LinkedIn profile: work item %s belongs to "%s", not "%s". Nothing was '
                            'recorded.' % (item.id, item.linkedin_profile_id.account_key, account),
                            {'expected_linkedin_profile': item.linkedin_profile_id.account_key})

    def _agent_of(self, item_or_type, persona=None):
        if isinstance(item_or_type, str):
            agent_type, persona = item_or_type, persona or self.env['li.persona']
        else:
            agent_type = item_or_type.agent_type
            persona = persona if persona is not None else item_or_type.persona_id
        if agent_type == 'connection':
            return persona.connection_agent_id
        if agent_type == 'chat':
            return persona.chat_agent_id
        if agent_type == 'followup':
            return self.env['li.followup.agent']._get()
        return self.env['li.activity.agent']._get()

    def _window(self, persona, agent):
        """(ok, reason) for the persona's target working day and the agent's send
        window, both read in the persona's target time zone."""
        now = local_now(persona.target_timezone)
        if not persona._is_working_day(now):
            return False, '%s: not a target working day (%s, %s)' % (
                persona.name, now.strftime('%A %H:%M'), persona.target_timezone)
        if not in_window(now, agent.send_window_from, agent.send_window_to):
            return False, '%s: outside the %s send window %s–%s (local time %s, %s)' % (
                persona.name, agent._agent_label, format_hour(agent.send_window_from),
                format_hour(agent.send_window_to), now.strftime('%H:%M'), persona.target_timezone)
        return True, ''

    def _quota_left(self, persona, agent_type, exclude=None):
        WorkItem = self.env['li.work.item'].sudo()
        if agent_type == 'followup':
            agent = self._agent_of('followup')
            return agent.daily_limit - WorkItem._followup_used(exclude=exclude)
        agent = self._agent_of(agent_type, persona)
        left = agent.daily_limit - WorkItem._quota_used_today(persona, agent_type, exclude=exclude)
        if agent_type == 'connection' and agent.weekly_limit:
            left = min(left, agent.weekly_limit - WorkItem._quota_used_week(persona, agent_type, exclude=exclude))
        return left

    def _notify_limit(self, persona, agent):
        """Post "daily limit reached" once per local day."""
        today = local_now(persona.target_timezone).date()
        if agent.limit_notice_date == today:
            return
        agent.sudo().limit_notice_date = today
        line = _('%(agent)s reached its daily limit (%(limit)s) — resumes next working day',
                 agent=agent._agent_label, limit=agent.daily_limit)
        persona.sudo().message_post(body=line, author_id=self.env['li.event']._ai_partner().id,
                                    subtype_xmlid='mail.mt_note')

    def _open_send_count(self, profile):
        return self.env['li.work.item'].search_count([
            ('linkedin_profile_id', '=', profile.id), ('state', '=', 'released'),
            ('work_type', 'in', SEND_TYPES), ('confirmed', '=', False)])

    def _has_open(self, domain):
        return bool(self.env['li.work.item'].search_count(domain + [('state', '=', 'released')]))

    def _create_item(self, work_type, agent_type, profile, persona=None, prospect=None, quota=False,
                     payload=None, **vals):
        now = utc_now()
        values = {
            'work_type': work_type,
            'agent_type': agent_type,
            'linkedin_profile_id': profile.id,
            'persona_id': persona.id if persona else False,
            'prospect_id': prospect.id if prospect else False,
            'date_released': now,
            'expires_at': now + self._claim_timeout(),
            'quota_consumed': quota,
            'quota_date': local_now(persona.target_timezone).date() if (quota and persona) else False,
        }
        values.update(vals)
        item = self.env['li.work.item'].create(values)
        if persona and agent_type in ('connection', 'chat'):
            self._agent_of(agent_type, persona).sudo().last_run = now
        data = {
            'work_id': item.id,
            'type': work_type,
            'linkedin_profile': profile.account_key,
            'linkedin_profile_name': profile.name,
            'report_with': REPORT_WITH[work_type],
            'expires_at': iso_utc(item.expires_at),
        }
        if persona:
            data['persona'] = persona._prompt_payload()
        if prospect:
            data['prospect'] = prospect._payload()
        data.update(payload or {})
        item.payload = json.dumps(data, ensure_ascii=False, default=str)
        return data

    # ------------------------------------------------------------------
    # li_get_work
    # ------------------------------------------------------------------
    def _tool_li_get_work(self, linkedin_profile, max_items=None):
        self._lock()
        self.env['li.work.item'].sudo()._cron_expire_claims()
        profile = self._profile_for(linkedin_profile, required=True)
        limit = min(int(max_items or self._param('max_items_per_run', 20)), 25)
        ctx = {'left': limit, 'reasons': [],
               'sends': {profile.id: max(self._param('max_sends_per_account', 5) - self._open_send_count(profile), 0)}}
        items = []
        if profile.execution_mode == 'chrome' and not profile._chrome_verified():
            items = [self._verify_item(profile)]
            ctx['left'] = 0
        elif profile.connection_state != 'connected':
            ctx['reasons'].append('%s: LinkedIn profile is %s' % (profile.name, profile.connection_state))
        order = WORK_ORDER if profile.execution_mode == 'chrome' else ENGINE_WORK_ORDER
        for work_type in order if profile.connection_state == 'connected' else ():
            if ctx['left'] <= 0:
                break
            for data in getattr(self, '_gen_%s' % work_type)(profile, ctx):
                items.append(data)
                ctx['left'] -= 1
                if work_type in SEND_TYPES:
                    ctx['sends'][profile.id] -= 1
                if ctx['left'] <= 0:
                    break
        result = {'items': items, 'count': len(items), 'linkedin_profile': profile.account_key,
                  'execution_mode': profile.execution_mode}
        if profile.execution_mode == 'engine':
            result['note'] = ('Odoo does the LinkedIn work of %s itself (built-in engine): search, inbox, '
                              'acceptance checks, sending and publishing. Do not open LinkedIn for it: only write '
                              '(li_submit_text, li_record_analysis, li_submit_post_draft).' % profile.account_key)
        if not items:
            reasons = list(dict.fromkeys(ctx['reasons']))[:12]
            if profile.execution_mode == 'engine' and profile.connection_state == 'connected':
                result['message'] = (
                    'Nothing to write for %s right now: no reply to analyse, no message, follow-up or handoff due, '
                    'no invite waiting for a note and no post idea. This is normal: Odoo keeps searching, sending '
                    'invites without notes and reading the inbox by itself; writing items appear once people accept '
                    'or reply. Call li_finish_run.' % profile.account_key)
            else:
                result['message'] = 'No work allowed right now for %s. Call li_finish_run.' % profile.account_key + (
                    ' Reasons: ' + '; '.join(reasons) if reasons else '')
            result['reasons'] = reasons
        return result

    # -- verify_account (Claude in Chrome) ----------------------------------
    def _verify_item(self, profile):
        return self._create_item('verify_account', 'system', profile, payload={
            'expected_linkedin_url': profile.linkedin_url,
            'instructions': 'Before any other LinkedIn work on this profile: in Chrome open '
                            'https://www.linkedin.com/in/me/ and wait for it to load. If LinkedIn shows a sign-in '
                            'page, do not sign in: call li_report_result with status not_logged_in. Otherwise call '
                            'li_report_result with status verified and linkedin_url = the profile address the page '
                            'landed on (linkedin.com/in/<username>/). Then call li_get_work again.',
        })

    def _verify_result(self, item, status, linkedin_url):
        profile = item.linkedin_profile_id.sudo()
        if status == 'not_logged_in':
            item._close('done', result_status=status)
            if profile.connection_state == 'connected':
                profile._set_reconnect_needed(_('Chrome is not signed in to LinkedIn'))
            return {'ok': False, 'message': 'Chrome is not signed in to LinkedIn. Ask the user to sign in as %s '
                                            '(%s), then start again. Do no work on this profile.' % (
                                                profile.name, profile.linkedin_url)}
        found = linkedin_username(linkedin_url)
        if status == 'wrong_account' or not found or found != linkedin_username(profile.linkedin_url):
            item._close('done', result_status='wrong_account', error=linkedin_url or False)
            profile.message_post(body=_('Claude in Chrome is signed in to %(found)s, not to this profile — '
                                        'nothing was done.', found=linkedin_url or _('another account')))
            return {'ok': False, 'message': 'Chrome is signed in to %s, not to %s (%s). Do no work on this '
                                            'profile; ask the user to sign in to the right account.' % (
                                                linkedin_url or 'another account', profile.name,
                                                profile.linkedin_url)}
        item._close('done', result_status='verified')
        vals = {'chrome_verified_at': utc_now()}
        if profile.connection_state != 'connected':
            vals['connection_state'] = 'connected'
            profile.message_post(body=_('Account checked in Claude in Chrome — Connected. Agents paused '
                                        'earlier stay paused until someone runs them.'))
        profile.write(vals)
        return {'ok': True, 'message': 'Account %s verified. Call li_get_work again.' % profile.account_key}

    # -- check_acceptance (6.1.6) ---------------------------------------
    def _gen_check_acceptance(self, profile, ctx):
        WorkItem = self.env['li.work.item']
        hours = self._param('acceptance_interval', 6)
        recent = WorkItem.search_count([
            ('linkedin_profile_id', '=', profile.id), ('work_type', '=', 'check_acceptance'),
            '|', ('state', '=', 'released'),
            '&', ('state', '=', 'done'), ('date_done', '>', utc_now() - timedelta(hours=hours))])
        if recent:
            return []
        pending = self.env['li.prospect'].search([
            ('linkedin_profile_id', '=', profile.id), ('stage', '=', 'invited'),
            '|', ('persona_id.connection_agent_id.state', '!=', 'stopped'),
            ('persona_id.chat_agent_id.state', '=', 'running'),
        ], order='date_invited asc', limit=50)
        if not pending:
            return []
        data = self._create_item('check_acceptance', 'connection', profile, prospect_ids=[(6, 0, pending.ids)],
                                 payload={
                                     'pending_invites': [p._payload() for p in pending],
                                     'instructions': 'For each pending invite, open its linkedin_url in Chrome '
                                                     'and look at the profile: it is accepted when LinkedIn shows '
                                                     '"1st" next to the name and Message as the main button '
                                                     '(Pending means not yet). Then call li_mark_accepted with '
                                                     'the ids of those who accepted (an empty list is fine). '
                                                     'Read-only: click nothing. ' + BROWSER_RULES,
                                 })
        return [data]

    # -- invite (6.1.1–6.1.5) --------------------------------------------
    def _connection_personas(self, profile, ctx):
        """Running Connection Agents of the profile that may send now."""
        result = []
        WorkItem = self.env['li.work.item'].sudo()
        for persona in profile.persona_ids.filtered(lambda p: p.connection_agent_id.state == 'running'):
            agent = persona.connection_agent_id
            ok, reason = self._window(persona, agent)
            if not ok:
                ctx['reasons'].append(reason)
                continue
            if agent.total_target:
                sent = WorkItem._total_invites(persona)
                if sent >= agent.total_target:
                    agent.sudo().action_stop()
                    ctx['reasons'].append('%s: total target of %s invites reached, agent stopped' % (
                        persona.name, agent.total_target))
                    continue
            left = self._quota_left(persona, 'connection')
            if agent.total_target:
                open_invites = WorkItem.search_count([('persona_id', '=', persona.id), ('work_type', '=', 'invite'),
                                                      ('state', '=', 'released')])
                left = min(left, agent.total_target - WorkItem._total_invites(persona) - open_invites)
            if left <= 0:
                self._notify_limit(persona, agent)
                ctx['reasons'].append('%s: Connection Agent daily limit (%s) reached' % (persona.name, agent.daily_limit))
                continue
            result.append((persona, agent, left))
        return result

    def _gen_invite(self, profile, ctx):
        items = []
        for persona, agent, left in self._connection_personas(profile, ctx):
            if ctx['sends'][profile.id] - len(items) <= 0 or ctx['left'] - len(items) <= 0:
                break
            queued = self.env['li.prospect'].search([
                ('persona_id', '=', persona.id), ('stage', '=', 'queued'), ('needs_check', '=', False),
                ('is_taken_over', '=', False), ('do_not_contact', '=', False),
            ], order='create_date asc, id asc', limit=50)
            busy = set(self.env['li.work.item'].search([('prospect_id', 'in', queued.ids),
                                                        ('state', '=', 'released')]).mapped('prospect_id').ids)
            for prospect in queued:
                if left <= 0 or ctx['sends'][profile.id] - len(items) <= 0 or ctx['left'] - len(items) <= 0:
                    break
                if prospect.id in busy or self._is_do_not_contact(prospect):
                    continue
                with_note = agent.send_note and not prospect.invite_without_note
                if with_note:
                    instructions = ('Write a personalised connection note of at most %s characters, one paragraph. '
                                    '%s %s Call li_confirm_send with work_id and the exact note as text. Only if go '
                                    'is true: open the prospect linkedin_url in Chrome, click Connect (or More > '
                                    'Connect), Add a note, type exactly that text, Send. Then li_report_result with '
                                    'text_sent and note_sent true. %s %s' % (
                                        NOTE_MAX_CHARS, agent.note_instructions or '', GUARDRAILS, SEND_STATUS_HELP,
                                        BROWSER_RULES))
                else:
                    instructions = ('Send the connection request without a note. Call li_confirm_send with work_id '
                                    '(no text). Only if go is true: open the prospect linkedin_url in Chrome, click '
                                    'Connect (or More > Connect), Send without a note. Then li_report_result. %s %s'
                                    % (SEND_STATUS_HELP, BROWSER_RULES))
                if agent.follow_if_no_connect:
                    instructions += (' If the profile has no Connect action (also not under More) but offers Follow, '
                                     'click Follow and report status followed.')
                items.append(self._create_item(
                    'invite', 'connection', profile, persona, prospect, quota=True, with_note=with_note,
                    payload={'send_note': with_note, 'note_max_chars': NOTE_MAX_CHARS if with_note else 0,
                             'instructions': instructions, 'conversation': []}))
                left -= 1
        return items

    def _is_do_not_contact(self, prospect):
        username = prospect.linkedin_username
        if not username:
            return False
        return bool(self.env['li.prospect'].search_count([('linkedin_username', '=', username),
                                                          ('do_not_contact', '=', True)]))

    # -- search_prospects (6.1.2) ------------------------------------------
    def _gen_search_prospects(self, profile, ctx):
        items = []
        Prospect = self.env['li.prospect']
        for persona, agent, left in self._connection_personas(profile, ctx):
            if ctx['left'] - len(items) <= 0:
                break
            queued = Prospect.search_count([('persona_id', '=', persona.id), ('stage', '=', 'queued'),
                                            ('needs_check', '=', False)])
            if queued >= left:
                continue  # the queue covers what may still be sent today
            if self._has_open([('persona_id', '=', persona.id), ('work_type', '=', 'search_prospects')]):
                continue
            if agent.last_search_date and utc_now() - agent.last_search_date < SEARCH_COOLDOWN:
                continue
            titles = [t.strip() for t in (persona.job_titles or '').replace('\n', ',').split(',') if t.strip()]
            locations = persona.location_ids.mapped('name')
            # search_people takes keywords + one location and has no paging: every
            # search uses the next job title x location combination instead
            combos = [(t, l) for l in (locations or ['']) for t in (titles or [''])]
            title, location = combos[agent.search_page % len(combos)]
            keywords = ' '.join(filter(None, [title, persona.include_keywords]))
            search_url = persona.search_url or ''
            note = ''
            if 'linkedin.com/sales' in search_url:
                note = ' Sales Navigator searches are not used: use the people search above.'
                search_url = ''
            items.append(self._create_item('search_prospects', 'connection', profile, persona, payload={
                'keywords': keywords,
                'location': location,
                'job_titles': titles,
                'locations': locations,
                'industries': persona.industry_ids.mapped('name'),
                'seniority': persona.seniority_ids.mapped('name'),
                'company_size': persona.company_size_ids.mapped('name'),
                'exclude_keywords': persona.exclude_keywords or '',
                'search_url': search_url,
                'search_number': agent.search_page + 1,
                'wanted': max(left * 2, 10),
                'people_search_url': people_search_url(keywords),
                'instructions': 'In Chrome open people_search_url (LinkedIn people search for "%s")%s. Read the '
                                'first page of results. Keep only people who fit the persona (ideal customer, '
                                'industries, seniority) and return them with li_add_prospects (name, headline, '
                                'location, linkedin_url). Odoo removes duplicates and people who must not be '
                                'contacted. Read-only: click no Connect or Message button.%s %s' % (
                                    keywords, ', then set the Locations filter to "%s"' % location if location else '',
                                    note, BROWSER_RULES),
            }))
            agent.sudo().last_search_date = utc_now()
        return items

    # ------------------------------------------------------------------
    # li_confirm_send
    # ------------------------------------------------------------------
    def _stop(self, item, reason, cancel=True, **extra):
        if cancel and item.state == 'released':
            item._close('cancelled', cancel_reason=reason)
        return dict({'go': False, 'reason': reason, 'work_id': item.id}, **extra)

    def _validate_text(self, item, text):
        """Return an error string, or None when the text may be sent."""
        needs_text = item.work_type in ('message', 'followup', 'handoff') or (
            item.work_type == 'invite' and item.with_note)
        text = (text or '').strip()
        if needs_text and not text:
            return 'text is required: pass the exact %s you will send' % (
                'note' if item.work_type == 'invite' else 'message')
        if item.work_type == 'invite' and not item.with_note and text:
            return 'this invite must be sent without a note: call li_confirm_send without text'
        if not text:
            return None
        if item.work_type == 'invite' and len(text) > NOTE_MAX_CHARS:
            return 'the note has %s characters; the maximum is %s' % (len(text), NOTE_MAX_CHARS)
        if len(text) > MESSAGE_MAX_CHARS:
            return 'the message has %s characters; the maximum is %s' % (len(text), MESSAGE_MAX_CHARS)
        placeholders = unfilled_placeholders(text)
        if placeholders:
            return 'fill the placeholders before sending: %s' % ', '.join('{%s}' % p for p in placeholders)
        return None

    def _send_verdict(self, item, text, dry=False):
        """Every rule checked right before a send, for both modes.

        Returns (verdict, reason, wait_seconds):
        * go      – send now (the delay gap is reserved, the item confirmed)
        * wait    – the delay gap of the account is not over (wait_seconds)
        * hold    – not now (send window, working day, daily limit, agent paused, account not connected);
                    a queued text stays queued
        * stop    – never: the prospect or the step changed; the item is cancelled
        * invalid – the text breaks a rule
        dry: only check, reserve nothing.
        """
        profile, persona = item.linkedin_profile_id, item.persona_id
        if profile.connection_state != 'connected':
            return 'hold', 'LinkedIn profile %s is %s' % (profile.name, profile.connection_state), 0
        reason = self._prospect_block_reason(item)
        if reason:
            return 'stop', reason, 0
        agent = self._agent_of(item)
        if agent.state == 'stopped':
            return 'stop', '%s is stopped' % agent._agent_label, 0
        if agent.state != 'running':
            return 'hold', '%s is %s' % (agent._agent_label, agent.state), 0
        ok, reason = self._window(persona, agent)
        if not ok:
            return 'hold', reason, 0
        if self._quota_left(persona, item.agent_type, exclude=item) <= 0:
            return 'hold', 'daily limit reached', 0
        error = self._validate_text(item, text)
        if error:
            return 'invalid', 'invalid text: %s' % error, 0
        now = utc_now()
        if profile.last_send_at:
            ready_at = profile.last_send_at + timedelta(seconds=profile.send_gap_seconds or 0)
            if now < ready_at:
                return 'wait', 'wait', int((ready_at - now).total_seconds()) + 1
        if dry:
            return 'go', '', 0
        con = persona.connection_agent_id
        gap = random.randint(min(con.delay_min, con.delay_max), max(con.delay_min, con.delay_max))
        profile.sudo().write({'last_send_at': now, 'send_gap_seconds': gap})
        item.write({'confirmed': True, 'date_confirmed': now, 'text_confirmed': (text or '').strip() or False,
                    'expires_at': now + self._claim_timeout(),
                    'quota_date': local_now(persona.target_timezone).date()})
        return 'go', '', 0

    def _tool_li_confirm_send(self, work_id, text=None):
        self._lock()
        item = self._get_item(work_id)
        self._check_chrome(item.linkedin_profile_id)
        if item.work_type not in SEND_TYPES:
            raise ToolError('Work item %s is a %s item: nothing to send' % (item.id, item.work_type))
        if item.state != 'released':
            reason = item.cancel_reason or {'expired': 'the claim expired', 'done': 'already reported',
                                            'failed': 'already reported as failed'}.get(item.state, item.state)
            return self._stop(item, reason, cancel=False)
        if item.confirmed:
            return self._stop(item, 'already confirmed: send once, then report with li_report_result', cancel=False)
        verdict, reason, wait = self._send_verdict(item, text)
        if verdict == 'invalid':
            # keep the claim: Claude can fix the text and confirm again
            return {'go': False, 'reason': reason, 'work_id': item.id}
        if verdict == 'wait':
            now = utc_now()
            item.expires_at = max(item.expires_at, now + timedelta(seconds=wait) + self._claim_timeout())
            return {'go': False, 'reason': 'wait', 'wait_seconds': wait, 'work_id': item.id,
                    'message': 'Delay gap on %s: do other items first, then call li_confirm_send again '
                               'in %s seconds.' % (item.linkedin_profile_id.account_key, wait)}
        if verdict != 'go':
            return self._stop(item, reason)
        return {'go': True, 'work_id': item.id,
                'message': 'Send now in Chrome as %s, then call li_report_result.' % item.linkedin_profile_id.account_key}

    def _prospect_block_reason(self, item):
        prospect = item.prospect_id
        if not prospect:
            return 'the prospect no longer exists'
        if prospect.do_not_contact or self._is_do_not_contact(prospect):
            return 'prospect is on the do-not-contact list'
        if prospect.needs_check:
            return 'prospect is flagged for a person to check'
        if item.work_type == 'handoff':
            # the pivot itself takes the prospect over; a later manual takeover cancels the handoff
            if prospect.takeover_reason not in ('pivot', False) or not prospect.handoff_pending:
                return 'handoff no longer pending'
            return None
        if prospect.is_taken_over:
            return 'prospect taken over'
        if item.work_type == 'invite':
            if prospect.stage != 'queued':
                return 'prospect is no longer queued (stage %s)' % prospect.stage
            return None
        if prospect.stage in CLOSED_STAGES or prospect.stage in ('warm', 'meeting'):
            return 'prospect stage is %s' % prospect.stage
        return self._send_specific_block(item)

    def _send_specific_block(self, item):
        """Hook for message / follow-up specific checks (phases 3 and 4)."""
        return None

    # ------------------------------------------------------------------
    # li_report_result
    # ------------------------------------------------------------------
    def _tool_li_report_result(self, work_id, status, linkedin_profile, text_sent=None, note_sent=None,
                               retry_safe=None, error=None, linkedin_url=None):
        self._lock()
        item = self._get_item(work_id, SEND_TYPES + ('verify_account',))
        self._check_connector(item, linkedin_profile, required=True)
        status = (status or '').strip().lower()
        if item.work_type == 'verify_account':
            if item.state != 'released':
                raise ToolError('Work item %s is %s' % (item.id, item.state))
            if status not in VERIFY_STATUSES:
                raise ToolError('status must be one of %s for a verify_account item' % ', '.join(VERIFY_STATUSES))
            return self._verify_result(item, status, linkedin_url)
        if item.state in ('done', 'failed'):
            raise ToolError('Work item %s was already reported (%s)' % (item.id, item.state))
        if item.state in ('expired', 'cancelled') and not item.confirmed:
            raise ToolError('Work item %s is %s (%s) and was never confirmed: it must not have been sent. '
                            'Nothing recorded.' % (item.id, item.state, item.cancel_reason or 'claim expired'))
        if status == 'restricted':
            item._close('failed', result_status=status, quota_consumed=False, error=error or status)
            item.linkedin_profile_id.sudo()._set_restricted(error or _('reported by Claude in Chrome'))
            return {'ok': True, 'work_id': item.id, 'message': 'Profile %s marked Restricted and paused. Stop '
                    'working on it.' % item.linkedin_profile_id.account_key}
        return self._apply_send_result(item, status, text_sent, note_sent, retry_safe, error)

    def _apply_send_result(self, item, status, text_sent=None, note_sent=None, retry_safe=None, error=None):
        """Record the outcome of a send (invite, message, follow-up, handoff),
        reported by Claude in Chrome or by the background sender."""
        text = (text_sent or '').strip() or item.text_confirmed or ''
        if status in SUCCESS_STATUSES:
            if item.work_type == 'invite' and (note_sent or item.with_note) and text and len(text) > NOTE_MAX_CHARS:
                raise ToolError('The note has %s characters; the maximum is %s.' % (len(text), NOTE_MAX_CHARS))
            if item.work_type != 'invite' and not text:
                raise ToolError('text_sent is required for a sent %s' % item.work_type)
            if text and unfilled_placeholders(text):
                raise ToolError('text_sent still contains placeholders: %s' % ', '.join(unfilled_placeholders(text)))
            warning = '' if item.confirmed else ' Warning: this send was not confirmed with li_confirm_send first.'
            already_pending = item.work_type == 'invite' and status == 'pending'
            item._close('done', result_status=status, text_sent=text or False, quota_consumed=not already_pending,
                        retry_safe=bool(retry_safe))
            item.prospect_id.sudo().send_attempts = 0
            self._agent_of(item)._register_success()
            if already_pending:
                text, note_sent = '', False
            message = getattr(self, '_apply_sent_%s' % item.work_type)(item, text, bool(note_sent))
            if already_pending:
                message = '%s already had a pending invitation: stage Invited.' % item.prospect_id.name
            return {'ok': True, 'work_id': item.id, 'message': message + warning}
        if item.work_type == 'invite' and status in ALREADY_CONNECTED:
            item._close('done', result_status=status, quota_consumed=False)
            self._accept(item.prospect_id, note=_('already a 1st-degree connection'))
            return {'ok': True, 'work_id': item.id, 'message': '%s is already connected: marked accepted.'
                    % item.prospect_id.name}
        if item.work_type == 'invite' and status == NOTE_LIMIT_STATUS:
            item._close('failed', result_status=status, quota_consumed=False, error=error or status)
            prospect = item.prospect_id.sudo()
            prospect.invite_without_note = True
            line = _('LinkedIn refused the invite note to %s (custom note limit reached) — the invite will be '
                     'sent again without a note', prospect.name)
            for record in (prospect, item.persona_id.sudo()):
                record.message_post(body=line, author_id=self.env['li.event']._ai_partner().id,
                                    subtype_xmlid='mail.mt_note')
            return {'ok': True, 'work_id': item.id, 'message': 'Noted: the invite will come back without a note.'}
        if item.work_type == 'invite' and status == WEEKLY_LIMIT_STATUS:
            item._close('failed', result_status=status, quota_consumed=False, error=error or status)
            paused = self._weekly_limit_reached(item.linkedin_profile_id, error)
            return {'ok': True, 'work_id': item.id,
                    'message': 'Weekly invitation limit of %s: %s Connection Agent(s) paused until next week. '
                               'Send no more invites from this profile.' % (item.linkedin_profile_id.account_key,
                                                                             len(paused))}
        if item.work_type == 'invite' and status in ('followed', 'already_following'):
            item._close('done', result_status=status, quota_consumed=False)
            self._mark_followed(item.prospect_id)
            return {'ok': True, 'work_id': item.id,
                    'message': '%s has no Connect action: followed instead (no invite counted).' % item.prospect_id.name}
        if status in SKIP_STATUSES:
            item._close('failed', result_status=status, quota_consumed=False, retry_safe=True,
                        error=error or SKIP_STATUSES[status])
            item.prospect_id._flag_check(_('%(why)s — skipped. %(detail)s', why=SKIP_STATUSES[status],
                                           detail=error or ''))
            return {'ok': True, 'work_id': item.id,
                    'message': '%s: %s — flagged for a person to check.' % (item.prospect_id.name,
                                                                          SKIP_STATUSES[status])}
        if status == 'unknown':
            retry_safe = False
        return self._send_failed(item, status or 'failed', retry_safe, error)

    def _mark_followed(self, prospect):
        """LinkedIn offered no Connect for this person and we follow them instead."""
        prospect = prospect.sudo()
        prospect.write({'stage': 'followed', 'send_attempts': 0})
        line = _('%s offers no Connect action on LinkedIn — followed instead', prospect.name)
        self.env['li.event']._log('followed', 'connection', persona=prospect.persona_id, prospect=prospect,
                                  detail=line, persona_body=line, prospect_body=line)
        return True

    def _weekly_limit_reached(self, profile, detail=None):
        """LinkedIn's weekly invitation limit counts per LinkedIn account: pause
        every Connection Agent of the profile until next Monday 00:00 in each
        persona's target time zone."""
        paused = self.env['li.connection.agent']
        for persona in profile.persona_ids:
            agent = persona.connection_agent_id
            if agent.state != 'running':
                continue
            now = local_now(persona.target_timezone)
            monday = (now + timedelta(days=7 - now.weekday())).date()
            until = datetime.combine(monday, time(0, 0), tzinfo=safe_zone(persona.target_timezone))
            until = until.astimezone(safe_zone('UTC')).replace(tzinfo=None)
            paused |= agent.sudo()._pause_until(until, _('LinkedIn weekly invitation limit reached on %s — runs '
                                                         'again next week', profile.name))
        profile.sudo().message_post(body=_('LinkedIn weekly invitation limit reached — Connection Agents paused '
                                           'until next week. %s', detail or ''))
        for agent in paused:
            self.env['li.event']._log('error', 'connection', persona=agent.persona_id,
                                      detail=_('Weekly invitation limit reached on %s', profile.name))
        return paused

    def _send_failed(self, item, status, retry_safe, error):
        if retry_safe is None:
            # an unconfirmed item cannot have been sent; a confirmed one has an unknown outcome
            retry_safe = not item.confirmed
        prospect = item.prospect_id.sudo()
        detail = error or status
        agent = self._agent_of(item)
        if retry_safe:
            item._close('failed', result_status=status, error=detail, quota_consumed=False, retry_safe=True)
            prospect.send_attempts += 1
            line = _('%(type)s to %(name)s failed — retrying (%(detail)s)',
                     type=dict(WORK_TYPES)[item.work_type], name=prospect.name, detail=detail)
            if prospect.send_attempts >= MAX_SEND_FAILURES:
                prospect._flag_check(_('%s failed %s times in a row: %s', dict(WORK_TYPES)[item.work_type],
                                       prospect.send_attempts, detail))
                line = _('%(type)s to %(name)s failed %(n)s times — flagged for a person to check',
                         type=dict(WORK_TYPES)[item.work_type], name=prospect.name, n=prospect.send_attempts)
        else:
            item._close('failed', result_status=status, error=detail, quota_consumed=True, retry_safe=False)
            prospect._flag_check(_('Send result unknown (retry_safe false): %s. Check LinkedIn before any new send.',
                                   detail))
            line = _('%(type)s to %(name)s has an unknown outcome — never retried, flagged for a person to check',
                     type=dict(WORK_TYPES)[item.work_type], name=prospect.name)
        self.env['li.event']._log('error', item.agent_type, persona=item.persona_id, prospect=prospect,
                                  detail='%s (%s)' % (line, detail), persona_body=line, prospect_body=line)
        agent._register_error(detail)
        return {'ok': True, 'work_id': item.id, 'retry_safe': bool(retry_safe),
                'message': 'Failure recorded.' + ('' if retry_safe else ' Do not retry this send.')}

    def _apply_sent_invite(self, item, text, note_sent):
        prospect = item.prospect_id.sudo()
        now = utc_now()
        prospect.write({'stage': 'invited', 'date_invited': now, 'invite_without_note': False})
        note = text if (note_sent or item.with_note) and text else ''
        if note:
            self.env['li.message'].sudo().create({
                'prospect_id': prospect.id, 'direction': 'out', 'kind': 'note', 'body': note,
                'ai_generated': True, 'date': now, 'state': 'sent', 'work_item_id': item.id})
        who = prospect.name + (' (%s)' % prospect.headline if prospect.headline else '')
        line = _('Connection request sent to %s', who) + (_(' — note: %s', note) if note else '')
        self.env['li.event']._log('invite_sent', 'connection', persona=item.persona_id, prospect=prospect,
                                  detail=note or line, persona_body=line, prospect_body=line)
        agent = item.persona_id.connection_agent_id
        if agent.total_target and self.env['li.work.item'].sudo()._total_invites(item.persona_id) >= agent.total_target:
            agent.sudo().action_stop()
        return 'Invite to %s recorded (stage Invited).' % prospect.name

    # ------------------------------------------------------------------
    # li_add_prospects
    # ------------------------------------------------------------------
    def _tool_li_add_prospects(self, work_id, people, linkedin_profile=None):
        self._lock()
        item = self._get_item(work_id, ['search_prospects'])
        self._check_connector(item, linkedin_profile)
        if item.state != 'released':
            raise ToolError('Work item %s is %s' % (item.id, item.state))
        counts = self._add_people(item.persona_id, people)
        item._close('done', result_status='ok')
        return counts

    def _add_people(self, persona, people):
        """Queue the people found by a search for the persona (duplicates,
        do-not-contact, excluded keywords and people contacted by another
        persona are skipped). Returns the counts."""
        agent = persona.connection_agent_id
        Prospect = self.env['li.prospect']
        excluded = [normalize_text(k) for k in (persona.exclude_keywords or '').replace(';', ',').split(',') if k.strip()]
        counts = {'created': 0, 'duplicates': 0, 'contacted_elsewhere': 0, 'do_not_contact': 0, 'excluded': 0,
                  'invalid': 0}
        seen = set()
        for person in people:
            username = linkedin_username(person.get('linkedin_url')) or linkedin_username(person.get('username'))
            if not username or not (person.get('name') or '').strip():
                counts['invalid'] += 1
                continue
            if username in seen:
                counts['duplicates'] += 1
                continue
            seen.add(username)
            text = normalize_text(' '.join(filter(None, [person.get('headline'), person.get('title'),
                                                         person.get('company')])))
            if any(k and k in text for k in excluded):
                counts['excluded'] += 1
                continue
            others = Prospect.search([('linkedin_username', '=', username)])
            if others.filtered('do_not_contact'):
                counts['do_not_contact'] += 1
                continue
            if others.filtered(lambda p: p.persona_id == persona):
                counts['duplicates'] += 1
                continue
            if others and agent.skip_if_contacted:
                counts['contacted_elsewhere'] += 1
                continue
            Prospect.create({
                'name': person['name'].strip(),
                'headline': person.get('headline') or False,
                'title': person.get('title') or False,
                'company': person.get('company') or False,
                'location': person.get('location') or False,
                'linkedin_url': normalize_profile_url(person.get('linkedin_url'), username),
                'persona_id': persona.id,
                'stage': 'queued',
            })
            counts['created'] += 1
        agent.sudo().write({'search_page': agent.search_page + 1})
        if counts['created']:
            persona.sudo().message_post(
                body=_('%(n)s new prospects queued from a LinkedIn search', n=counts['created']),
                author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        counts['message'] = '%(created)s queued, %(duplicates)s duplicates, %(contacted_elsewhere)s already ' \
                            'contacted by another persona, %(do_not_contact)s do-not-contact, %(excluded)s ' \
                            'excluded by keywords, %(invalid)s without a LinkedIn URL.' % counts
        return counts

    # ------------------------------------------------------------------
    # li_mark_accepted
    # ------------------------------------------------------------------
    def _accept(self, prospect, note=None):
        prospect = prospect.sudo()
        if prospect.stage not in ('queued', 'invited', 'withdrawn'):
            return False
        now = utc_now()
        without_invite = prospect.stage == 'queued' and not prospect.date_invited
        chat = prospect.persona_id.chat_agent_id
        prospect.write({'stage': 'accepted', 'date_accepted': now,
                        'next_message_date': now + timedelta(hours=chat.first_message_delay or 0)})
        if prospect.date_invited:
            days = (now - prospect.date_invited).days
            line = _('%(name)s accepted the connection request (%(days)s days after invite)',
                     name=prospect.name, days=days)
        else:
            line = _('%(name)s accepted the connection request', name=prospect.name)
        if note:
            line = '%s — %s' % (line, note)
        event = self.env['li.event']._log('invite_accepted', 'connection', persona=prospect.persona_id,
                                          prospect=prospect, detail=line, persona_body=line, prospect_body=line)
        if without_invite:
            event.without_invite = True
        return True

    def _tool_li_mark_accepted(self, work_id, accepted, linkedin_profile=None):
        self._lock()
        item = self._get_item(work_id, ['check_acceptance'])
        self._check_connector(item, linkedin_profile)
        if item.state not in ('released', 'expired'):
            raise ToolError('Work item %s is %s' % (item.id, item.state))
        listed = set(item.prospect_ids.ids)
        marked, ignored = [], []
        for prospect_id in accepted:
            if prospect_id not in listed:
                ignored.append(prospect_id)
                continue
            if self._accept(self.env['li.prospect'].browse(prospect_id)):
                marked.append(prospect_id)
        item._close('done', result_status='ok')
        message = '%s marked accepted.' % len(marked)
        if ignored:
            message += ' Ignored ids not listed in this item: %s.' % ', '.join(map(str, ignored))
        return {'accepted': marked, 'ignored': ignored, 'still_pending': len(listed) - len(marked),
                'message': message}

    # ------------------------------------------------------------------
    # li_report_error
    # ------------------------------------------------------------------
    def _tool_li_report_error(self, linkedin_profile, error, work_id=None, session_expired=False, restricted=False):
        self._lock()
        profile = self._profile_for(linkedin_profile, required=True)
        self._check_chrome(profile)
        item = self.env['li.work.item']
        if work_id:
            item = self._get_item(work_id)
            self._check_connector(item, linkedin_profile, required=True)
        Event = self.env['li.event']
        if restricted:
            if item and item.state == 'released':
                item._close('failed', error=error, quota_consumed=bool(item.confirmed))
            profile.sudo()._set_restricted(error)
            return {'ok': True, 'profile_state': 'restricted',
                    'message': 'Profile %s marked Restricted, its agents paused and the owner told. Stop working '
                               'on it.' % profile.account_key}
        paused = 0
        if session_expired:
            running = profile.persona_ids.filtered(
                lambda p: 'running' in (p.connection_agent_id.state, p.chat_agent_id.state))
            paused = len(running)
            profile.sudo()._set_reconnect_needed(error)
            self.env['li.work.item'].sudo()._cancel_open([('linkedin_profile_id', '=', profile.id)],
                                                         reason='LinkedIn session expired')
            for persona in profile.persona_ids or [self.env['li.persona']]:
                Event._log('error', 'system', persona=persona,
                           detail=_('LinkedIn session expired on %s: %s', profile.name, error),
                           persona_body=persona and _('LinkedIn session expired on %s — agents paused', profile.name))
            return {'ok': True, 'profile_state': 'reconnect_needed', 'paused_personas': paused,
                    'message': 'Profile %s marked Reconnect needed and its agents paused. Skip this profile.'
                               % profile.account_key}
        if item:
            if item.state == 'released':
                item._close('failed', error=error, quota_consumed=bool(item.confirmed))
            line = _('%(type)s failed: %(error)s', type=dict(WORK_TYPES)[item.work_type], error=error)
            Event._log('error', item.agent_type, persona=item.persona_id, prospect=item.prospect_id,
                       detail=line, persona_body=line)
            if item.persona_id or item.agent_type == 'followup':
                self._agent_of(item)._register_error(error)
        else:
            Event._log('error', 'system', detail='%s: %s' % (profile.name, error))
            profile.sudo().message_post(body=_('Error reported by Claude: %s', error))
        return {'ok': True, 'message': 'Error logged.'}

    # ------------------------------------------------------------------
    # li_take_over
    # ------------------------------------------------------------------
    def _tool_li_take_over(self, prospect_id=None, linkedin_url=None, name=None):
        Prospect = self.env['li.prospect']
        if prospect_id:
            prospects = Prospect.browse(prospect_id).exists()
        elif linkedin_url:
            prospects = Prospect.search([('linkedin_username', '=', linkedin_username(linkedin_url))])
        elif name:
            prospects = Prospect.search([('name', 'ilike', name), ('stage', 'not in', CLOSED_STAGES)])
        else:
            raise ToolError('Give prospect_id, linkedin_url or name')
        if not prospects:
            raise ToolError('No matching prospect')
        if name and not prospect_id and not linkedin_url and len(prospects) > 1:
            raise ToolError('Several prospects match "%s": %s. Call again with prospect_id.' % (
                name, '; '.join('%s (id %s, %s, %s)' % (p.name, p.id, p.company or '-', p.persona_id.name)
                                for p in prospects[:10])))
        prospects._take_over(reason='manual')
        return {'taken_over': [{'id': p.id, 'name': p.name, 'by': p.taken_over_by.name} for p in prospects],
                'message': 'Agents stopped for %s.' % ', '.join(prospects.mapped('name'))}

    # ------------------------------------------------------------------
    # li_finish_run
    # ------------------------------------------------------------------
    def _tool_li_finish_run(self, summary=None):
        self._lock()
        icp = self.env['ir.config_parameter'].sudo()
        WorkItem = self.env['li.work.item'].sudo()
        # release still-claimed items that were never sent; their quota comes back
        open_items = WorkItem.search([('state', '=', 'released'), ('confirmed', '=', False)])
        open_items._close('cancelled', cancel_reason='released by li_finish_run')
        now = utc_now()
        last = icp.get_param('li_sales.last_run_finished')
        try:
            since = fields.Datetime.to_datetime(last) if last else None
        except (ValueError, TypeError):
            since = None
        since = max(since or now - timedelta(hours=24), now - timedelta(hours=24))
        events = self.env['li.event'].sudo().search([('date', '>=', since)])
        keys = {'invite_sent': 'invites', 'invite_accepted': 'accepted', 'message_sent': 'messages',
                'followup_sent': 'followups', 'reply_received': 'replies', 'warm_lead': 'warm_leads',
                'error': 'errors'}
        accounts = {}
        for profile in self.env['li.profile'].search([]):
            accounts[profile.id] = dict({v: 0 for v in keys.values()}, linkedin_profile=profile.account_key,
                                        execution_mode=profile.execution_mode)
        per_persona = {}
        for event in events:
            key = keys.get(event.event_type)
            if not key:
                continue
            if event.linkedin_profile_id.id in accounts:
                accounts[event.linkedin_profile_id.id][key] += 1
            if event.persona_id:
                per_persona.setdefault(event.persona_id, dict.fromkeys(keys.values(), 0))[key] += 1
        ai = self.env['li.event']._ai_partner()
        for persona, counts in per_persona.items():
            line = _('Run finished: %(invites)s invites, %(accepted)s accepted, %(messages)s messages, '
                     '%(followups)s follow-ups, %(replies)s replies, %(warm_leads)s warm leads, %(errors)s errors',
                     **counts)
            persona.sudo().message_post(body=line, author_id=ai.id, subtype_xmlid='mail.mt_note')
        icp.set_param('li_sales.last_run_finished', now.strftime('%Y-%m-%d %H:%M:%S'))
        return {'released_items': len(open_items),
                'released_sends': len(open_items.filtered(lambda i: i.work_type in SEND_TYPES)),
                'accounts': list(accounts.values()),
                'since': iso_utc(since),
                'message': 'Run closed; %s unsent item(s) released. Give the user a short summary per LinkedIn '
                           'account.' % len(open_items)}

    # ------------------------------------------------------------------
    # Housekeeping crons
    # ------------------------------------------------------------------
    @api.model
    def _cron_withdraw_old_invites(self):
        """Pending invites older than stop_tracking_after_days -> Withdrawn (6.1.7)."""
        Prospect = self.env['li.prospect'].sudo()
        count = 0
        for agent in self.env['li.connection.agent'].sudo().search([('stop_tracking_after_days', '>', 0)]):
            limit = utc_now() - timedelta(days=agent.stop_tracking_after_days)
            for prospect in Prospect.search([('persona_id', '=', agent.persona_id.id), ('stage', '=', 'invited'),
                                             ('date_invited', '<', limit)]):
                prospect.stage = 'withdrawn'
                line = _('Pending invite to %(name)s withdrawn after %(days)s days (withdraw it by hand on '
                         'LinkedIn if wanted)', name=prospect.name, days=agent.stop_tracking_after_days)
                self.env['li.event']._log('invite_withdrawn', 'connection', persona=agent.persona_id,
                                          prospect=prospect, detail=line, persona_body=line, prospect_body=line)
                count += 1
        return count

