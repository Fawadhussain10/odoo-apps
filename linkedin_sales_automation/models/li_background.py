"""Background LinkedIn work of built-in engine profiles.

A cron does, for every engine profile in turn, what Claude in Chrome does by
hand: send the queued texts and invites, read the inbox and the changed
threads (replies, manual takeover, Activity Agent), check pending invites and
search for new prospects. Everything goes through the same checks and result
handling as the Chrome tools (li_engine.py).

Pacing:
* one profile at a time (session advisory lock per profile, also taken by
  Start / Stop / Connect), one send per profile per run, the profile's delay
  gap between sends, a small random pause between engine calls;
* a run starts an engine call only when it can finish well before Odoo's
  cron time limit; what does not fit waits for the next run;
* a daily read budget per profile shared by search, inbox, threads and
  acceptance checks; part of it is kept for the thread re-read before each
  message.
Every engine call is logged in li.engine.action.
"""
import logging
import random
import time
from datetime import datetime, timedelta
from urllib.parse import unquote

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module
from odoo.tools import config

from .li_common import local_now, normalize_name, one_paragraph, safe_zone, utc_now
from .li_engine import SEARCH_COOLDOWN, VERIFY_VALID, ToolError
from .li_engine_manager import ENGINE_LOCK_NAMESPACE, is_odoo_sh
from .li_engine_parse import (
    connect_outcome, connected_usernames, error_kind, inbox_preview, inbox_threads, interface_language,
    is_weekly_limit, message_outcome, parse_search_results, parse_thread, result_data, result_text,
)
from .li_mcp_client import McpClientError
from .li_post import parse_post_stats

_logger = logging.getLogger(__name__)

SEND_PRIORITY = {'handoff': 0, 'message': 1, 'followup': 2, 'invite': 3}
SEND_TOOLS = {'invite': 'connect_with_person', 'message': 'send_message', 'followup': 'send_message',
              'handoff': 'send_message'}
BACKGROUND_SHARE = 0.8          # background reading may use 80% of the read budget; the rest is for re-reads
THREADS_PER_RUN = 3
MAX_RUN_SECONDS = 240
ACCEPTANCE_RECHECK = timedelta(hours=12)
PROFILE_READ_TRIES = 2
PROFILES_PER_RUN = 2
PROFILE_MAX_CHARS = 4000
INVITES_REFUSED_AFTER = 2                   # different people in a row: the account, not the person
INVITES_REFUSED_PAUSE = timedelta(hours=24)
MAX_TEXT_ATTEMPTS = 3
NO_THREAD_HINTS = ('could not find a conversation',)
ACTIONS = [
    ('profile', 'Read own profile'),
    ('search', 'Search people'),
    ('inbox', 'Read inbox'),
    ('thread', 'Read thread'),
    ('acceptance', 'Check acceptance'),
    ('person', 'Read prospect profile'),
    ('invite_check', 'Check invite dialog'),
    ('invite', 'Send invite'),
    ('message', 'Send message'),
    ('followup', 'Send follow-up'),
    ('handoff', 'Send handoff'),
    ('follow', 'Follow (no Connect)'),
    ('post', 'Publish post'),
    ('post_stats', 'Read post stats'),
]


