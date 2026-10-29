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
import re
import time
from datetime import datetime, timedelta
from urllib.parse import unquote

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module
from odoo.tools import config

from .li_common import in_window, local_now, normalize_name, one_paragraph, safe_zone, utc_now
from .li_engine import SEARCH_COOLDOWN, VERIFY_VALID, ToolError
from .li_engine_manager import ENGINE_LOCK_NAMESPACE, is_odoo_sh
from .li_engine_parse import (
    connect_outcome, connected_usernames, error_kind, inbox_preview, inbox_threads, interface_language,
    is_account_warning, is_weekly_limit, message_outcome, top_card_state, parse_search_results, parse_thread, result_data, result_text,
)
from .li_mcp_client import McpClientError
from .li_post import parse_post_stats

_logger = logging.getLogger(__name__)

SEND_PRIORITY = {'handoff': 0, 'message': 1, 'followup': 2, 'invite': 3}
SEND_TOOLS = {'invite': 'connect_with_person', 'message': 'send_message', 'followup': 'send_message',
              'handoff': 'send_message'}
BACKGROUND_SHARE = 0.8          # background reading may use 80% of the read budget; the rest is for re-reads
# The frequent reads (inbox, changed threads, acceptances) may use 60% of the budget at most, so the
# rest of the background share stays free for invite verification, profile reads and search all day.
ROUTINE_SHARE = 0.6
# The engine call reached nothing or the account itself has a problem: stop reading LinkedIn in this run.
ACCOUNT_KINDS = ('session', 'restricted', 'rate_limit', 'warning')
STOP_KINDS = ACCOUNT_KINDS + ('refused',)
LOCATION_LOOKUP_EVERY = timedelta(days=7)
SEARCH_PAGES = 100
WARNING_PAUSE = timedelta(hours=24)     # LinkedIn warned the account about automated activity
ROUTINE_ACTIONS = ('inbox', 'thread', 'acceptance')
ENGINE_SLOW_AFTER = timedelta(minutes=30)      # a just-started engine is never judged slow
ENGINE_SLOW_SHARE = 0.6                         # of the engine's time limit per action
ENGINE_SLOW_READS = 3
INBOX_OFF_HOURS = 60            # minutes between inbox reads outside the personas' working hours
SENT_RECHECK = timedelta(hours=24)          # invites already verified are compared with the Sent list daily
THREADS_PER_RUN = 8             # default of li_sales.threads_per_run
THREAD_READ_TRIES = 5           # failed reads of one changed thread before it is left alone
# changed threads are opened in this order: conversations in progress, new connections, closed people
THREAD_PRIORITY = {'replied': 0, 'messaged': 0, 'warm': 0, 'meeting': 0, 'accepted': 1, 'invited': 1, 'queued': 1}
CLOSED_PER_INBOX = 300
MAX_RUN_SECONDS = 240
ACCEPTANCE_RECHECK = timedelta(hours=12)
INVITE_VERIFY_AFTER = timedelta(minutes=10)     # LinkedIn has settled by then
INVITE_VERIFY_WITHIN = timedelta(days=7)
INVITE_VERIFY_PER_RUN = 3
NO_SENT_INVITATIONS = re.compile(r'no (sent|pending) invitations|no invitations (sent|pending)|haven.t sent any|have no (sent|pending)', re.I)
INVITE_VERIFY_PER_CRON = 10
INVITE_VERIFY_TRIES = 3
SENT_PAGE_SIZE = 10             # LinkedIn's Sent invitations page shows this many before "Show more"
INVITE_PERSON_TRIES = 2         # invitations LinkedIn did not record for one person before a person is asked
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
    ('location', 'Look up location'),
    ('inbox', 'Read inbox'),
    ('thread', 'Read thread'),
    ('acceptance', 'Check acceptance'),
    ('person', 'Read prospect profile'),
    ('invite_verify', 'Verify invite'),
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
    last_sent_check = fields.Datetime(readonly=True, copy=False,
                                      help='Last read of LinkedIn\'s Sent invitations page.')
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

    def _reads_today(self, actions=None):
        """Pages read today; `actions` limits the count to those kinds of action."""
        self.ensure_one()
        self.env.cr.execute("""SELECT COALESCE(SUM(reads), 0) FROM li_engine_action
                               WHERE linkedin_profile_id = %s AND date >= %s
                                 AND (%s OR action = ANY(%s))""",
                            (self.id, self._day_start(), not actions, list(actions or [])))
        return self.env.cr.fetchone()[0]

    def _session_lock(self):
        """Hold the profile's engine lock across the commits of a background run."""
        self.env.cr.execute('SELECT pg_try_advisory_lock(%s, %s)', (ENGINE_LOCK_NAMESPACE, self.id))
        return self.env.cr.fetchone()[0]

    def _session_unlock(self):
        self.env.cr.execute('SELECT pg_advisory_unlock(%s, %s)', (ENGINE_LOCK_NAMESPACE, self.id))

    def _linkedin_warned(self, text):
        """LinkedIn showed this account its "unusual activity" page: it has seen
        too many pages opened by a tool. The engine stays running, but nothing is
        read or sent for a day (the agents resume by themselves after it), and the
        owner is told to lower the settings that cause the traffic."""
        profile = self.sudo()
        if profile.bg_paused_until and profile.bg_paused_until > utc_now() + WARNING_PAUSE / 2:
            return                              # already handled
        until = utc_now() + WARNING_PAUSE
        profile.bg_paused_until = until
        reason = _('LinkedIn warned %s about unusual activity (a high volume of pages opened by a tool): '
                   'nothing is read or sent for 24 hours', profile.name)
        for persona in profile.persona_ids:
            persona.connection_agent_id._pause_until(until, reason)
            persona.chat_agent_id._pause_until(until, reason)
            self.env['li.event']._log('error', 'system', persona=persona, detail=reason)
        how = _('Before the agents run again, lower the traffic: Settings > Check inbox every 30 minutes or more, '
                'Daily read budget about 200, Recent connections every 60 minutes, and send windows that '
                'cover real business hours instead of the whole day. Open LinkedIn yourself and complete any '
                'check it asks for.')
        profile.message_post(body=_('%(reason)s. LinkedIn said: %(said)s %(how)s', reason=reason,
                                    said=(text or '')[:300], how=how),
                             author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        profile.activity_schedule('mail.mail_activity_data_todo', user_id=profile.owner_id.id,
                                  summary=_('LinkedIn warned %s about unusual activity', profile.account_key),
                                  note=how)

    def _engine_is_slow(self):
        """The engine's browser gets slower the longer it runs: the same inbox
        read that takes 12 seconds after a start takes a minute some hours
        later, and then every read fails at the time limit. True when the last
        three inbox reads since the start each took most of that limit."""
        self.ensure_one()
        if not self.engine_started or utc_now() - self.engine_started < ENGINE_SLOW_AFTER:
            return False
        limit_ms = self.env['li.mcp.tools']._param('engine_tool_timeout', 60) * 1000 * ENGINE_SLOW_SHARE
        rows = self.env['li.engine.action'].sudo().search([
            ('linkedin_profile_id', '=', self.id), ('action', '=', 'inbox'), ('date', '>=', self.engine_started)],
            order='id desc', limit=ENGINE_SLOW_READS)
        return len(rows) == ENGINE_SLOW_READS and all(row.duration_ms >= limit_ms for row in rows)

    @api.model
    def _cron_engine_watchdog(self):
        """Also restarts an engine whose reads have become slow, before they
        start failing: a fresh engine is fast again."""
        if not is_odoo_sh():
            for profile in self.sudo().search([('engine_wanted', '=', True), ('execution_mode', '=', 'engine'),
                                               ('engine_state', '=', 'running')]):
                if not profile._engine_is_slow() or not profile._engine_lock(wait=False):
                    continue                    # in use right now: the next round looks again
                if profile._engine_is_mine():
                    _logger.info('LinkedIn engine of profile %s restarted: its reads had become slow', profile.id)
                    profile._engine_kill()
                    profile.engine_wanted = True
                    profile.message_post(body=_('Engine restarted by itself: LinkedIn pages had become slow to '
                                                'read (a fresh engine is fast again).'),
                                         author_id=self.env['li.event']._ai_partner().id,
                                         subtype_xmlid='mail.mt_note')
        return super()._cron_engine_watchdog()

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
    thread_read_tries = fields.Integer(readonly=True, copy=False,
                                       help='Failed reads in a row of the changed thread (it is retried).')
    last_acceptance_check = fields.Datetime(readonly=True, copy=False)
    invite_verified_at = fields.Datetime(readonly=True, copy=False,
                                         help='Some minutes after an invite Odoo opens the profile again and '
                                              'checks that LinkedIn shows the invitation as pending.')
    invite_verify_tries = fields.Integer(readonly=True, copy=False)
    invite_gone_check = fields.Datetime(readonly=True, copy=False,
                                        help='Last look at the profile after the invitation left LinkedIn\'s Sent list.')
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
            self.sudo()._li_fill_fields()
        return bool(text)

    def _li_fill_fields(self):
        """Headline, location, title and company from what Odoo already knows:
        a headline that landed in Location goes back, the saved profile page
        fills what is missing, and title and company come from the headline.
        The profile page is LinkedIn's own top card, so it also replaces a value
        it does not contain that is no headline or place at all (a search-results
        line such as "See open roles" or the next person's name)."""
        from .li_engine_parse import looks_like_headline, profile_top_fields, split_headline
        for prospect in self:
            vals = {}
            page = prospect.profile_text or ''
            headline, location = prospect.headline or '', prospect.location or ''
            if not headline and looks_like_headline(location):
                headline, location = location, ''
            page_headline, page_location = profile_top_fields(page, prospect.name)
            if page_headline and (not headline or (headline not in page and not looks_like_headline(headline))):
                headline = page_headline
            if page_location and not looks_like_headline(page_location) and location not in page:
                location = ''
            if not location or looks_like_headline(location):
                location = page_location if not looks_like_headline(page_location) else ''
            changed = headline != (prospect.headline or '')
            if changed:
                vals['headline'] = headline[:250] or False
            if location != (prospect.location or ''):
                vals['location'] = location[:120] or False
            title, company = split_headline(headline)
            # title and company taken from a wrong headline go with it
            stale = changed and page_headline == headline
            if title and (not prospect.title or (stale and prospect.title not in page)):
                vals['title'] = title
            if stale and prospect.company and prospect.company not in page:
                vals['company'] = company or False
            elif not prospect.company and company:
                vals['company'] = company
            if vals:
                prospect.write(vals)

    @api.model
    def _li_once(self, key, force=False):
        """True the first time a one-time repair asks (then remembered), or when forced."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param(key) and not force:
            return False
        params.set_param(key, '1')
        return True

    @api.model
    def _li_repair_prospect_fields(self, force=False):
        """Once, on upgrade: fill title and company and put misplaced headlines back."""
        if not self._li_once('li_sales.repaired_prospect_fields', force):
            return 0
        prospects = self.sudo().with_context(active_test=False).search([])
        prospects._li_fill_fields()
        return len(prospects)

    @api.model
    def _li_repair_search_line_fields(self, force=False):
        """Once, on upgrade: headlines and places taken from search-result lines
        that were not about the person ("See open roles", a Sales Navigator offer,
        the next person's name) are replaced from the saved profile page."""
        if not self._li_once('li_sales.repaired_search_line_fields', force):
            return 0
        prospects = self.sudo().with_context(active_test=False).search([('profile_text', '!=', False)])
        prospects._li_fill_fields()
        return len(prospects)

    def _profile_pending(self):
        """True while the engine still has to read this person's profile."""
        self.ensure_one()
        return (not self.profile_read_at and self.profile_read_tries < PROFILE_READ_TRIES
                and self.linkedin_profile_id.execution_mode == 'engine' and bool(self.linkedin_username))


class LiProspectRepair(models.Model):
    _inherit = 'li.prospect'

    @api.model
    def _li_repair_mojibake(self, force=False):
        """Text read before engine answers were decoded as UTF-8 (garbled names,
        headlines, locations, messages): repair it; a headline that turns out to be
        LinkedIn's connection-degree label is cleared. Runs once on upgrade."""
        from .li_engine_parse import _DEGREE_RE, repair_mojibake
        if not self._li_once('li_sales.repaired_mojibake', force):
            return 0
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
    def _li_repair_ui_messages(self, force=False):
        """Remove LinkedIn interface text that an earlier version stored as messages
        (the online-status banner, quick-reply suggestions), and give back to the
        agents a prospect that was taken over only because of such a line. Runs
        once on upgrade."""
        from .li_engine_parse import _SUGGESTION_RE, is_thread_ui_text
        if not self._li_once('li_sales.repaired_ui_messages', force):
            return 0
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


class LiProspectInviteReverify(models.Model):
    _inherit = 'li.prospect'

    @api.model
    def _li_reverify_invites(self):
        """Once: invites marked verified by the first version of the check (which
        read the profile buttons) are checked again against LinkedIn's list."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('li_sales.invite_verify_sent_list'):
            return 0
        prospects = self.sudo().search([('stage', '=', 'invited'), ('invite_verified_at', '!=', False)])
        prospects.write({'invite_verified_at': False, 'invite_verify_tries': 0})
        params.set_param('li_sales.invite_verify_sent_list', '1')
        return len(prospects)


class LiProspectAttachmentRepair(models.Model):
    _inherit = 'li.prospect'

    @api.model
    def _li_merge_attachment_messages(self):
        """Once: a shared file was stored as three messages (its name, its size,
        "Download"). They become one "[Attachment] name (size)" message, so the
        conversation reads right and the file gets an answer."""
        from .li_engine_parse import attachment_run
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('li_sales.attachments_merged'):
            return 0
        Message = self.env['li.message'].sudo()
        merged = 0
        for prospect in Message.search([('body', '=ilike', 'download')]).mapped('prospect_id'):
            messages = prospect.message_ids_li.sorted('id')
            index = 0
            while index < len(messages):
                same = messages[index:index + 3].filtered(lambda m: m.direction == messages[index].direction)
                count, text = attachment_run(same.mapped('body')) if same[:1] == messages[index] else (0, '')
                if count:
                    messages[index].body = text
                    messages[index + 1:index + count].unlink()
                    merged += 1
                index += count or 1
        params.set_param('li_sales.attachments_merged', '1')
        return merged


class LiProspectFollowedRetry(models.Model):
    _inherit = 'li.prospect'

    @api.model
    def _li_requeue_followed_with_connect(self):
        """Once: people who were only followed although their saved profile page
        shows a Connect button go back to the queue for a real invitation."""
        from .li_engine_parse import top_card_state
        if not self._li_once('li_sales.followed_with_connect_requeued'):
            return 0
        prospects = self.sudo().search([('stage', '=', 'followed'), ('do_not_contact', '=', False),
                                        ('is_taken_over', '=', False), ('profile_text', '!=', False)])
        prospects = prospects.filtered(lambda p: top_card_state(p.profile_text) == 'connectable')
        prospects.write({'stage': 'queued', 'send_attempts': 0})
        for prospect in prospects:
            prospect.message_post(body=_('Back in the queue: the profile shows a Connect button, so following '
                                         'was not the right outcome.'),
                                  author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        return len(prospects)

    @api.model
    def _li_requeue_followed_once(self):
        """Once: people who were only followed because the engine saw no Connect
        go back to the queue, so the wider search for Connect (invite link,
        Connect button, More menu) gets a try. Still no Connect: followed again."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('li_sales.followed_requeued'):
            return 0
        prospects = self.sudo().search([('stage', '=', 'followed'), ('do_not_contact', '=', False),
                                        ('is_taken_over', '=', False)])
        prospects.write({'stage': 'queued', 'send_attempts': 0})
        for prospect in prospects:
            prospect.message_post(body=_('Back in the queue once: Odoo now also looks for Connect in the More menu.'),
                                  author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        params.set_param('li_sales.followed_requeued', '1')
        return len(prospects)


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

    def _bg_routine_left(self, profile):
        """Reads left for the frequent work (inbox, changed threads, acceptances)."""
        cap = int(self._param('read_budget', 150) * ROUTINE_SHARE)
        return min(cap - profile._reads_today(ROUTINE_ACTIONS), self._bg_budget_left(profile))

    def _bg_working_hours(self, profile):
        """True inside the working hours of one of the profile's personas: a target
        working day, within the send window of an agent of that persona that is not stopped."""
        for persona in profile.persona_ids:
            now = local_now(persona.target_timezone)
            if not persona._is_working_day(now):
                continue
            for agent in (persona.connection_agent_id, persona.chat_agent_id):
                if agent and agent.state != 'stopped' and in_window(now, agent.send_window_from,
                                                                    agent.send_window_to):
                    return True
        return False

    def _bg_inbox_minutes(self, profile):
        """Minutes between inbox reads: the setting during working hours, at least
        an hour outside them (nobody is answered at night anyway)."""
        fast = self._inbox_interval()
        if self._bg_working_hours(profile):
            return fast
        return max(fast, self._param('inbox_interval_off_hours', INBOX_OFF_HOURS))

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
            # the engine gives up on an action after its time limit and then only says "Error calling
            # tool": that is a timeout (a send may have gone out), not a plain failure
            limit = self._param('engine_tool_timeout', 60)
            if kind == 'other' and time.monotonic() - started >= limit - 1:
                kind = 'timeout'
                text = _('%(text)s (no answer within %(n)s seconds: LinkedIn was loading slowly)',
                         text=text, n=limit)
        if result is not None and is_account_warning(result_text(result)):
            # LinkedIn showed its "unusual activity" page instead of what was asked: whatever the tool
            # answered, nothing more is read or sent on this account for a day
            text, kind = result_text(result), 'warning'
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
        elif kind == 'warning':
            profile._linkedin_warned(text)
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
        for step in (self._bg_send, self._bg_publish, self._bg_inbox, self._bg_threads, self._bg_verify_invites, self._bg_profiles, self._bg_acceptance,
                     self._bg_post_stats, self._bg_locations, self._bg_search):
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
        if item.work_type == 'invite' and self._bg_invites_on_probation(profile):
            return calls                        # the last invite is verified first
        item.write({'state': 'sending', 'quota_consumed': True})
        self._bg_commit()                       # from here a crash means "outcome unknown", never a resend
        prospect = item.prospect_id
        verified_pending = False
        if item.work_type == 'invite':
            data, kind, text, more, verified_pending = self._bg_invite(profile, item, deadline)
            calls += more
            if kind == 'later':                 # not enough time left for the next step: this person waits
                item.write({'state': 'queued', 'confirmed': False, 'date_confirmed': False,
                            'quota_consumed': False, 'error': text or False})
                return calls
            if kind == 'handled':               # closed and left to a person inside _bg_invite
                return calls
        else:
            arguments = {'linkedin_username': prospect.linkedin_username, 'message': item.text_confirmed,
                         'confirm_send': True}
            data, kind, text = self._bg_call(profile, SEND_TOOLS[item.work_type], arguments, item.work_type,
                                             item=item, prospect=prospect)
            calls += 1
        self._bg_send_result(profile, item, data, kind, text)
        if verified_pending and prospect.stage == 'invited':
            prospect.invite_verified_at = utc_now()         # LinkedIn's Sent list or the profile showed it
        return calls

    def _bg_invite(self, profile, item, deadline):
        """One invitation, by every route. Returns (data, kind, text, calls,
        verified): verified when LinkedIn itself showed the invitation (Sent list
        or "Pending" on the profile). kind 'later' means no time is left for the
        next step, so the person waits for another run: nobody is followed
        before every Connect route was tried, and nobody is followed while an
        invitation may exist."""
        prospect = item.prospect_id
        follow = item.persona_id.connection_agent_id.follow_if_no_connect
        calls, verified = 0, False
        page = ''                               # the profile page as the engine read it for this invite
        later = (None, 'later', _('Waiting for a run with enough time to finish this invitation.'))

        def status():
            return (data.get('status') or '').strip().lower() if kind is None else ''

        def no_connect():
            return kind is None and connect_outcome(data)[0] == 'not_invitable'

        if item.connect_tried:
            # an earlier run tried every Connect route: only Follow is left
            data, kind, text = {'status': 'connect_unavailable',
                                'message': _('LinkedIn offers no Connect for this profile.')}, None, ''
        else:
            arguments = {'linkedin_username': prospect.linkedin_username}
            if item.with_note and item.text_confirmed:
                arguments['note'] = item.text_confirmed
            data, kind, text = self._bg_call(profile, 'connect_with_person', arguments, 'invite', item=item,
                                             prospect=prospect)
            calls += 1
            if kind is None:
                prospect._store_profile_text(data.get('profile'))     # the invite already loaded their profile page
                page = data.get('profile') or ''
                self._bg_note_action(profile, prospect, 'invite', _(
                    'Engine: %(status)s. LinkedIn confirmed: %(confirmed)s. Notice: %(notice)s. Dialog: %(dialog)s',
                    status=data.get('status') or '?', confirmed=_('yes') if data.get('confirmed') else _('no'),
                    notice=data.get('linkedin_notice') or '-', dialog=data.get('invite_dialog') or '-'))
        if status() == 'pending' and not prospect.date_invited and self._bg_time_for(deadline, 2):
            data, kind, text, more, verified = self._bg_pending_or_send(profile, item, data, deadline)
            calls += more
        if status() == 'send_failed' and self._bg_time_for(deadline) and not is_weekly_limit(data.get('message')):
            data, kind, text, more = self._bg_check_invite_dialog(profile, item, data)
            calls += more
        if no_connect() and not item.connect_tried and top_card_state(data.get('profile')) == 'pending':
            # the engine saw no Connect because an invitation is already outstanding
            self._bg_note_action(profile, prospect, 'invite', _(
                'The profile itself shows "Pending": an invitation to this person already exists.'))
            data, verified = dict(data, status='pending'), True
        if no_connect() and not item.connect_tried:
            if not data.get('direct'):          # (direct: the routes were tried already, engine misread "pending")
                if not self._bg_time_for(deadline):
                    return later + (calls, False)   # never Follow without having tried every Connect route
                data, kind, text, more, checked = self._bg_connect_any_way(profile, item, data, deadline)
                calls += more
                verified = verified or checked
                if kind == 'later':
                    return later + (calls, False)
                if kind == 'no_follow':         # the routes could not be tried: a person looks, nobody is followed
                    kind, follow = None, False
            if no_connect() and follow and top_card_state(page or prospect.profile_text) == 'connectable':
                # the profile itself shows a Connect button: it is not a follow-only profile, Odoo just
                # could not press Connect. Never Follow then: try again, and after three tries ask a person
                item.send_attempts += 1
                if item.send_attempts < MAX_TEXT_ATTEMPTS:
                    return later + (calls, False)
                reason = _('The LinkedIn profile of %s shows a Connect button, but Odoo could not open the '
                           'invitation (tried %s times, by the invite link, the button and the More menu). '
                           'Invite them by hand on LinkedIn, or skip them. They were not followed.',
                           prospect.name, item.send_attempts)
                item._close('failed', result_status='connect_not_pressed', quota_consumed=False, retry_safe=True,
                            error=reason)
                prospect._flag_check(reason)
                return None, 'handled', reason, calls, False
            if no_connect():
                item.connect_tried = True
        if no_connect() and follow:
            if not self._bg_time_for(deadline):
                return later + (calls, False)   # Follow in the next run (the routes are not tried again)
            data, kind, text, more = self._bg_follow(profile, item, data)
            calls += more
        return data, kind, text, calls, verified

    def _bg_connect_any_way(self, profile, item, connect_data, deadline):
        """The engine saw no Connect on this profile (often Follow is the main
        button and Connect sits in the "More" menu). send_invite_direct, an Odoo
        tool added to the engine, tries LinkedIn's invite link, the Connect button
        and the More menu in turn. Returns (data, kind, text, calls, verified):
        the engine's own answer again when no route offers Connect, so the person
        is followed. When the tool could not finish, nobody is followed: kind
        'later' tries again in another run, 'no_follow' leaves it to a person."""
        prospect = item.prospect_id
        arguments = {'linkedin_username': prospect.linkedin_username}
        if item.with_note and item.text_confirmed:
            arguments['note'] = item.text_confirmed
        self._bg_pause()
        data, kind, text = self._bg_call(profile, 'send_invite_direct', arguments, 'invite', item=item,
                                         prospect=prospect)
        if kind in STOP_KINDS:
            return None, kind, text, 1, False
        if kind in ('timeout', 'transport'):
            # the tool stopped half-way: Connect may have been pressed
            data, kind = {'status': 'maybe_sent', 'direct': True, 'message': text}, None
        elif kind:
            item.send_attempts += 1
            if item.send_attempts < MAX_TEXT_ATTEMPTS:
                return None, 'later', text, 1, False
            return connect_data, 'no_follow', text, 1, False
        self._bg_note_action(profile, prospect, 'invite', _(
            'No Connect found by the engine: tried the invite link, the Connect button and the More menu. '
            'Result: %(status)s by %(route)s. LinkedIn confirmed: %(confirmed)s. Notice: %(notice)s. '
            'Dialog: %(dialog)s', status=data.get('status') or '?', route=data.get('route') or '-',
            confirmed=_('yes') if data.get('confirmed') else _('no'),
            notice=data.get('linkedin_notice') or '-', dialog=data.get('invite_dialog') or '-'))
        calls, verified = 1, False
        if (data.get('status') or '').lower() == 'maybe_sent':
            data, more, verified = self._bg_settle_maybe_sent(profile, item, data, deadline)
            calls += more
        if (data.get('status') or '').lower() == 'connect_unavailable':
            return connect_data, None, text, calls, False       # really no Connect: follow instead
        return data, None, text, calls, verified

    def _bg_settle_maybe_sent(self, profile, item, data, deadline):
        """send_invite_direct pressed Connect (or stopped half-way) and nothing
        showed what LinkedIn did. LinkedIn's Sent list decides before anything
        else happens to this person: on the list, the invitation exists; a list
        proven whole without them, nothing was sent (no Connect); anything else
        is an unknown outcome a person checks. Returns (data, calls, verified)."""
        prospect = item.prospect_id
        unknown = dict(data, status='outcome_unknown', message=_(
            'Connect was pressed for %s but nothing shows whether LinkedIn sent the invitation.', prospect.name))
        if not self._bg_time_for(deadline) or self._bg_budget_left(profile, background=False) < 1:
            return unknown, 0, False
        self._bg_pause()
        listed, kind, _text = self._bg_call(profile, 'get_sent_invitations', {'limit': 300}, 'invite_verify',
                                            reads=1, prospect=prospect)
        names, proven = self._bg_sent_list(listed, kind)
        self._bg_note_sent_list(profile, prospect, listed, kind)
        if (prospect.linkedin_username or '').lower() in names:
            return dict(data, status='connected', message=_('Invitation found on LinkedIn\'s Sent list.')), 1, True
        if proven:
            return dict(data, status='connect_unavailable', message=_(
                'Connect was pressed but LinkedIn\'s Sent list holds no invitation to this person.')), 1, False
        return unknown, 1, False

    def _bg_pending_or_send(self, profile, item, connect_data, deadline):
        """The engine says an invitation to this person is already pending, but
        Odoo never sent one. The engine reads that from the profile's buttons and
        gets it wrong for some profiles (it then sends nothing). LinkedIn's Sent
        list decides: on the list, it really is pending; not on it, the invite
        goes out through LinkedIn's invite link (send_invite_direct).
        Returns (data, kind, text, calls, verified_pending)."""
        prospect = item.prospect_id
        words = top_card_state(connect_data.get('profile'))
        if words == 'pending':
            self._bg_note_action(profile, prospect, 'invite', _(
                'The profile itself shows "Pending": an invitation to this person already exists.'))
            return connect_data, None, '', 0, True
        listed, kind, text = self._bg_call(profile, 'get_sent_invitations', {'limit': 300}, 'invite_verify',
                                           reads=1, prospect=prospect)
        if kind in STOP_KINDS:
            return None, kind, text, 1, False
        names, proven = self._bg_sent_list(listed, kind)
        self._bg_note_sent_list(profile, prospect, listed, kind)
        if (prospect.linkedin_username or '').lower() in names:
            return connect_data, None, text, 1, True
        if not (words == 'connectable' or proven):
            # nothing proves the engine wrong: believe it, the later verification looks again
            return connect_data, None, text, 1, False
        self._bg_pause()
        arguments = {'linkedin_username': prospect.linkedin_username}
        if item.with_note and item.text_confirmed:
            arguments['note'] = item.text_confirmed
        data, kind, text = self._bg_call(profile, 'send_invite_direct', arguments, 'invite', item=item,
                                         prospect=prospect)
        if kind:
            return None, kind, text, 2, False
        self._bg_note_action(profile, prospect, 'invite', _(
            'The engine read "pending" but LinkedIn\'s Sent list had no invitation: sent through the invite link. '
            'Result: %(status)s. LinkedIn confirmed: %(confirmed)s. Notice: %(notice)s. Dialog: %(dialog)s',
            status=data.get('status') or '?', confirmed=_('yes') if data.get('confirmed') else _('no'),
            notice=data.get('linkedin_notice') or '-', dialog=data.get('invite_dialog') or '-'))
        if (data.get('status') or '').lower() == 'maybe_sent':
            data, more, verified = self._bg_settle_maybe_sent(profile, item, data, deadline)
            return data, None, text, 2 + more, verified
        return data, None, text, 2, False

    def _bg_check_invite_dialog(self, profile, item, connect_data):
        """LinkedIn did not record an invitation: open that person's invite dialog
        without sending (check_invite_dialog, an Odoo tool added to the engine)
        to tell a person who can only be invited with their email address, or a
        limit LinkedIn states there, from an account-wide refusal."""
        data, kind, text = self._bg_call(profile, 'check_invite_dialog',
                                         {'linkedin_username': item.prospect_id.linkedin_username}, 'invite_check',
                                         reads=1, item=item, prospect=item.prospect_id)
        if kind in ACCOUNT_KINDS:
            return None, kind, text, 1
        if kind is None and data.get('status') == 'email_required':
            return {'status': 'connect_unavailable',
                    'message': _('LinkedIn asks for this person\'s email address to connect.')}, None, text, 1
        if kind is None and is_weekly_limit(data.get('text')):
            return dict(connect_data, message=(data.get('text') or '')[:300]), None, text, 1
        return connect_data, None, text, 1

    def _bg_sent_list(self, data, kind):
        """(usernames, proven): the people on LinkedIn's Sent invitations page, and
        whether the list is proven to be whole. Only then does "not on the list"
        mean "no invitation": the page shows the newest ones first and may stop
        after a page."""
        if kind:
            return set(), False
        data = data or {}
        names = {unquote(u).strip('/').lower() for u in data.get('usernames') or []}
        total = data.get('total') or 0
        if not names:
            return names, bool(NO_SENT_INVITATIONS.search(data.get('page_text') or ''))
        rows_only = data.get('rows_only')       # the names come from invitation rows, not from any link on the page
        if rows_only is False:
            return names, False                 # suggested people may be among them: proves nothing
        if total:
            return names, len(names) == total if rows_only else len(names) >= total
        return names, bool(data.get('complete')) and len(names) < SENT_PAGE_SIZE

    def _bg_note_sent_list(self, profile, prospect, data, kind):
        """Keep what LinkedIn's Sent invitations page showed, for a person to compare."""
        if kind:
            return
        names = [unquote(u).strip('/') for u in (data or {}).get('usernames') or []]
        rows_only = (data or {}).get('rows_only')
        if rows_only:
            origin = _('invitation rows')
        elif rows_only is False:
            # no invitation row was recognised on the page: the names are every profile link on it
            origin = _('fallback (profile checks)')
        else:
            origin = _('not stated by the engine')
        self._bg_note_action(profile, prospect, 'invite_verify', _(
            'LinkedIn Sent list: %(n)s people read (LinkedIn says %(total)s), source: %(origin)s, '
            'proven whole: %(proven)s. %(names)s | page: %(page)s',
            n=len(names), total=(data or {}).get('total') or '?', origin=origin,
            proven=_('yes') if self._bg_sent_list(data, kind)[1] else _('no'),
            names=', '.join(names[:80]) or '-', page=((data or {}).get('page_text') or '')[:300]))

    def _bg_note_action(self, profile, prospect, action, text):
        """Add what LinkedIn showed to the last logged action of that kind."""
        row = self.env['li.engine.action'].sudo().search([
            ('linkedin_profile_id', '=', profile.id), ('action', '=', action), ('prospect_id', '=', prospect.id)],
            order='id desc', limit=1)
        if row:
            row.detail = ((row.detail + '\n') if row.detail else '') + (text or '')[:1500]

    def _bg_follow(self, profile, item, connect_data):
        """No Connect on that profile: follow the person instead (follow_person,
        an Odoo tool added to the engine). Returns the answer to record."""
        data, kind, text = self._bg_call(profile, 'follow_person',
                                         {'linkedin_username': item.prospect_id.linkedin_username}, 'follow',
                                         item=item, prospect=item.prospect_id)
        if kind is None and data.get('status') in ('followed', 'already_following'):
            return {'status': 'followed', 'message': data.get('message')}, None, text, 1
        if kind in ACCOUNT_KINDS:
            return None, kind, text, 1
        return connect_data, None, text, 1

    def _bg_refresh_thread(self, profile, item):
        """Read the prospect's thread right before a message. Returns (fresh, calls):
        fresh is False when the text must not go out (conversation changed,
        takeover, unreadable thread)."""
        prospect = item.prospect_id
        if not self._bg_read_thread(profile, prospect, reread=True):
            if prospect.needs_check and item.state == 'queued':     # flagged by the read: never sent blind
                item._close('cancelled', cancel_reason=_('the conversation could not be read before sending'))
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
        elif kind in ('session', 'rate_limit', 'refused', 'warning'):
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
            if self._bg_use_click_to_send(profile, data):
                # nothing was typed or sent: the same text goes out in the next run, no attempt counted
                item.write({'state': 'queued', 'confirmed': False, 'date_confirmed': False,
                            'quota_consumed': False, 'error': False})
                return
            self._bg_enter_to_send(profile)
            status = 'failed'
        if item.work_type == 'invite' and kind is None:
            if status == 'sent' and profile.invites_not_recorded < INVITES_REFUSED_AFTER:
                # a single earlier glitch is over; after real refusals only a verified invite clears it
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
        self._bg_pause_invites(profile)
        return True

    def _bg_pause_invites(self, profile):
        """LinkedIn is not recording this account's invitations: pause its
        Connection Agents for a day (they try again by themselves)."""
        profile = profile.sudo()
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
        if paused:
            profile.message_post(body=reason, author_id=self.env['li.event']._ai_partner().id,
                                 subtype_xmlid='mail.mt_note')
        for agent in paused:
            self.env['li.event']._log('error', 'connection', persona=agent.persona_id, detail=reason)
        return paused

    # ------------------------------------------------------------------
    # Invite verification
    # ------------------------------------------------------------------
    def _bg_unverified_invites(self, profile, settled=False):
        # invite_verify_tries only limits the profile fallback: LinkedIn's Sent list always decides
        domain = [('linkedin_profile_id', '=', profile.id), ('stage', '=', 'invited'),
                  ('invite_verified_at', '=', False),
                  ('date_invited', '>=', utc_now() - INVITE_VERIFY_WITHIN), ('linkedin_username', '!=', False)]
        if settled:
            domain.append(('date_invited', '<=', utc_now() - INVITE_VERIFY_AFTER))
        return self.env['li.prospect'].sudo().search(domain, order='date_invited asc, id asc')

    def _bg_invites_on_probation(self, profile):
        """After LinkedIn refused invitations, send one at a time: the next one
        waits until the last one was verified as pending."""
        return (profile.invites_not_recorded >= INVITES_REFUSED_AFTER and bool(
            self._bg_unverified_invites(profile).filtered(lambda p: p.invite_verify_tries < INVITE_VERIFY_TRIES)))

    @api.model
    def _cron_verify_invites(self):
        """Scheduled action of its own: check the invites of every engine profile
        against LinkedIn (see _bg_verify_invites). The background job does the
        same a few at a time; this one works through a backlog faster and can be
        run by hand from Scheduled Actions."""
        self = self.sudo()
        if is_odoo_sh():
            return 0
        deadline = time.monotonic() + self._bg_time_limit()
        profiles = self.env['li.profile'].sudo().search(
            [('execution_mode', '=', 'engine'), ('connection_state', '=', 'connected'),
             ('engine_wanted', '=', True), ('interface_language', '!=', 'other')])
        calls = 0
        for profile in profiles:
            if deadline - time.monotonic() < self._bg_call_timeout() + 5:
                break
            if profile.bg_paused_until and profile.bg_paused_until > utc_now():
                continue
            if not profile._session_lock():
                continue                         # the background job or a Connect is using the engine
            try:
                if profile._engine_is_mine() and profile.engine_state == 'running':
                    calls += self._bg_verify_invites(profile, deadline, limit=INVITE_VERIFY_PER_CRON)
            except Exception:
                if self._bg_in_test():
                    raise
                _logger.exception('Invite verification failed for profile %s', profile.id)
                self.env.cr.rollback()
            finally:
                profile._session_unlock()
        return calls

    def _bg_verify_invites(self, profile, deadline, limit=None):
        """About ten minutes after an invite, check it against LinkedIn's own
        list of pending invitations (get_sent_invitations, an Odoo tool added to
        the engine: My Network > Manage > Sent). On the list: the invitation
        exists. Gone from a list proven whole: the person's own profile says why
        (see _bg_judge_invite): accepted, never recorded (back to the queue) or
        declined (closed, never invited again). Invites verified earlier are
        compared with the list too, at least once a day. When the list cannot
        be read whole, the profile of each unverified person is checked instead."""
        Prospect = self.env['li.prospect'].sudo()
        prospects = self._bg_unverified_invites(profile, settled=True).filtered(
            lambda p: p.invite_verify_tries < INVITE_VERIFY_TRIES)     # after that a person decides
        watched = Prospect.search([('linkedin_profile_id', '=', profile.id), ('stage', '=', 'invited'),
                                   ('invite_verified_at', '!=', False), ('linkedin_username', '!=', False)])
        # nothing new to verify: the list is still read once a day for the invites it showed before
        last_look = profile.last_sent_check or min(watched.mapped('invite_verified_at') or [utc_now()])
        daily = bool(watched) and utc_now() - last_look >= SENT_RECHECK
        if not (prospects or daily) or not self._bg_time_for(deadline) or self._bg_budget_left(profile) < 1:
            return 0
        data, kind, _text = self._bg_call(profile, 'get_sent_invitations', {'limit': 300}, 'invite_verify', reads=1)
        calls = 1
        if kind in STOP_KINDS:
            return calls
        profile.sudo().last_sent_check = utc_now()
        sent, proven = self._bg_sent_list(data, kind)
        self._bg_note_sent_list(profile, Prospect, data, kind)
        missing = Prospect
        for prospect in prospects:
            if (prospect.linkedin_username or '').lower() in sent:
                prospect.invite_verified_at = utc_now()            # LinkedIn lists it as pending
                profile.sudo().write({'invites_not_recorded': 0, 'invite_refused_prospect_id': False})
            else:
                missing |= prospect
        # verified earlier and gone now: accepted or declined (looked at once in twelve hours at most)
        recheck = utc_now() - ACCEPTANCE_RECHECK
        vanished = watched.filtered(
            lambda p: (p.linkedin_username or '').lower() not in sent
            and (not p.invite_gone_check or p.invite_gone_check < recheck)) if proven else Prospect
        self._bg_commit()
        if not (missing or vanished):
            return calls
        if not proven:
            # the list may be cut off (newest first): absence proves nothing, so look at each profile
            return calls + self._bg_verify_invites_by_profile(profile, missing, deadline, limit)
        if not self._bg_time_for(deadline) or self._bg_budget_left(profile) < 1:
            return calls
        # gone from the list: one read of the newest connections finds those who accepted
        self._bg_pause()
        data, kind, _text = self._bg_call(profile, 'get_recent_connections', {'limit': 80}, 'invite_verify', reads=1)
        calls += 1
        if kind in STOP_KINDS:
            return calls
        connected = {unquote(u).strip('/').lower() for u in (data or {}).get('usernames') or []} if kind is None \
            else set()
        checked = 0
        for prospect in missing | vanished:
            if (prospect.linkedin_username or '').lower() in connected:
                self._accept(prospect, note=_('found connected when the invite was verified'))
                self._bg_commit()
                continue
            # not pending, not among the newest connections: the person's own profile decides
            if checked >= (limit or INVITE_VERIFY_PER_RUN) or not self._bg_time_for(deadline) \
                    or self._bg_budget_left(profile) < 1:
                break
            self._bg_pause()
            calls += 1
            checked += 1
            if not self._bg_judge_invite(profile, prospect):
                break
            self._bg_commit()
        return calls

    def _bg_verify_invites_by_profile(self, profile, prospects, deadline, limit=None):
        """Fallback when the Sent invitations list cannot be read whole: look at
        each person's profile."""
        calls = 0
        prospects = prospects.filtered(lambda p: p.invite_verify_tries < INVITE_VERIFY_TRIES)
        for prospect in prospects[:limit or INVITE_VERIFY_PER_RUN]:
            if not self._bg_time_for(deadline) or self._bg_budget_left(profile) < 1:
                break
            self._bg_pause()
            calls += 1
            if not self._bg_judge_invite(profile, prospect):
                break
            self._bg_commit()
        return calls

    def _bg_judge_invite(self, profile, prospect):
        """Open the profile of someone whose invitation is not (or no longer) on
        LinkedIn's Sent list and act on what it shows (check_connection_state):
        * Pending: the invitation exists;
        * Message / 1st degree: they accepted;
        * Connect again: an invite LinkedIn's list showed before was declined or
          ignored: closed, never invited again. One that never showed up there
          was not recorded by LinkedIn: back to the queue;
        * anything else: looked at again later.
        Returns False when the account itself has a problem (stop checking)."""
        data, kind, _text = self._bg_call(profile, 'check_connection_state',
                                          {'linkedin_username': prospect.linkedin_username}, 'invite_verify',
                                          reads=1, prospect=prospect)
        if kind in STOP_KINDS:
            return False
        state = (data or {}).get('status') if kind is None else None
        words = top_card_state((data or {}).get('top_text')) if kind is None else ''
        self._bg_note_action(profile, prospect, 'invite_verify', _(
            'Profile check: engine says %(state)s, the page\'s buttons say %(words)s',
            state=state or '?', words=words or _('neither Pending nor Connect')))
        seen_before = bool(prospect.invite_verified_at)
        prospect.invite_gone_check = utc_now()
        if words == 'pending':
            if not seen_before:
                prospect.invite_verified_at = utc_now()        # the profile itself shows "Pending"
                profile.sudo().write({'invites_not_recorded': 0, 'invite_refused_prospect_id': False})
        elif words == 'connectable' or (not words and state == 'connectable'):
            if seen_before:
                self._invite_declined(prospect)
            else:
                self._invite_was_not_recorded(profile, prospect)
        elif state == 'already_connected':
            self._accept(prospect, note=_('found connected when the invite was verified'))
        elif not seen_before:
            # the engine's "pending" alone is not proof (it misreads some profiles): try again later
            prospect.invite_verify_tries += 1
        return True

    def _invite_declined(self, prospect):
        """The invitation existed and is gone while the profile offers Connect
        again: declined, ignored or withdrawn. Closed; this person is never
        invited again, by any persona."""
        prospect = prospect.sudo()
        invited_on = prospect.date_invited
        prospect.write({'stage': 'declined'})
        self.env['li.work.item'].sudo()._cancel_open([('prospect_id', '=', prospect.id)],
                                                     reason=_('invitation declined'))
        line = _('%(name)s declined or ignored the invitation sent on %(date)s UTC (it left LinkedIn\'s Sent '
                 'list and the profile offers Connect again) — closed, never invited again',
                 name=prospect.name, date=fields.Datetime.to_string(invited_on)[:16] if invited_on else '?')
        self.env['li.event']._log('invite_withdrawn', 'connection', persona=prospect.persona_id, prospect=prospect,
                                  detail=line, persona_body=line, prospect_body=line)

    def _invite_was_not_recorded(self, profile, prospect):
        """LinkedIn shows Connect again for someone recorded as invited."""
        invited_on = prospect.date_invited
        items = self.env['li.work.item'].sudo().search([
            ('prospect_id', '=', prospect.id), ('work_type', '=', 'invite'), ('state', '=', 'done')],
            order='id desc', limit=1)
        items.write({'quota_consumed': False, 'result_status': 'invite_not_recorded',
                     'error': _('LinkedIn did not record this invitation.')})
        self.env['li.event'].sudo().search([('prospect_id', '=', prospect.id), ('event_type', '=', 'invite_sent'),
                                            ('date', '>=', invited_on - timedelta(minutes=5))]).unlink()
        self.env['li.message'].sudo().search([('prospect_id', '=', prospect.id), ('kind', '=', 'note'),
                                              ('work_item_id', 'in', items.ids)]).unlink()
        attempts = prospect.send_attempts + 1
        prospect.write({'stage': 'queued', 'date_invited': False, 'invite_verify_tries': 0,
                        'send_attempts': attempts})
        line = _('LinkedIn did not record the invitation to %(name)s sent on %(date)s UTC (it is not on '
                 'LinkedIn\'s Sent list) — back in the queue, not counted as invited',
                 name=prospect.name, date=fields.Datetime.to_string(invited_on)[:16])
        self.env['li.event']._log('error', 'connection', persona=prospect.persona_id, prospect=prospect,
                                  detail=line, prospect_body=line)
        # is it this person (LinkedIn wants their email address, a special dialog) or the account?
        outcome, shown = self._bg_diagnose_invite(profile, prospect)
        if outcome == 'weekly_limit':
            self._weekly_limit_reached(profile, shown)
            return
        if outcome == 'email_required':
            prospect._flag_check(_('LinkedIn asks for this person\'s email address to connect: it cannot be sent '
                                   'automatically. Invite them by hand, or skip them.'))
            return                                  # about the person: the account is fine
        if attempts >= INVITE_PERSON_TRIES:
            prospect._flag_check(_('LinkedIn did not record %(n)s invitations to this person, while others go '
                                   'through. Invite them by hand on LinkedIn, or skip them. LinkedIn showed: %(shown)s',
                                   n=attempts, shown=shown or _('nothing unusual')))
        profile = profile.sudo()
        count = profile.invites_not_recorded
        if profile.invite_refused_prospect_id != prospect:
            count += 1
        profile.write({'invites_not_recorded': count, 'invite_refused_prospect_id': prospect.id})
        if count >= INVITES_REFUSED_AFTER:          # different people in a row: the account
            self._bg_pause_invites(profile)

    def _bg_diagnose_invite(self, profile, prospect):
        """Open that person's invite dialog without sending and say what LinkedIn
        asks there. Returns (outcome, text shown): email_required, weekly_limit or
        unknown. The text is kept with the action for a person to read."""
        if self._bg_budget_left(profile) < 1:
            return 'unknown', ''
        data, kind, _text = self._bg_call(profile, 'check_invite_dialog',
                                          {'linkedin_username': prospect.linkedin_username}, 'invite_check',
                                          reads=1, prospect=prospect)
        if kind:
            return 'unknown', ''
        shown = ((data or {}).get('text') or '').strip()
        self._bg_note_action(profile, prospect, 'invite_check', _(
            'Invite dialog: %(status)s. LinkedIn shows: %(text)s', status=(data or {}).get('status') or '?',
            text=shown or '-'))
        if (data or {}).get('status') == 'email_required':
            return 'email_required', shown
        if is_weekly_limit(shown):
            return 'weekly_limit', shown
        return 'unknown', shown[:300]

    def _bg_use_click_to_send(self, profile, data):
        """LinkedIn's "Press Enter to Send" hides the Send button the engine
        clicks: switch the account to "Click Send to send" (use_click_to_send, an
        Odoo tool added to the engine; it types and sends nothing). True when done."""
        url = (data or {}).get('url') or ''
        result, kind, text = self._bg_call(profile, 'use_click_to_send', {'url': url} if url else {}, 'message')
        if kind is None and (result or {}).get('status') == 'click_to_send':
            profile.sudo().message_post(
                body=_('LinkedIn was set to "Press Enter to Send"; the engine switched it to "Click Send to send" '
                       'and sends the queued messages again.'),
                author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
            return True
        profile.sudo().message_post(
            body=_('The engine could not switch LinkedIn to "Click Send to send" (%(status)s): %(detail)s',
                   status=(result or {}).get('status') or kind or '-',
                   detail=((result or {}).get('message') or text or '-')[:500]),
            author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        return False

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
        # closed people stay on the list: reading the inbox costs nothing more, and their thread is
        # opened only when its row on the inbox page changed (they wrote again)
        closed = self.sudo()._closed_prospects(profile, limit=CLOSED_PER_INBOX)
        return tracked | invited | closed

    def _bg_inbox(self, profile, deadline):
        minutes = self._bg_inbox_minutes(profile)
        if profile.last_inbox_check and utc_now() - profile.last_inbox_check < timedelta(minutes=minutes):
            return 0
        followup = self.env['li.followup.agent']._get()
        activity = self.env['li.activity.agent']._get()
        if not (any(p.chat_agent_id.state == 'running' for p in profile.persona_ids)
                or followup.state == 'running' or activity.state == 'running'
                or any(p.connection_agent_id.state == 'running' for p in profile.persona_ids)):
            return 0
        candidates = self._bg_inbox_candidates(profile)
        if not candidates or self._bg_routine_left(profile) < 1:
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
        """Open the changed threads: conversations in progress first, then new
        connections, then closed people; at most li_sales.threads_per_run per
        run, so a backlog (the first sync of a profile) is spread over runs."""
        limit = max(self._param('threads_per_run', THREADS_PER_RUN), 1)
        prospects = self.env['li.prospect'].sudo().search([('linkedin_profile_id', '=', profile.id),
                                                           ('thread_check_needed', '=', True)])
        prospects = prospects.sorted(lambda p: (THREAD_PRIORITY.get(p.stage, 2), p.write_date, p.id))[:limit]
        calls = 0
        for prospect in prospects:
            if not self._bg_time_for(deadline) or self._bg_routine_left(profile) < 1:
                break
            self._bg_read_thread(profile, prospect)
            calls += 1
            self._bg_commit()
            if profile.connection_state != 'connected' or (profile.bg_paused_until
                                                             and profile.bg_paused_until > utc_now()):
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
        if kind:
            no_thread = kind == 'other' and any(h in text.lower() for h in NO_THREAD_HINTS)
            if no_thread and prospect.message_ids_li:
                # LinkedIn says there is no conversation, but Odoo holds messages with this person: the lookup
                # missed it. Never treat that as an empty conversation (a text would go out blind).
                no_thread = False
                if reread:
                    prospect._flag_check(_(
                        'LinkedIn found no conversation with %(name)s, but Odoo has %(count)s message(s) with them. '
                        'Nothing was sent: open the conversation in LinkedIn, then clear the check.',
                        name=prospect.name, count=len(prospect.message_ids_li)))
            # a busy or stopped engine ('refused') reached nothing: it does not count as a try
            tries = prospect.thread_read_tries + (kind != 'refused')
            if no_thread or kind == 'not_found' or tries >= THREAD_READ_TRIES:
                prospect.write({'thread_check_needed': False, 'last_thread_read': utc_now(), 'thread_read_tries': 0})
            else:
                prospect.write({'thread_read_tries': tries})    # still marked as changed: the next run reads again
            return no_thread
        prospect.write({'thread_check_needed': False, 'last_thread_read': utc_now(), 'thread_read_tries': 0})
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
            if kind in STOP_KINDS:
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
            if not self._bg_time_for(deadline) or self._bg_routine_left(profile) < 1:
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
        if not invited or self._bg_routine_left(profile) < 1:
            return 0, False
        data, kind, _text = self._bg_call(profile, 'get_recent_connections', {'limit': 40}, 'acceptance', reads=1)
        if kind in STOP_KINDS:
            profile.sudo().last_connections_check = utc_now()
            return 1, True          # no more LinkedIn reads in this run
        usernames = {unquote(u).strip('/').lower() for u in (data or {}).get('usernames') or []} if not kind else set()
        profile.sudo().write({'last_connections_check': utc_now(), 'connections_list_ok': bool(usernames)})
        for prospect in invited:
            if (prospect.linkedin_username or '').lower() in usernames:
                self._accept(prospect, note=_('found among the recent connections'))
        self._bg_commit()
        return 1, False

    def _bg_locations(self, profile, deadline):
        """LinkedIn's own id of each persona location, asked once (LinkedIn's
        location suggestions, the same as typing in its "Locations" filter): the
        search then uses LinkedIn's real location filter."""
        personas = profile.persona_ids.filtered(lambda p: p.connection_agent_id.state == 'running')
        now = utc_now()
        todo = personas.location_ids.filtered(
            lambda t: not t.linkedin_geo_id and (not t.geo_lookup_date or now - t.geo_lookup_date > LOCATION_LOOKUP_EVERY))
        calls = 0
        for tag in todo[:3]:
            if not self._bg_time_for(deadline):
                break
            query = tag.geo_query or tag.name
            data, kind, text = self._bg_call(profile, 'lookup_location', {'query': query}, 'location')
            calls += 1
            if kind and 'unknown tool' in (text or '').lower():
                # the engine still runs the previous add-on tools: asked again hourly until it is restarted
                tag.sudo().write({'geo_lookup_date': now - LOCATION_LOOKUP_EVERY + timedelta(hours=1),
                                  'geo_lookup_note': _('LinkedIn filter: restart the engine to look it up')})
                break
            if kind in STOP_KINDS:
                break
            if kind:
                tag.sudo().write({'geo_lookup_date': now, 'geo_lookup_note': _('LinkedIn filter: lookup failed (%s), '
                                                                             'tried again in a week', kind)})
                continue
            candidates = (data or {}).get('candidates') or []
            pick = tag._pick_linkedin_place(candidates)
            if pick:
                tag.sudo().write({'linkedin_geo_id': str(pick['id']), 'linkedin_geo_name': pick.get('name'),
                                  'geo_lookup_date': now, 'geo_lookup_note': False})
            else:
                offered = ', '.join(c.get('name', '') for c in candidates[:4]) or _('nothing')
                tag.sudo().write({'geo_lookup_date': now, 'geo_lookup_note': _(
                    'LinkedIn filter: LinkedIn offered %(offered)s for "%(q)s"; enter the LinkedIn location ID by '
                    'hand', offered=offered, q=query)})
            self._bg_commit()
        return calls

    def _bg_search_arguments(self, persona, agent):
        """(tool, arguments) of the next people search for a persona: LinkedIn's
        Locations filter (location ids), its Title filter (one job title per
        search, in turn) and 2nd/3rd-degree people only, page after page; or the
        persona's own LinkedIn search URL."""
        url = (persona.search_url or '').strip()
        if url.startswith('https://www.linkedin.com/search/results/people/'):
            return 'search_people_filtered', {'url': url, 'page': agent.search_page % SEARCH_PAGES + 1}
        titles = [t.strip() for t in re.split(r'[,;\n]+', persona.job_titles or '') if t.strip()] or ['']
        title = titles[agent.search_page % len(titles)]
        page = (agent.search_page // len(titles)) % SEARCH_PAGES + 1
        arguments = {'keywords': ' '.join(filter(None, [title, persona.include_keywords])), 'title': title,
                     'network': ['S', 'O'], 'page': page}
        geo_ids = [t.linkedin_geo_id for t in persona.location_ids if t.linkedin_geo_id]
        if geo_ids:
            arguments['geo_ids'] = geo_ids
        return 'search_people_filtered', arguments

    def _bg_search(self, profile, deadline):
        Prospect = self.env['li.prospect']
        ctx = {'reasons': [], 'left': 1, 'sends': {profile.id: 0}}
        for persona, agent, left in self._connection_personas(profile, ctx):
            waiting = Prospect.search_count([('persona_id', '=', persona.id), ('stage', 'in', ('queued', 'screening')),
                                             ('needs_check', '=', False)])
            if waiting >= left:
                continue
            if agent.last_search_date and utc_now() - agent.last_search_date < SEARCH_COOLDOWN:
                continue
            if self._bg_budget_left(profile) < 1:
                return 0
            if persona.location_ids.filtered(lambda t: not t.linkedin_geo_id and not t.geo_lookup_date):
                continue                    # its locations are looked up first (_bg_locations)
            tool, arguments = self._bg_search_arguments(persona, agent)
            agent.sudo().last_search_date = utc_now()
            data, kind, text = self._bg_call(profile, tool, arguments, 'search', reads=1, persona=persona)
            if kind and 'unknown tool' in (text or '').lower():
                # engine not restarted since the update: its plain search (LinkedIn ignores a location word,
                # so every result still passes the persona check before it is queued)
                arguments = {'keywords': arguments.get('keywords') or ''}
                data, kind, text = self._bg_call(profile, 'search_people', arguments, 'search', reads=1,
                                                 persona=persona)
            if kind:
                return 1
            own = (profile.linkedin_url or '').rstrip('/').rsplit('/', 1)[-1].lower()
            people = parse_search_results(data, own_username=own)
            counts = self._add_people(persona, people)
            self._bg_last_action(profile).detail = \
                _('%(found)s found: %(created)s queued, %(outside)s outside the persona, %(dup)s duplicates, '
                  '%(other)s skipped', found=len(people), created=counts['created'],
                  outside=counts['outside_target'], dup=counts['duplicates'],
                  other=counts['contacted_elsewhere'] + counts['do_not_contact'] + counts['excluded']
                  + counts['invalid']) + ''.join('\n- %s' % r for r in counts['outside_reasons'])
            return 1
        return 0
