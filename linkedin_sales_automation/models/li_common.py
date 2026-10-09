"""Small helpers shared by the models and the MCP tools."""
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odoo import fields

AGENT_STATES = [
    ('stopped', 'Stopped'),
    ('running', 'Running'),
    ('paused', 'Paused'),
]

PROSPECT_STAGES = [
    ('queued', 'Queued'),
    ('invited', 'Invited'),
    ('followed', 'Followed (no Connect)'),
    ('accepted', 'Accepted'),
    ('messaged', 'Messaged'),
    ('replied', 'Replied'),
    ('warm', 'Warm lead'),
    ('meeting', 'Meeting'),
    ('not_interested', 'Closed (not interested)'),
    ('no_response', 'Closed (no response)'),
    ('withdrawn', 'Withdrawn'),
    ('do_not_contact', 'Do not contact'),
]
CLOSED_STAGES = ('not_interested', 'no_response', 'withdrawn', 'do_not_contact')

EVENT_TYPES = [
    ('invite_sent', 'Invite sent'),
    ('invite_accepted', 'Invite accepted'),
    ('invite_withdrawn', 'Invite withdrawn'),
    ('followed', 'Followed (no Connect)'),
    ('message_sent', 'Message sent'),
    ('reply_received', 'Reply received'),
    ('warm_lead', 'Warm lead'),
    ('meeting_booked', 'Meeting booked'),
    ('followup_sent', 'Follow-up sent'),
    ('taken_over', 'Taken over'),
    ('reply_activity_created', 'Reply activity created'),
    ('reply_activity_done', 'Reply activity done'),
    ('reply_activity_overdue', 'Reply activity overdue'),
    ('agent_started', 'Agent started'),
    ('agent_paused', 'Agent paused'),
    ('agent_stopped', 'Agent stopped'),
    ('error', 'Error'),
]

AGENT_TYPES = [
    ('connection', 'Connection Agent'),
    ('chat', 'Chat Agent'),
    ('followup', 'Follow-up Agent'),
    ('activity', 'Activity Agent'),
    ('system', 'System'),
]

WORK_TYPES = [
    ('verify_account', 'Verify account'),
    ('check_inbox', 'Check inbox'),
    ('analyse', 'Analyse'),
    ('handoff', 'Handoff'),
    ('message', 'Message'),
    ('followup', 'Follow-up'),
    ('check_acceptance', 'Check acceptance'),
    ('invite', 'Invite'),
    ('search_prospects', 'Search prospects'),
    ('post_draft', 'Post draft'),
    ('publish_post', 'Publish post'),
    ('post_stats', 'Post stats'),
]
SEND_TYPES = ('invite', 'message', 'followup', 'handoff')

NOTE_MAX_CHARS = 200
PLACEHOLDER_RE = re.compile(r'\{\s*(first_name|company|service|name|title|meeting_link|[a-z_]+)\s*\}')


def utc_now():
    """Naive UTC datetime, the format Odoo stores (freezegun friendly)."""
    return fields.Datetime.now()


def safe_zone(tz_name):
    try:
        return ZoneInfo(tz_name or 'UTC')
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def to_local(dt_utc, tz_name):
    """Naive UTC datetime -> aware datetime in tz_name."""
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(safe_zone(tz_name))


def local_now(tz_name):
    return to_local(utc_now(), tz_name)


def float_hour(dt_local):
    return dt_local.hour + dt_local.minute / 60.0 + dt_local.second / 3600.0


def in_window(dt_local, hour_from, hour_to):
    """True when the local time is inside [from, to). to <= from never matches,
    except the full day 0–24."""
    h = float_hour(dt_local)
    if hour_from <= 0 and hour_to >= 24:
        return True
    return hour_from <= h < hour_to


def format_hour(value):
    value = value or 0.0
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    return '%02d:%02d' % (hours, minutes)


def iso_utc(dt):
    return dt.replace(microsecond=0).isoformat() + 'Z' if dt else None


def normalize_connector(name):
    """Compare connector names ignoring case, extra spaces and dash style."""
    name = unicodedata.normalize('NFKC', name or '')
    name = re.sub(r'[‐-―−]', '-', name)
    name = re.sub(r'\s+', ' ', name).strip().casefold()
    return name


def normalize_text(text):
    text = unicodedata.normalize('NFKC', text or '')
    return re.sub(r'\s+', ' ', text).strip().casefold()


_IN_RE = re.compile(r'linkedin\.com/in/([^/?#\s]+)', re.I)


def linkedin_username(url_or_username):
    """Return the public username ('ali-raza') from a profile URL or a bare username."""
    value = (url_or_username or '').strip()
    if not value:
        return ''
    match = _IN_RE.search(value)
    if match:
        value = match.group(1)
    elif '/' in value or ' ' in value:
        return ''
    return value.strip('/').lower()


def normalize_profile_url(url, username=None):
    user = linkedin_username(url) or linkedin_username(username)
    if user:
        return 'https://www.linkedin.com/in/%s/' % user
    return (url or '').strip()


def unfilled_placeholders(text):
    return sorted(set(PLACEHOLDER_RE.findall(text or '')))


_TRAILING_PUNCT = '.!?…,;:-–—~ '


def normalize_message(text):
    """Text key used to recognise the same LinkedIn message: NFKC, emoji and
    symbols removed, spaces collapsed, trailing punctuation dropped, casefolded."""
    text = unicodedata.normalize('NFKC', text or '')
    kept = []
    for char in text:
        cat = unicodedata.category(char)
        if cat in ('So', 'Sk', 'Cs', 'Co') or char in '‍︎️':
            continue
        kept.append(char)
    text = re.sub(r'\s+', ' ', ''.join(kept)).strip()
    text = text.rstrip(_TRAILING_PUNCT)
    return text.casefold()


def normalize_name(name):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', name or '')).strip().casefold()


_BREAKS_RE = re.compile(r'\s*[\x00-\x1f\x7f]+\s*')


def one_paragraph(text):
    """The engine sends messages as one line (it refuses line breaks, tabs and
    other control characters, so nothing can press Enter in LinkedIn's message
    box): every break becomes a single space."""
    return re.sub(r' {2,}', ' ', _BREAKS_RE.sub(' ', text or '')).strip()


# The same working order in one line: tool descriptions, tool answers, li_overview, prompts.
WRITE_ORDER = ('For each person, in this order: (1) read who they are in prospect.profile (role, company, about, '
               'experience); (2) read their last reply and judge its nature (interested, curious, neutral, busy, '
               'sceptical, objection, question, not interested); (3) only then analyse or write, so the text fits '
               'their real role and what they said and moves toward the objective of the step.')