class LiEngineAction(models.Model):
    """One LinkedIn action done in the background by a built-in engine."""
    _name = 'li.engine.action'
    _description = 'LinkedIn engine action'
    _order = 'id desc'

    linkedin_profile_id = fields.Many2one('li.profile', 'LinkedIn Profile', required=True, index=True,
                                          ondelete='cascade')
    company_id = fields.Many2one(related='linkedin_profile_id.company_id', store=True, index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    action = fields.Selection(ACTIONS, required=True, index=True)
    reads = fields.Integer(help='LinkedIn pages read (counted in the daily read budget).')
    state = fields.Selection([('ok', 'Done'), ('error', 'Error')], required=True, default='ok', index=True)
    status = fields.Char(help='Outcome, e.g. sent, already_connected, session, rate_limit.')
    detail = fields.Text()
    duration_ms = fields.Integer('Duration (ms)')
    work_item_id = fields.Many2one('li.work.item', ondelete='set null')
    prospect_id = fields.Many2one('li.prospect', ondelete='set null', index=True)
    persona_id = fields.Many2one('li.persona', ondelete='set null', index=True)

    @api.model
    def _cron_purge(self, days=60):
        self.search([('date', '<', utc_now() - timedelta(days=days))]).unlink()


class LiProfileBackground(models.Model):
    _inherit = 'li.profile'

    chrome_verified_at = fields.Datetime(readonly=True, copy=False,
                                         help='Claude in Chrome last confirmed it is signed in to this account.')
    bg_last_run = fields.Datetime('Last background run', readonly=True, copy=False)
    bg_paused_until = fields.Datetime('Background paused until', readonly=True, copy=False,
                                      help='LinkedIn asked to slow down: no background work before this time.')
    last_inbox_check = fields.Datetime(readonly=True, copy=False)
    last_acceptance_check = fields.Datetime(readonly=True, copy=False)
    last_connections_check = fields.Datetime(readonly=True, copy=False,
                                             help='Last read of the recent connections list (acceptances).')
    connections_list_ok = fields.Boolean(readonly=True, copy=False,
                                         help='The last read of the recent connections list worked.')
    invites_not_recorded = fields.Integer(readonly=True, copy=False,
                                          help='Different people in a row whose invitation LinkedIn did not record '
                                               '(the profile still showed Connect after sending).')
    invite_refused_prospect_id = fields.Many2one('li.prospect', readonly=True, copy=False, ondelete='set null')
    last_success_at = fields.Datetime('Last successful action', readonly=True, copy=False)
    send_now_until = fields.Datetime(readonly=True, copy=False,
                                     help='"Send now" asked from Claude: until then the engine comes back as soon as '
                                          'the delay gap ends, instead of at its normal interval.')
    interface_language = fields.Selection([('en', 'English'), ('other', 'Not English')],
                                          'LinkedIn language', readonly=True, copy=False,
                                          help='Language of the LinkedIn interface, checked at Connect and Test '
                                               'connection. Odoo reads LinkedIn pages by their English labels: in '
                                               'another language the background work of this profile is paused.')
    language_checked_at = fields.Datetime(readonly=True, copy=False)
    reads_today = fields.Integer('Pages read today', compute='_compute_reads_today')
    read_budget = fields.Integer('Daily read budget', compute='_compute_reads_today')
    engine_action_ids = fields.One2many('li.engine.action', 'linkedin_profile_id', 'Engine actions')

    def _compute_reads_today(self):
        budget = self.env['li.mcp.tools']._param('read_budget', 150)
        for profile in self:
            profile.read_budget = budget
            profile.reads_today = profile._reads_today() if profile.id else 0

    def _apply_interface_language(self, result):
        """Record the LinkedIn interface language seen on the own profile page
        (get_my_profile). Not English: background reading pauses and the owner
        is told; English again: it resumes."""
        self.ensure_one()
        data = result_data(result)
        text = (data.get('sections') or {}).get('main_profile') or result_text(result)
        language = interface_language(text)
        if not language:
            return False
        profile = self.sudo()
        before = profile.interface_language
        profile.write({'interface_language': language, 'language_checked_at': utc_now()})
        summary = _('Set the LinkedIn language of %s to English', profile.account_key)
        if language == 'other' and before != 'other':
            profile.message_post(body=_('The LinkedIn interface of this account is not in English. Odoo reads '
                                        'LinkedIn pages by their English labels, so background work on this '
                                        'profile is paused. On LinkedIn: Settings > Account preferences > '
                                        'Language > English, then press Test connection.'))
            profile.activity_schedule('mail.mail_activity_data_todo', user_id=profile.owner_id.id, summary=summary,
                                      note=_('LinkedIn: Settings > Account preferences > Language > English. Then '
                                             'press Test connection on the profile.'))
        elif language == 'en' and before == 'other':
            profile.activity_ids.filtered(lambda a: a.summary == summary).action_feedback(
                feedback=_('LinkedIn is in English again'))
            profile.message_post(body=_('LinkedIn is in English again — background work resumes.'))
        return language

    def action_test_connection(self):
        """Read the own profile through the engine: session, display name and
        interface language."""
        self.ensure_one()
        profile = self.sudo()
        if not profile._engine_lock(wait=False):
            raise UserError(_('The engine of %s is busy. Try again in a moment.', profile.name))
        if not (profile._engine_is_mine() and profile._engine_ping()):
            return self._notify(_('Test connection'), _('The engine is not running: press Start engine.'), 'warning')
        tools = self.env['li.mcp.tools']
        data, kind, text = tools._bg_call(profile, 'get_my_profile', {}, 'profile', reads=1)
        if kind:
            return self._notify(_('Test connection'), text[:300] or kind, 'danger')
        result = {'structuredContent': data, 'content': [{'type': 'text', 'text': text}]}
        name = self.env['li.profile']._own_profile_name(result)
        if name and name != profile.my_display_name:
            profile.my_display_name = name
        language = profile._apply_interface_language(result)
        if language == 'other':
            return self._notify(_('Test connection'), _('Connected as %s, but LinkedIn is not in English: set it to '
                                                        'English, then test again.', name or profile.name), 'warning')
        return self._notify(_('Test connection'), _('Connected as %s.', name or profile.name), 'success')

    def _chrome_verified(self):
        """Claude in Chrome checked the account recently and it is connected."""
        self.ensure_one()
        return bool(self.connection_state == 'connected' and self.chrome_verified_at
                    and utc_now() - self.chrome_verified_at < VERIFY_VALID)

    def _day_start(self):
        """Start of the profile's day (home time zone, else UTC) as naive UTC."""
        self.ensure_one()
        tz = self.home_timezone or 'UTC'
        local = local_now(tz)
        start = datetime.combine(local.date(), datetime.min.time(), tzinfo=safe_zone(tz))
        return start.astimezone(safe_zone('UTC')).replace(tzinfo=None)

    def _reads_today(self):
        self.ensure_one()
        self.env.cr.execute("""SELECT COALESCE(SUM(reads), 0) FROM li_engine_action
                               WHERE linkedin_profile_id = %s AND date >= %s""", (self.id, self._day_start()))
        return self.env.cr.fetchone()[0]

    def _session_lock(self):
        """Hold the profile's engine lock across the commits of a background run."""
        self.env.cr.execute('SELECT pg_try_advisory_lock(%s, %s)', (ENGINE_LOCK_NAMESPACE, self.id))
        return self.env.cr.fetchone()[0]

    def _session_unlock(self):
        self.env.cr.execute('SELECT pg_advisory_unlock(%s, %s)', (ENGINE_LOCK_NAMESPACE, self.id))

    def action_open_engine_actions(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Engine actions'), 'res_model': 'li.engine.action',
                'view_mode': 'list,form', 'domain': [('linkedin_profile_id', '=', self.id)]}


class LiProspectBackground(models.Model):
    _inherit = 'li.prospect'

    li_thread_id = fields.Char('LinkedIn thread id', readonly=True, copy=False)
    inbox_preview_hash = fields.Char(readonly=True, copy=False)
    thread_check_needed = fields.Boolean(readonly=True, copy=False, index=True,
                                         help='The inbox row changed: the thread is read in the background.')
    last_thread_read = fields.Datetime(readonly=True, copy=False)
    last_acceptance_check = fields.Datetime(readonly=True, copy=False)
    profile_text = fields.Text('LinkedIn profile', readonly=True, copy=False,
                               help='The person\'s LinkedIn profile as read by the engine (headline, about, '
                                    'experience). Claude reads it before writing to this person.')
    profile_read_at = fields.Datetime(readonly=True, copy=False)
    profile_read_tries = fields.Integer(readonly=True, copy=False)

    def _store_profile_text(self, text):
        """Keep the profile page text the engine read for this person."""
        self.ensure_one()
        text = '\n'.join(line.strip() for line in (text or '').splitlines() if line.strip())[:PROFILE_MAX_CHARS]
        if text:
            self.sudo().write({'profile_text': text, 'profile_read_at': utc_now()})
        return bool(text)

    def _profile_pending(self):
        """True while the engine still has to read this person's profile."""
        self.ensure_one()
        return (not self.profile_read_at and self.profile_read_tries < PROFILE_READ_TRIES
                and self.linkedin_profile_id.execution_mode == 'engine' and bool(self.linkedin_username))


class LiProspectRepair(models.Model):
    _inherit = 'li.prospect'

    @api.model
    def _li_repair_mojibake(self):
        """Text read before engine answers were decoded as UTF-8 (garbled names,
        headlines, locations, messages): repair it; a headline that turns out to be
        LinkedIn's connection-degree label is cleared. Safe to run again."""
        from .li_engine_parse import _DEGREE_RE, repair_mojibake
        fixed = 0
        for model, names in (('li.prospect', ('name', 'headline', 'title', 'company', 'location')),
                             ('li.message', ('body', 'sender_name'))):
            records = self.env[model].sudo().with_context(active_test=False).search([])
            for record in records:
                values = {}
                for name in names:
                    value = record[name]
                    if isinstance(value, str):
                        repaired = repair_mojibake(value)
                        if name == 'headline' and repaired and _DEGREE_RE.match(repaired) and len(repaired) < 12:
                            repaired = False
                        if repaired != value:
                            values[name] = repaired
                if values:
                    record.write(values)
                    fixed += 1
        return fixed


class LiProspectUiTextRepair(models.Model):
    _inherit = 'li.prospect'

    @api.model
    def _li_repair_ui_messages(self):
        """Remove LinkedIn interface text that an earlier version stored as messages
        (the online-status banner, quick-reply suggestions), and give back to the
        agents a prospect that was taken over only because of such a line. Safe
        to run again."""
        from .li_engine_parse import _SUGGESTION_RE, is_thread_ui_text
        Message = self.env['li.message'].sudo()
        candidates = Message.search(['|', '|', '|', '|', ('body', '=ilike', 'reply to conversation with%'),
                                     ('body', '=ilike', 'your online status is%'), ('body', '=ilike', 'dismiss'),
                                     ('body', '=ilike', 'manage'), ('body', '=ilike', 'you can change this in your%')])
        wrong = candidates.filtered(lambda m: is_thread_ui_text(m.body))
        for message in wrong:                   # the suggestion's button text stored right beside it
            match = _SUGGESTION_RE.match(message.body.strip())
            wanted = normalize_name(match.group('text').rstrip('.\u2026 ')) if match else ''
            if not wanted:
                continue
            siblings = Message.search([('prospect_id', '=', message.prospect_id.id), ('ai_generated', '=', False),
                                       ('direction', '=', message.direction), ('id', 'not in', wrong.ids)])
            near = siblings.filtered(lambda m: abs(m.id - message.id) <= 2 and (
                normalize_name(m.body) == wanted or (message.body.rstrip().endswith(('\u2026', '...', '\u2026"'))
                                                     and normalize_name(m.body).startswith(wanted))))
            wrong |= near[:1]
        prospects = wrong.mapped('prospect_id')
        count = len(wrong)
        wrong.unlink()
        for prospect in prospects.filtered(lambda p: p.is_taken_over and p.takeover_reason == 'human_message'):
            if not Message.search_count([('prospect_id', '=', prospect.id), ('kind', '=', 'manual')]):
                prospect.write({'is_taken_over': False, 'taken_over_by': False, 'date_taken_over': False,
                                'takeover_reason': False})
                prospect.message_post(
                    body=_('Returned to the agents: the takeover came from LinkedIn interface text, not from a '
                           'message written by hand.'),
                    author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        return count


class LiBackgroundWork(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    # ------------------------------------------------------------------
    # Time, budget, helpers
    # ------------------------------------------------------------------
    @api.model
    def _bg_time_limit(self):
        """Seconds a background run may last: well under Odoo's cron time limit
        (limit_time_real_cron, else limit_time_real), and never more than 4 minutes."""
        limit = config.get('limit_time_real_cron') or 0
        if limit <= 0:
            limit = config.get('limit_time_real') or 0
        return max(min(limit - 15, MAX_RUN_SECONDS), 30) if limit > 0 else MAX_RUN_SECONDS

    @api.model
    def _bg_call_timeout(self):
        """Odoo's wait for one engine call: the engine's own tool timeout plus a margin."""
        return self._param('engine_tool_timeout', 60) + 15

    @api.model
    def _bg_in_test(self):
        return bool(odoo_module.current_test) or self.env.registry.in_test_mode()

    @api.model
    def _bg_commit(self):
        if not self._bg_in_test():
            self.env.cr.commit()

    @api.model
    def _bg_pause(self):
        top = self._param('bg_jitter_max', 8)
        if top > 0:
            time.sleep(random.uniform(min(2, top), top))

    def _bg_budget_left(self, profile, background=True):
        budget = self._param('read_budget', 150)
        allowed = int(budget * BACKGROUND_SHARE) if background else budget
        return allowed - profile._reads_today()

    def _bg_call(self, profile, tool, arguments, action, reads=0, item=None, prospect=None, persona=None):
        """One engine call, logged. Returns (data, error_kind, text): data is the
        structured answer on success, error_kind None then."""
        started = time.monotonic()
        result, kind, text = None, None, ''
        try:
            result = profile._engine_call(tool, arguments, timeout=self._bg_call_timeout())
        except McpClientError as exc:
            text = str(exc)
            kind = 'refused' if 'refused' in text.lower() else (error_kind(text)[0] if 'timed out' in text.lower()
                                                                 else 'transport')
        except UserError as exc:        # engine busy or not running: nothing reached LinkedIn
            text, kind = str(exc), 'refused'
        wait = 0
        if result is not None and result.get('isError'):
            text = result_text(result)
            kind, wait = error_kind(text)
        status = kind or 'ok'
        self.env['li.engine.action'].sudo().create({
            'linkedin_profile_id': profile.id, 'action': action, 'reads': reads,
            'state': 'error' if kind else 'ok', 'status': status, 'detail': (text or '')[:2000] or False,
            'duration_ms': int((time.monotonic() - started) * 1000),
            'work_item_id': item.id if item else False, 'prospect_id': prospect.id if prospect else False,
            'persona_id': (persona or (item and item.persona_id) or (prospect and prospect.persona_id)
                           or self.env['li.persona']).id or False,
        })
        if kind is None:
            profile.sudo().last_success_at = utc_now()
            return result_data(result), None, result_text(result)
        self._bg_account_error(profile, kind, wait, text)
        return None, kind, text

    def _bg_last_action(self, profile):
        return self.env['li.engine.action'].sudo().search([('linkedin_profile_id', '=', profile.id)],
                                                         order='id desc', limit=1)

    def _bg_account_error(self, profile, kind, wait, text):
        """Errors that concern the whole account."""
        profile = profile.sudo()
        if kind == 'session':
            # without a session the engine keeps its own login window open: stop it until Reconnect
            profile._set_reconnect_needed(text[:300])
            profile.engine_wanted = False
            profile._engine_kill()
        elif kind == 'restricted':
            profile._set_restricted(text[:300])
            profile.engine_wanted = False
            profile._engine_kill()
        elif kind == 'rate_limit':
            profile.bg_paused_until = utc_now() + timedelta(seconds=max(wait, 60))
            profile.message_post(body=_('LinkedIn asked to slow down — background work on this profile paused '
                                        'for %s minutes.', max(wait, 60) // 60))

    # ------------------------------------------------------------------
    # The cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_background_work(self):
        """Every few minutes: background LinkedIn work of the engine profiles,
        one profile after the other."""
        self = self.sudo()
        for model in ('li.connection.agent', 'li.chat.agent', 'li.followup.agent', 'li.activity.agent'):
            self.env[model]._resume_due()
        self.env['li.work.item'].sudo()._recover_interrupted_sends()
        self.env['li.post'].sudo()._cron_recover_publishing()
        self._bg_commit()
        if is_odoo_sh():
            return 0
        run_started = utc_now()
        deadline = time.monotonic() + self._bg_time_limit()
        profiles = self.env['li.profile'].sudo().search(
            [('execution_mode', '=', 'engine'), ('connection_state', '=', 'connected'),
             ('engine_wanted', '=', True), ('interface_language', '!=', 'other')],
            order='bg_last_run asc nulls first, id')
        calls = 0
        for profile in profiles:
            if deadline - time.monotonic() < self._bg_call_timeout() + 5:
                break
            if profile.bg_paused_until and profile.bg_paused_until > utc_now():
                continue
            if not profile._session_lock():
                continue                         # Start / Stop / Connect or another run is using it
            try:
                if not (profile._engine_is_mine() and profile.engine_state == 'running'):
                    continue                     # the watchdog restarts it
                profile.bg_last_run = utc_now()
                self._bg_commit()
                calls += self._bg_profile(profile, deadline)
            except Exception:
                if self._bg_in_test():
                    raise
                _logger.exception('Background LinkedIn work failed for profile %s', profile.id)
                self.env.cr.rollback()
            finally:
                profile._session_unlock()
        self._bg_follow_up(run_started)
        return calls

    def _bg_follow_up(self, run_started):
        """Come back as soon as the delay gap of a profile ends, instead of at the
        cron's interval, while that profile has more to send right now: after a send
        in this run, or during a "send now" asked from Claude."""
        now = utc_now()
        Action = self.env['li.engine.action']
        profiles = self.env['li.profile'].sudo().search([('execution_mode', '=', 'engine'),
                                                         ('connection_state', '=', 'connected'),
                                                         ('engine_wanted', '=', True)])
        moments = []
        for profile in profiles:
            active = (profile.send_now_until and profile.send_now_until > now) or Action.search_count([
                ('linkedin_profile_id', '=', profile.id), ('date', '>=', run_started), ('state', '=', 'ok'),
                ('action', 'in', ('invite', 'message', 'followup', 'handoff'))])
            if not active or not self._bg_can_send_more(profile):
                continue
            ready = (profile.last_send_at + timedelta(seconds=profile.send_gap_seconds or 0)
                     if profile.last_send_at else now)
            moments.append(max(now + timedelta(seconds=30), ready + timedelta(seconds=5)))
        if moments:
            self.env.ref('linkedin_sales_automation.cron_background_work').sudo()._trigger(at=min(moments))
        return min(moments) if moments else False

    def _bg_can_send_more(self, profile):
        """Something may go out for this profile today: a queued text whose only
        obstacle is the delay gap, or a queued prospect of a Connection Agent that is
        inside its window with quota left."""
        for item in self.env['li.work.item'].sudo().search([('linkedin_profile_id', '=', profile.id),
                                                           ('state', '=', 'queued')], limit=20):
            if self._send_verdict_dry(item)[0] in ('go', 'wait'):
                return True
        ctx = {'reasons': [], 'left': 1, 'sends': {profile.id: 1}}
        for persona, agent, left in self._connection_personas(profile, ctx):
            if left > 0 and self.env['li.prospect'].sudo().search_count([
                    ('persona_id', '=', persona.id), ('stage', '=', 'queued'), ('needs_check', '=', False),
                    ('is_taken_over', '=', False), ('do_not_contact', '=', False)]):
                return True
        return False

    def _bg_profile(self, profile, deadline):
        calls = 0
        for step in (self._bg_send, self._bg_publish, self._bg_inbox, self._bg_threads, self._bg_profiles, self._bg_acceptance,
                     self._bg_post_stats, self._bg_search):
            if profile.connection_state != 'connected' or (profile.bg_paused_until
                                                             and profile.bg_paused_until > utc_now()):
                break
            if deadline - time.monotonic() < self._bg_call_timeout() + 5:
                break
            done = step(profile, deadline)
            self._bg_commit()
            if done:
                calls += done
                self._bg_pause()
        return calls

    def _bg_time_for(self, deadline, calls=1):
        return deadline - time.monotonic() >= calls * self._bg_call_timeout() + 5

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    @api.model
    def _queue_send(self, work_type, prospect, text=None, step=None, followup_step=None, with_note=False):
        """Put a send on an engine profile's queue: an approved text (invite note,
        message, follow-up, handoff) or an invite without note. The text is
        tied to the conversation as it is now (stale check before sending)."""
        agent_type = {'invite': 'connection', 'message': 'chat', 'handoff': 'chat', 'followup': 'followup'}[work_type]
        prospect = prospect.sudo()
        now = utc_now()
        return self.env['li.work.item'].sudo().create({
            'work_type': work_type, 'agent_type': agent_type, 'state': 'queued',
            'linkedin_profile_id': prospect.linkedin_profile_id.id, 'persona_id': prospect.persona_id.id,
            'prospect_id': prospect.id, 'step_id': step.id if step else False,
            'followup_step_id': followup_step.id if followup_step else False,
            'with_note': with_note, 'text_confirmed': one_paragraph(text) or False,
            'conversation_version': max(prospect.message_ids_li.ids or [0]),
            'date_released': now, 'expires_at': now,
        })

    def _bg_send(self, profile, deadline):
        """At most one send per run: the oldest queued item that may go now,
        else the next invite without note."""
        WorkItem = self.env['li.work.item'].sudo()
        queued = WorkItem.search([('linkedin_profile_id', '=', profile.id), ('state', '=', 'queued')])
        for item in queued.sorted(lambda i: (SEND_PRIORITY.get(i.work_type, 9), i.id)):
            verdict, reason, _wait = self._send_verdict_dry(item)
            if verdict == 'stop':
                item._close('cancelled', cancel_reason=reason)
                continue
            if verdict == 'invalid':
                item._close('cancelled', cancel_reason=reason)
                continue
            if verdict != 'go':
                continue
            return self._bg_send_item(profile, item, deadline)
        item = self._bg_next_plain_invite(profile)
        if item:
            return self._bg_send_item(profile, item, deadline)
        return 0

    def _send_verdict_dry(self, item):
        return self._send_verdict(item, item.text_confirmed, dry=True)

    def _bg_next_plain_invite(self, profile):
        """The next queued prospect of a running Connection Agent that sends
        invites without a note (a note is written by Claude and queued)."""
        ctx = {'reasons': [], 'left': 1, 'sends': {profile.id: 1}}
        for persona, agent, left in self._connection_personas(profile, ctx):
            if left <= 0:
                continue
            busy = self.env['li.work.item'].sudo().search([('persona_id', '=', persona.id),
                                                           ('state', 'in', ('released', 'queued', 'sending'))])
            candidates = self.env['li.prospect'].sudo().search([
                ('persona_id', '=', persona.id), ('stage', '=', 'queued'), ('needs_check', '=', False),
                ('is_taken_over', '=', False), ('do_not_contact', '=', False),
                ('id', 'not in', busy.mapped('prospect_id').ids)], order='create_date asc, id asc', limit=20)
            for prospect in candidates:
                if self._is_do_not_contact(prospect):
                    continue
                if agent.send_note and not prospect.invite_without_note:
                    break                       # needs a note from Claude first
                item = self._queue_send('invite', prospect)
                verdict, _reason, _wait = self._send_verdict_dry(item)
                if verdict == 'go':
                    return item
                item.unlink()
                break
        return self.env['li.work.item']

    def _bg_send_item(self, profile, item, deadline):
        """Re-read the thread (messages), re-check every rule, send, record."""
        calls = 0
        if item.work_type != 'invite':
            if self._bg_budget_left(profile, background=False) < 1:
                return 0                        # no read left today for the re-read: wait for tomorrow
            fresh, read_calls = self._bg_refresh_thread(profile, item)
            calls += read_calls
            if not fresh:
                return calls
            if not self._bg_time_for(deadline):
                return calls                    # send in the next run (it re-reads again)
        if item.text_confirmed and item.text_confirmed != one_paragraph(item.text_confirmed):
            item.text_confirmed = one_paragraph(item.text_confirmed)
        verdict, reason, _wait = self._send_verdict(item, item.text_confirmed)
        if verdict in ('stop', 'invalid'):
            item._close('cancelled', cancel_reason=reason)
            return calls
        if verdict != 'go':
            return calls
        item.write({'state': 'sending', 'quota_consumed': True})
        self._bg_commit()                       # from here a crash means "outcome unknown", never a resend
        prospect = item.prospect_id
        if item.work_type == 'invite':
            arguments = {'linkedin_username': prospect.linkedin_username}
            if item.with_note and item.text_confirmed:
                arguments['note'] = item.text_confirmed
        else:
            arguments = {'linkedin_username': prospect.linkedin_username, 'message': item.text_confirmed,
                         'confirm_send': True}
        data, kind, text = self._bg_call(profile, SEND_TOOLS[item.work_type], arguments, item.work_type,
                                         item=item, prospect=prospect)
        calls += 1
        if item.work_type == 'invite' and kind is None:
            prospect._store_profile_text(data.get('profile'))     # the invite already loaded their profile page
        if (item.work_type == 'invite' and kind is None and self._bg_time_for(deadline)
                and (data.get('status') or '').strip().lower() == 'send_failed'
                and not is_weekly_limit(data.get('message'))):
            data, kind, text, check_calls = self._bg_check_invite_dialog(profile, item, data)
            calls += check_calls
        if (item.work_type == 'invite' and kind is None and connect_outcome(data)[0] == 'not_invitable'
                and item.persona_id.connection_agent_id.follow_if_no_connect and self._bg_time_for(deadline)):
            data, kind, text, follow_calls = self._bg_follow(profile, item, data)
            calls += follow_calls
        self._bg_send_result(profile, item, data, kind, text)
        return calls

    def _bg_check_invite_dialog(self, profile, item, connect_data):
        """LinkedIn did not record an invitation: open that person's invite dialog
        without sending (check_invite_dialog, an Odoo tool added to the engine)
        to tell a person who can only be invited with their email address, or a
        limit LinkedIn states there, from an account-wide refusal."""
        data, kind, text = self._bg_call(profile, 'check_invite_dialog',
                                         {'linkedin_username': item.prospect_id.linkedin_username}, 'invite_check',
                                         reads=1, item=item, prospect=item.prospect_id)
        if kind in ('session', 'restricted', 'rate_limit'):
            return None, kind, text, 1
        if kind is None and data.get('status') == 'email_required':
            return {'status': 'connect_unavailable',
                    'message': _('LinkedIn asks for this person\'s email address to connect.')}, None, text, 1
        if kind is None and is_weekly_limit(data.get('text')):
            return dict(connect_data, message=(data.get('text') or '')[:300]), None, text, 1
        return connect_data, None, text, 1

    def _bg_follow(self, profile, item, connect_data):
        """No Connect on that profile: follow the person instead (follow_person,
        an Odoo tool added to the engine). Returns the answer to record."""
        data, kind, text = self._bg_call(profile, 'follow_person',
                                         {'linkedin_username': item.prospect_id.linkedin_username}, 'follow',
                                         item=item, prospect=item.prospect_id)
        if kind is None and data.get('status') in ('followed', 'already_following'):
            return {'status': 'followed', 'message': data.get('message')}, None, text, 1
        if kind in ('session', 'restricted', 'rate_limit'):
            return None, kind, text, 1
        return connect_data, None, text, 1

    def _bg_refresh_thread(self, profile, item):
        """Read the prospect's thread right before a message. Returns (fresh, calls):
        fresh is False when the text must not go out (conversation changed,
        takeover, unreadable thread)."""
        prospect = item.prospect_id
        if not self._bg_read_thread(profile, prospect, reread=True):
            return False, 1
        if item.state != 'queued':              # a new reply or a takeover cancelled it
            return False, 1
        if max(prospect.message_ids_li.ids or [0]) > item.conversation_version:
            item.write({'discarded_stale': True})
            item._close('cancelled', cancel_reason=_('the conversation changed after the text was written'))
            return False, 1
        return True, 1

    def _bg_send_result(self, profile, item, data, kind, text):
        if kind is None:
            if item.work_type == 'invite':
                status, retry_safe, detail = connect_outcome(data)
            else:
                status, retry_safe, detail = message_outcome(data)
        elif kind in ('session', 'rate_limit', 'refused'):
            status, retry_safe, detail = 'requeue', True, text   # stopped before LinkedIn was touched
        elif kind == 'restricted':
            status, retry_safe, detail = 'restricted', True, text
        elif kind == 'not_found':
            status, retry_safe, detail = 'not_found', True, text
        elif kind in ('timeout', 'transport'):
            status, retry_safe, detail = 'unknown', False, text
        else:
            status, retry_safe, detail = 'failed', True, text
        if status == 'enter_to_send':
            self._bg_enter_to_send(profile)
            status = 'failed'
        if item.work_type == 'invite' and kind is None:
            if status == 'sent':
                profile.sudo().write({'invites_not_recorded': 0, 'invite_refused_prospect_id': False})
            elif status == 'failed' and (data.get('status') or '').strip().lower() == 'send_failed' \
                    and self._bg_invite_not_recorded(profile, item, detail):
                return
        if status == 'requeue' or (status == 'failed' and item.text_confirmed
                                    and item.send_attempts + 1 < MAX_TEXT_ATTEMPTS):
            item.write({'state': 'queued', 'confirmed': False, 'date_confirmed': False, 'quota_consumed': False,
                        'send_attempts': item.send_attempts + (status == 'failed'), 'error': detail or False})
            return
        if status == 'restricted':
            item._close('failed', result_status=status, quota_consumed=False, error=detail)
            return
        try:
            self._apply_send_result(item, status, text_sent=item.text_confirmed,
                                    note_sent=bool(item.with_note and item.text_confirmed),
                                    retry_safe=retry_safe, error=detail if status != 'sent' else None)
        except ToolError as exc:
            item._close('failed', result_status='unknown', quota_consumed=True, error=str(exc))
            item.prospect_id._flag_check(_('The engine answered %(status)s but Odoo could not record it: %(e)s',
                                           status=status, e=exc))

    def _bg_invite_not_recorded(self, profile, item, detail):
        """The engine submitted the invitation but LinkedIn did not record it (the
        profile still shows Connect). Once is retried as a normal failure; for
        different people in a row it is the account: LinkedIn's invitation limit,
        which it only shows in a pop-up. The Connection Agents of the account are
        paused for a day instead of failing prospect after prospect. Returns True
        when the item was handled here."""
        profile = profile.sudo()
        count = profile.invites_not_recorded
        if count >= INVITES_REFUSED_AFTER or profile.invite_refused_prospect_id != item.prospect_id:
            count += 1
        profile.write({'invites_not_recorded': count, 'invite_refused_prospect_id': item.prospect_id.id})
        if count < INVITES_REFUSED_AFTER:
            return False
        if item.text_confirmed:                 # keep the note Claude wrote for when invites work again
            item.write({'state': 'queued', 'confirmed': False, 'date_confirmed': False, 'quota_consumed': False,
                        'error': detail or False})
        else:
            item._close('failed', result_status='invite_not_recorded', quota_consumed=False, retry_safe=True,
                        error=detail)
        until = utc_now() + INVITES_REFUSED_PAUSE
        reason = _('LinkedIn is not recording invitations from %(profile)s (sent, but the profile still shows '
                   'Connect) — usually LinkedIn\'s invitation limit for the account; invites are paused for a day',
                   profile=profile.name)
        paused = self.env['li.connection.agent']
        for persona in profile.persona_ids:
            agent = persona.connection_agent_id.sudo()
            if agent.state == 'running':
                paused |= agent._pause_until(until, reason)
                agent.consecutive_errors = 0
        profile.message_post(body=reason, author_id=self.env['li.event']._ai_partner().id,
                             subtype_xmlid='mail.mt_note')
        for agent in paused:
            self.env['li.event']._log('error', 'connection', persona=agent.persona_id, detail=reason)
        return True

    def _bg_enter_to_send(self, profile):
        summary = _('Switch LinkedIn to "Click Send to send" (%s)', profile.account_key)
        if not profile.activity_ids.filtered(lambda a: a.summary == summary):
            profile.sudo().activity_schedule(
                'mail.mail_activity_data_todo', user_id=profile.owner_id.id, summary=summary,
                note=_('LinkedIn\'s "Press Enter to Send" setting hides the Send button, so messages cannot go '
                       'out. In LinkedIn messaging, open the send options next to the Send button and choose '
                       '"Click Send to send".'))

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------
    def _bg_publish(self, profile, deadline):
        """Publish the next approved post that is due (create_post, an Odoo tool
        added to the engine). Marked Publishing and committed first: a crash means
        an unknown outcome, never a second post."""
        Post = self.env['li.post'].sudo()
        post = Post.search(Post._due_domain(profile), order='scheduled_at asc, id asc', limit=1)
        if not post:
            return 0
        post.write({'state': 'publishing', 'publish_started': utc_now()})
        self._bg_commit()
        image_path = self._bg_post_image(post)
        arguments = {'text': post.text}
        if image_path:
            arguments['image_path'] = str(image_path)
        try:
            data, kind, text = self._bg_call(profile, 'create_post', arguments, 'post')
        finally:
            if image_path:
                image_path.unlink(missing_ok=True)
        if kind is None:
            status = data.get('status')
            if status == 'published':
                post._mark_published(data.get('post_url'))
            elif status == 'published_no_url':
                post._mark_published(None, note=data.get('message'))
            else:
                post._publish_failed('%s: %s' % (status, data.get('message') or ''), bool(data.get('retry_safe')))
        elif kind in ('session', 'rate_limit', 'refused'):
            post.write({'state': 'scheduled' if post.scheduled_at else 'approved', 'publish_started': False})
        else:
            post._publish_failed(text[:500], retry_safe=kind not in ('timeout', 'transport'))
        return 1

    def _bg_post_image(self, post):
        """Write the post image where only the engine reads it (deleted after the call)."""
        if not post.image:
            return None
        import base64
        manager = self.env['li.engine.manager']
        folder = manager._secure_dir(manager._root() / 'incoming')
        data = base64.b64decode(post.image)
        extension = 'png' if data[:4] == b'\x89PNG' else 'gif' if data[:3] == b'GIF' else 'jpg'
        path = folder / ('%s-post-%s.%s' % (self.env.cr.dbname, post.id, extension))
        path.write_bytes(data)
        path.chmod(0o600)
        return path

    def _bg_post_stats(self, profile, deadline):
        """Re-read one published post a week (90 days), within the read budget."""
        Post = self.env['li.post'].sudo()
        post = Post.search(Post._stats_domain(profile), order='stats_checked_at asc nulls first', limit=1)
        if not post or self._bg_budget_left(profile) < 1:
            return 0
        data, kind, _text = self._bg_call(profile, 'get_post_stats', {'post_url': post.post_url}, 'post_stats',
                                          reads=1)
        if kind is None:
            post._set_stats(*parse_post_stats((data.get('sections') or {}).get('post', '')))
        elif kind == 'not_found':
            post.stats_checked_at = utc_now()
        return 1

    # ------------------------------------------------------------------
    # Inbox and threads
    # ------------------------------------------------------------------
    def _bg_inbox_candidates(self, profile):
        tracked = self._tracked_prospects(profile, limit=100)
        invited = self.env['li.prospect'].sudo().search([('linkedin_profile_id', '=', profile.id),
                                                         ('stage', '=', 'invited'), ('do_not_contact', '=', False)],
                                                        limit=200)
        return tracked | invited

    def _bg_inbox(self, profile, deadline):
        minutes = self._param('inbox_interval', 60)
        if profile.last_inbox_check and utc_now() - profile.last_inbox_check < timedelta(minutes=minutes):
            return 0
        followup = self.env['li.followup.agent']._get()
        activity = self.env['li.activity.agent']._get()
        if not (any(p.chat_agent_id.state == 'running' for p in profile.persona_ids)
                or followup.state == 'running' or activity.state == 'running'
                or any(p.connection_agent_id.state == 'running' for p in profile.persona_ids)):
            return 0
        candidates = self._bg_inbox_candidates(profile)
        if not candidates or self._bg_budget_left(profile) < 1:
            return 0
        data, kind, _text = self._bg_call(profile, 'get_inbox', {'limit': 20}, 'inbox', reads=1)
        profile.sudo().last_inbox_check = utc_now()
        if kind:
            return 1
        threads = inbox_threads(data)
        for prospect in candidates:
            preview = inbox_preview(data, prospect.name)
            if not preview:
                continue
            vals = {}
            thread_id = threads.get(normalize_name(prospect.name))
            if thread_id and thread_id != prospect.li_thread_id:
                vals['li_thread_id'] = thread_id
            if preview != prospect.inbox_preview_hash:
                vals.update(inbox_preview_hash=preview, thread_check_needed=True)
            if vals:
                prospect.sudo().write(vals)
        return 1

    def _bg_threads(self, profile, deadline):
        prospects = self.env['li.prospect'].sudo().search([('linkedin_profile_id', '=', profile.id),
                                                           ('thread_check_needed', '=', True)],
                                                          order='write_date asc', limit=THREADS_PER_RUN)
        calls = 0
        for prospect in prospects:
            if not self._bg_time_for(deadline) or self._bg_budget_left(profile) < 1:
                break
            self._bg_read_thread(profile, prospect)
            calls += 1
            self._bg_commit()
            if profile.connection_state != 'connected':
                break
        return calls

    def _bg_read_thread(self, profile, prospect, reread=False):
        """Read one thread and record what is new. Returns True when the thread
        was read (an existing empty thread counts as read)."""
        if not profile.my_display_name:
            self.env['li.engine.action'].sudo().create({
                'linkedin_profile_id': profile.id, 'action': 'thread', 'state': 'error', 'status': 'no_name',
                'prospect_id': prospect.id,
                'detail': _('My display name is empty: press Reconnect LinkedIn so Odoo can tell your messages '
                            'from the prospect\'s.')})
            return False
        arguments = ({'thread_id': prospect.li_thread_id} if prospect.li_thread_id
                     else {'linkedin_username': prospect.linkedin_username})
        data, kind, text = self._bg_call(profile, 'get_conversation', arguments, 'thread', reads=1,
                                         prospect=prospect)
        prospect = prospect.sudo()
        prospect.write({'thread_check_needed': False, 'last_thread_read': utc_now()})
        if kind:
            return kind == 'other' and any(h in text.lower() for h in NO_THREAD_HINTS)
        conversation = (data.get('sections') or {}).get('conversation', '')
        messages = parse_thread(conversation, profile.my_display_name, prospect.name)
        if messages is None:
            if conversation.strip():
                self.env['li.engine.action'].sudo().create({
                    'linkedin_profile_id': profile.id, 'action': 'thread', 'state': 'error', 'status': 'unreadable',
                    'prospect_id': prospect.id,
                    'detail': _('The thread could not be read message by message. Page text:\n%s',
                                conversation[:1500])})
                return False
            return True                          # an empty thread
        if messages:
            self._record_thread(profile, prospect, messages)
        return True

    # ------------------------------------------------------------------
    # Prospect profiles (read once, before the Chat Agent writes)
    # ------------------------------------------------------------------
    def _bg_profiles(self, profile, deadline):
        """Read the LinkedIn profile of people the Chat Agent is about to write to
        (get_person_profile, one page each, once per person). Claude gets the text
        with every item for that person and reads it before writing."""
        from .li_engine_chat import CHAT_STAGES
        prospects = self.env['li.prospect'].sudo().search([
            ('linkedin_profile_id', '=', profile.id), ('stage', 'in', CHAT_STAGES), ('profile_read_at', '=', False),
            ('profile_read_tries', '<', PROFILE_READ_TRIES), ('is_taken_over', '=', False),
            ('do_not_contact', '=', False), ('linkedin_username', '!=', False),
            ('persona_id.chat_agent_id.state', '=', 'running')], order='date_accepted asc, id asc',
            limit=PROFILES_PER_RUN)
        calls = 0
        for prospect in prospects:
            if not self._bg_time_for(deadline) or self._bg_budget_left(profile) < 1:
                break
            data, kind, _text = self._bg_call(profile, 'get_person_profile',
                                              {'linkedin_username': prospect.linkedin_username}, 'person', reads=1,
                                              prospect=prospect)
            calls += 1
            if kind in ('session', 'restricted', 'rate_limit', 'refused'):
                break                               # nothing was read: try again in a later run
            text = (((data or {}).get('sections') or {}).get('main_profile') or '') if kind is None else ''
            prospect.profile_read_tries += 1
            if not prospect._store_profile_text(text) and kind == 'not_found':
                prospect.profile_read_at = utc_now()
            self._bg_commit()
        return calls

    # ------------------------------------------------------------------
    # Acceptance and search
    # ------------------------------------------------------------------
    def _bg_invited_domain(self, profile):
        return [('linkedin_profile_id', '=', profile.id), ('stage', '=', 'invited'),
                '|', ('persona_id.connection_agent_id.state', '!=', 'stopped'),
                ('persona_id.chat_agent_id.state', '=', 'running')]

    def _bg_acceptance(self, profile, deadline):
        """Acceptances: one read of the newest connections finds all of them;
        the per-person search is the fallback when that list cannot be read."""
        calls, stop = self._bg_recent_connections(profile)
        if stop or profile.connections_list_ok:
            return calls
        minutes = self._param('acceptance_every', 60)
        if profile.last_acceptance_check and utc_now() - profile.last_acceptance_check < timedelta(minutes=minutes):
            return calls
        pending = self.env['li.prospect'].sudo().search(self._bg_invited_domain(profile) + [
            '|', ('last_acceptance_check', '=', False), ('last_acceptance_check', '<', utc_now() - ACCEPTANCE_RECHECK),
        ], order='last_acceptance_check asc nulls first, date_invited asc', limit=self._param('acceptance_per_run', 3))
        if not pending:
            return calls
        profile.sudo().last_acceptance_check = utc_now()
        calls = 0
        for prospect in pending:
            if not self._bg_time_for(deadline) or self._bg_budget_left(profile) < 1:
                break
            data, kind, _text = self._bg_call(profile, 'search_people', {'keywords': prospect.name, 'network': ['F']},
                                              'acceptance', reads=1, prospect=prospect)
            calls += 1
            prospect.last_acceptance_check = utc_now()
            if kind:
                break
            if prospect.linkedin_username in connected_usernames(data):
                self._accept(prospect, note=_('found among the 1st-degree connections'))
            self._bg_commit()
        return calls

    def _bg_recent_connections(self, profile):
        """Read the newest connections (get_recent_connections, an Odoo tool added
        to the engine) every few minutes while invites are pending, and mark every
        invited prospect found there as accepted."""
        minutes = self._param('connections_every', 15)
        if profile.last_connections_check and utc_now() - profile.last_connections_check < timedelta(minutes=minutes):
            return 0, False
        invited = self.env['li.prospect'].sudo().search(self._bg_invited_domain(profile))
        if not invited or self._bg_budget_left(profile) < 1:
            return 0, False
        data, kind, _text = self._bg_call(profile, 'get_recent_connections', {'limit': 40}, 'acceptance', reads=1)
        if kind in ('session', 'restricted', 'rate_limit', 'refused'):
            profile.sudo().last_connections_check = utc_now()
            return 1, True          # no more LinkedIn reads in this run
        usernames = {unquote(u).strip('/').lower() for u in (data or {}).get('usernames') or []} if not kind else set()
        profile.sudo().write({'last_connections_check': utc_now(), 'connections_list_ok': bool(usernames)})
        for prospect in invited:
            if (prospect.linkedin_username or '').lower() in usernames:
                self._accept(prospect, note=_('found among the recent connections'))
        self._bg_commit()
        return 1, False

    def _bg_search(self, profile, deadline):
        Prospect = self.env['li.prospect']
        ctx = {'reasons': [], 'left': 1, 'sends': {profile.id: 0}}
        for persona, agent, left in self._connection_personas(profile, ctx):
            queued = Prospect.search_count([('persona_id', '=', persona.id), ('stage', '=', 'queued'),
                                            ('needs_check', '=', False)])
            if queued >= left:
                continue
            if agent.last_search_date and utc_now() - agent.last_search_date < SEARCH_COOLDOWN:
                continue
            if self._bg_budget_left(profile) < 1:
                return 0
            titles = [t.strip() for t in (persona.job_titles or '').replace('\n', ',').split(',') if t.strip()]
            locations = persona.location_ids.mapped('name')
            combos = [(t, l) for l in (locations or ['']) for t in (titles or [''])]
            title, location = combos[agent.search_page % len(combos)]
            keywords = ' '.join(filter(None, [title, persona.include_keywords]))
            arguments = {'keywords': keywords}
            if location:
                arguments['location'] = location
            agent.sudo().last_search_date = utc_now()
            data, kind, _text = self._bg_call(profile, 'search_people', arguments, 'search', reads=1, persona=persona)
            if kind:
                return 1
            own = (profile.linkedin_url or '').rstrip('/').rsplit('/', 1)[-1].lower()
            people = parse_search_results(data, own_username=own)
            counts = self._add_people(persona, people)
            self._bg_last_action(profile).detail = \
                _('%(found)s found: %(created)s queued, %(dup)s duplicates, %(other)s skipped',
                  found=len(people), created=counts['created'], dup=counts['duplicates'],
                  other=counts['contacted_elsewhere'] + counts['do_not_contact'] + counts['excluded']
                  + counts['invalid'])
            return 1
        return 0
