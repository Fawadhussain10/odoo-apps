"""Reading the LinkedIn engine's answers (pure functions, no Odoo).

The engine returns the text of LinkedIn pages plus typed links
("references"). Its browser always runs in en-US, so the English labels used
below are the ones LinkedIn shows. Profile URLs and thread ids come from the
links, never from guessed text.
"""
import hashlib
import json
import re

from .li_common import linkedin_username, normalize_name

# ---------------------------------------------------------------------------
# Results and outcomes
# ---------------------------------------------------------------------------
# Wording of the engine (4.26.2) when it has no working LinkedIn session. Without a
# session it does not fail: it opens its own login window and answers "A LinkedIn
# login window is open and login is still in progress ..." (seen in the real check).
SESSION_HINTS = ('session expired', 'authentication failed', 'run with --login', 'login required',
                 'not authenticated', 'needs this client to log in', 'log in again', 'sign in again',
                 'login window is open', 'login is still in progress', 'login browser window',
                 'no usable session', 'cannot sign in by itself', 'session stopped working',
                 'no linkedin source session', 'source session metadata', 'auth_required')
RESTRICTED_HINTS = ('restricted access to this account', 'account restricted', 'identity verification')
WEEKLY_LIMIT_HINTS = ('weekly invitation limit', 'weekly limit', 'reached the limit for invitations',
                      'invitation limit', 'too many invitations', 'too many pending invitations')
NOT_FOUND_HINTS = ('profile not found', 'page not found', "this page doesn't exist", 'this profile is not available')
TIMEOUT_HINTS = ('timed out', 'timeout', 'deadline')
RATE_LIMIT_RE = re.compile(r'rate limit detected\. wait (\d+) seconds', re.I)


def result_text(result):
    return ' '.join(c.get('text', '') for c in (result or {}).get('content', []) if c.get('type') == 'text')


def result_data(result):
    """The structured answer of a tool call (dict), from structuredContent or the JSON text."""
    data = (result or {}).get('structuredContent')
    if isinstance(data, dict):
        return data.get('result') if set(data) == {'result'} and isinstance(data.get('result'), dict) else data
    try:
        data = json.loads(result_text(result))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def error_kind(text):
    """Classify an engine error text: session, restricted, rate_limit, not_found,
    timeout or other. Returns (kind, wait_seconds)."""
    lowered = (text or '').lower()
    if any(h in lowered for h in RESTRICTED_HINTS):
        return 'restricted', 0
    if any(h in lowered for h in SESSION_HINTS):
        return 'session', 0
    match = RATE_LIMIT_RE.search(lowered)
    if match or 'rate limit' in lowered:
        return 'rate_limit', int(match.group(1)) if match else 300
    if any(h in lowered for h in NOT_FOUND_HINTS):
        return 'not_found', 0
    if any(h in lowered for h in TIMEOUT_HINTS):
        return 'timeout', 0
    return 'other', 0


# LinkedIn's page for accounts it suspects of automation ("We noticed some unusual
# activity on your account ... accessed a high volume of LinkedIn profile data").
WARNING_HINTS = ('noticed some unusual activity on your account', 'high volume of linkedin profile data',
                 'accessed a high volume of linkedin')


def is_account_warning(text):
    lowered = (text or '').lower()
    return any(h in lowered for h in WARNING_HINTS)


def is_weekly_limit(text):
    lowered = (text or '').lower()
    return any(h in lowered for h in WEEKLY_LIMIT_HINTS)


# Engine status of connect_with_person -> status reported to Odoo's send logic
CONNECT_STATUS = {
    'connected': 'sent',            # the invitation was submitted now
    'pending': 'pending',           # an invitation was already outstanding
    'already_connected': 'already_connected',
    'accepted': 'already_connected',    # an incoming invitation was accepted
    'custom_note_limit_reached': 'custom_note_limit_reached',
    'note_not_supported': 'custom_note_limit_reached',
    'follow_only': 'not_invitable',
    'connect_unavailable': 'not_invitable',
    'unavailable': 'failed',        # the profile page could not be read: nothing sent
    'send_failed': 'failed',
    'outcome_unknown': 'unknown',
    'maybe_sent': 'unknown',        # Connect was pressed, nothing shows the result
    'followed': 'followed',            # set by Odoo after follow_person
}


def connect_outcome(data):
    """(status, retry_safe, detail) for a connect_with_person answer."""
    raw = (data.get('status') or '').strip().lower()
    detail = data.get('message') or raw
    if is_weekly_limit(detail):
        return 'weekly_invite_limit', True, detail
    status = CONNECT_STATUS.get(raw, 'failed')
    if status == 'unknown':
        return 'unknown', False, detail
    return status, True, detail


def message_outcome(data):
    """(status, retry_safe, detail) for a send_message answer (confirm_send true)."""
    raw = (data.get('status') or '').strip().lower()
    detail = data.get('message') or raw
    if data.get('sent') is True:
        return 'sent', False, detail
    if raw == 'outcome_unknown' or data.get('retry_safe') is False:
        return 'unknown', False, detail
    if raw == 'enter_to_send_enabled':
        return 'enter_to_send', True, detail
    return 'failed', True, detail


# ---------------------------------------------------------------------------
# People search
# ---------------------------------------------------------------------------
_DEGREE_RE = re.compile(r'^\W*(1st|2nd|3rd\+?)(\W|$)', re.I)
_NOISE_LINES = {'connect', 'message', 'follow', 'following', 'pending', 'view profile', 'status is offline',
                'status is online', 'premium', 'verified', 'open to work', 'hiring', 'save', 'more',
                'see open roles'}
# LinkedIn's own lines between search results: hiring badges and Sales Navigator / Premium offers
_NOISE_RE = re.compile(r'^(view .{1,80}profile|.{0,40}mutual connections?|.{0,40}followers?|'
                       r'current:|past:|summary:|skills:|provides services|degree connection|'
                       r'see (open roles|jobs)|prioriti[sz]e the right prospects|(try|get|unlock|upgrade to) sales navigator|'
                       r'try premium|reactivate premium|.{0,40}\bpremium for\b|'
                       r'\d+(st|nd|rd|th) degree connection|\(?(he|she|they)/(him|her|them)\)?)', re.I)


def _ref_username(url):
    """Username of a person link; the engine gives paths like /in/ali-raza/."""
    url = (url or '').strip()
    if url.startswith('/'):
        url = 'https://www.linkedin.com' + url
    return linkedin_username(url)


def _clean_lines(text):
    return [line.strip() for line in (text or '').splitlines() if line.strip()]


def _is_noise(line, name_key):
    key = normalize_name(line)
    if key in _NOISE_LINES or key == name_key or _DEGREE_RE.match(line) or _NOISE_RE.match(line):
        return True
    return key.startswith(name_key + ' ') and len(key) - len(name_key) < 25   # "Jane Doe • 2nd"


def parse_search_results(data, own_username=''):
    """People of a search_people answer: [{name, linkedin_url, username, headline, location}].

    The profile link and the name come from the result links; headline and
    location are the first two meaningful lines after the name in the page text."""
    references = (data.get('references') or {}).get('search_results') or []
    lines = _clean_lines((data.get('sections') or {}).get('search_results', ''))
    # the name of the next person is never this person's headline or place ("Sara Eid • 2nd")
    names = {normalize_name(re.sub(r'^view\s+|[’\']s?\s+profile$', '', (r.get('text') or '').strip(), flags=re.I))
             for r in references if r.get('kind') == 'person'} - {''}
    people, seen = [], set()
    for ref in references:
        if ref.get('kind') != 'person':
            continue
        username = _ref_username(ref.get('url'))
        name = re.sub(r'^view\s+|[’\']s?\s+profile$', '', (ref.get('text') or '').strip(), flags=re.I).strip()
        if not username or not name or username in seen or username == own_username:
            continue
        seen.add(username)
        headline = location = ''
        name_key = normalize_name(name)
        start = next((i for i, line in enumerate(lines) if normalize_name(line).startswith(name_key)), None)
        if start is not None:
            details = []
            for line in lines[start + 1:start + 12]:
                if normalize_name(line).startswith(name_key) and details:
                    break
                key = normalize_name(line)
                if any(key == other or key.startswith(other + ' ') for other in names - {name_key}):
                    break
                if not _is_noise(line, name_key):
                    details.append(line)
                if len(details) == 2:
                    break
            headline = details[0] if details else ''
            location = details[1] if len(details) > 1 else ''
        people.append({'name': name, 'username': username,
                       'linkedin_url': 'https://www.linkedin.com/in/%s/' % username,
                       'headline': headline[:250], 'location': location[:120]})
    return people


def connected_usernames(data):
    """Usernames found by a 1st-degree people search."""
    references = (data.get('references') or {}).get('search_results') or []
    return {_ref_username(r.get('url')) for r in references if r.get('kind') == 'person'} - {''}


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------
def inbox_threads(data):
    """{normalised participant name: thread id} from the inbox links."""
    threads = {}
    for ref in (data.get('references') or {}).get('inbox') or []:
        match = re.search(r'/messaging/thread/([^/]+)/', ref.get('url') or '')
        if ref.get('kind') == 'conversation' and match and ref.get('text'):
            threads.setdefault(normalize_name(ref['text']), match.group(1))
    return threads


def inbox_preview(data, name):
    """Hash of the inbox row of `name` (the name line and the next three lines),
    or '' when the person has no row. A changed hash means a changed thread."""
    lines = _clean_lines((data.get('sections') or {}).get('inbox', ''))
    key = normalize_name(name)
    for index, line in enumerate(lines):
        if normalize_name(line) == key:
            row = '\n'.join(lines[index:index + 4])
            return hashlib.sha1(row.encode()).hexdigest()[:16]
    return ''


# ---------------------------------------------------------------------------
# Conversation thread
# ---------------------------------------------------------------------------
_GROUP_RE = re.compile(r'^(?P<name>.+?) sent the following (?:messages?|attachments?) at (?P<time>.+)$', re.I)
_LINK_RE = re.compile(r'https?://|www\.|\b[a-z0-9-]+\.(com|io|net|org|co|me|app)(/|\b)', re.I)
_TIME_RE = re.compile(r'^\d{1,2}:\d{2}\s*(AM|PM)?$', re.I)
_DATE_RE = re.compile(r'^(today|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
                      r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}(, \d{4})?)$', re.I)
_THREAD_NOISE_RE = re.compile(
    r'^(view .{1,80}profile|seen by .*|\(edited\)|reacted .*|'
    r'more options|open the options list.*|\(?(he|she|they)/(him|her|them)\)?|'
    r'.{1,80} is typing.*|load more messages?|this message has been deleted\.?|'
    r'.{1,80} • \d{1,2}:\d{2}\s*(am|pm)?)$', re.I)
# Words LinkedIn prints around messages (delivery marks, button labels) that a
# person can also send as a whole message. The text alone cannot tell: where
# the line stands does (see _settle_group).
_AMBIGUOUS_WORDS = {'sent', 'delivered', 'read', 'edited', 'react', 'reply', 'attachment', 'you'}
_DELIVERY_MARKS = {'sent', 'delivered', 'read'}        # LinkedIn shows them under our own messages only
# LinkedIn's own interface text around a conversation: the online-status banner,
# the message box and its buttons. Never a message.
_THREAD_UI_RE = re.compile(
    r'^(your online status is .*|you can change this in your settings\.?( manage)?|manage|dismiss|'
    r'write a message.*|press enter to send.*|click send to send.*|send|open send options|'
    r'maximize compose field|minimize compose field|attach (an image|a file|media).*|'
    r'open (emoji|gif) keyboard|record a voice message|show more quick repl.*)$', re.I)
# Quick-reply suggestion: an accessibility line 'Reply to conversation with "Thanks"'
# next to the button text itself ("Thanks"). Suggested to the account owner, never sent.
_SUGGESTION_RE = re.compile(r'^reply to conversation with\s*["\u201c\u2018\'](?P<text>.*?)["\u201d\u2019\']?\s*$', re.I)


def is_thread_ui_text(line):
    """LinkedIn interface text that must never be stored as a message."""
    line = (line or '').strip()
    return bool(_THREAD_UI_RE.match(line) or _SUGGESTION_RE.match(line))


def _drop_suggestions(lines):
    """Remove quick-reply suggestions: each accessibility line and the button
    text right before or after it."""
    drop = set()
    for index, line in enumerate(lines):
        match = _SUGGESTION_RE.match(line)
        if not match:
            continue
        drop.add(index)
        wanted = normalize_name(match.group('text').rstrip('.\u2026 '))
        for near in (index + 1, index - 1):
            if 0 <= near < len(lines) and near not in drop and wanted:
                key = normalize_name(lines[near])
                if key == wanted or (match.group('text').rstrip().endswith(('\u2026', '...')) and key.startswith(wanted)):
                    drop.add(near)
                    break
    return [line for index, line in enumerate(lines) if index not in drop]


# A file shared in the chat shows as three lines: its name, its size and "Download".
ATTACHMENT_PREFIX = '[Attachment] '
_FILE_SIZE_RE = re.compile(r'^\d+(?:[.,]\d+)?\s?(?:bytes?|kb|mb|gb)$', re.I)
_FILE_NAME_RE = re.compile(r'^.{1,200}\.[A-Za-z0-9]{2,5}$')


def is_attachment_text(text):
    return (text or '').startswith(ATTACHMENT_PREFIX)


def attachment_run(texts):
    """How many of the first lines of `texts` are one shared file (3: name, size,
    Download; 2: name, Download; 0: not a file), and the single line to keep."""
    first = (texts[0] if texts else '').strip()
    if not first or is_attachment_text(first):
        return 0, ''
    second = (texts[1] if len(texts) > 1 else '').strip()
    third = (texts[2] if len(texts) > 2 else '').strip()
    if _FILE_SIZE_RE.match(second) and third.lower() == 'download':
        return 3, '%s%s (%s)' % (ATTACHMENT_PREFIX, first, second)
    if second.lower() == 'download' and _FILE_NAME_RE.match(first):
        return 2, ATTACHMENT_PREFIX + first
    return 0, ''


def _merge_attachments(messages):
    """A shared file becomes one message "[Attachment] name (size)" instead of
    three lines read as three messages."""
    merged, index = [], 0
    while index < len(messages):
        same = [m for m in messages[index:index + 3] if m['sender_name'] == messages[index]['sender_name']]
        count, text = attachment_run([m['text'] for m in same])
        if count:
            merged.append(dict(messages[index], text=text))
            index += count
        else:
            merged.append(messages[index])
            index += 1
    return merged


def _name_time(line, names):
    """'Jane Doe  4:10 PM' or 'Jane Doe' -> the matching known name key, else None."""
    head = re.sub(r'\s+\d{1,2}:\d{2}\s*(AM|PM)?$', '', line, flags=re.I).strip()
    key = normalize_name(head)
    return key if key in names else None


def parse_thread(text, my_name, other_name):
    """Messages of a conversation page text, oldest first: [{sender_name, text}].

    LinkedIn starts every message group with a line "<Name> sent the following
    message(s) at <time>"; without those lines a line holding a known name
    starts a group. Each remaining line is one message: messages sent by Odoo
    are always one line, and a reply spread over lines is kept line by line so
    the same thread reads the same way every time.
    Returns None when no message group can be recognised."""
    lines = _drop_suggestions(_clean_lines(text))
    mine, other = normalize_name(my_name), normalize_name(other_name)
    names = {mine: my_name, other: other_name}
    names.pop('', None)
    has_groups = any(_GROUP_RE.match(line) for line in lines)
    messages, sender, groups, group = [], None, 0, []

    def settle():
        messages.extend(_settle_group(sender, group, mine))
        del group[:]

    for line in lines:
        match = _GROUP_RE.match(line)
        if match:
            settle()
            sender, groups = match.group('name').strip(), groups + 1
            continue
        known = _name_time(line, names)
        if known:
            if not has_groups:
                settle()
                sender, groups = names[known], groups + 1
            continue                      # the name above a group, never a message
        if (sender is None or _TIME_RE.match(line) or _DATE_RE.match(line) or _THREAD_NOISE_RE.match(line)
                or _THREAD_UI_RE.match(line)):
            continue
        group.append(line)
    settle()
    return _merge_attachments(messages) if groups else None


def _settle_group(sender, lines, mine):
    """The messages of one group. A line that is only "Sent", "Read", "Reply",
    "You" ... is LinkedIn's own text when it stands beside real messages of the
    group. It is a message when nothing else can be: a group always holds at
    least one message, so a group with nothing but that one word is the person
    writing it; and delivery marks (Sent, Delivered, Read) only ever stand under
    our own messages, so in the other person's group they are their words."""
    theirs = normalize_name(sender) != mine
    plain = [line for line in lines if normalize_name(line) not in _AMBIGUOUS_WORDS]
    doubtful = [line for line in lines if normalize_name(line) in _AMBIGUOUS_WORDS]
    messages, after_link = [], False
    for line in lines:
        key = normalize_name(line)
        if key in _AMBIGUOUS_WORDS and not ((theirs and key in _DELIVERY_MARKS)
                                             or (not plain and len(doubtful) == 1)):
            continue
        message = {'sender_name': sender, 'text': line}
        if after_link:
            message['after_link'] = True
        messages.append(message)
        after_link = after_link or bool(_LINK_RE.search(line))
    return messages


_JOB_WORDS = re.compile(
    r'\b(ceo|cto|cfo|coo|founder|co-?founder|owner|director|manager|head|lead|chief|officer|president|partner|'
    r'consultant|developer|engineer|architect|analyst|specialist|expert|executive|accountant|designer|trainer|'
    r'freelancer|student|intern|odoo|erp|helping|we|i)\b', re.I)


def looks_like_headline(text):
    """True when a text reads like a job headline rather than a place."""
    text = (text or '').strip()
    if not text:
        return False
    return bool(len(text) > 70 or re.search(r'\s(at|@)\s|[|@*™]', text, re.I) or _JOB_WORDS.search(text))


def split_headline(headline):
    """(title, company) from a LinkedIn headline: "CEO at Odoo Concepts",
    "MD @ HLC Solutions | Odoo", "Founder & CEO, AV ASCENT | ...". Only the first
    part of a long headline is used; company is '' when none is named."""
    text = re.sub(r'\s{2,}(?=\*)', ' | ', headline or '')         # "… Enterprises  **Odoo Developer"
    text = re.sub(r'\s+', ' ', re.sub(r'[*“”"]', '', text)).strip()
    first = re.split(r'\s*[|•·]\s*', text)[0].strip()
    if not first:
        return '', ''
    match = re.match(r'^(?P<title>.+?)\s*(?:\bat\b|@)\s*(?P<company>.+)$', first, re.I)
    if not match:
        match = re.match(r'^(?P<title>[^,]{2,60}),\s*(?P<company>[^,]{2,60})$', first)
    if match:
        return match.group('title').strip(' -–,')[:120], match.group('company').strip(' -–,.')[:120]
    return first[:120], ''


def profile_top_fields(text, name=''):
    """(headline, location) from the top of a profile page text: the lines
    between the person's name and "Contact info"."""
    lines = [l.strip() for l in (text or '').splitlines() if l.strip()]
    key = normalize_name(name)
    start = next((i for i, l in enumerate(lines[:12]) if key and normalize_name(l) == key), -1)
    end = next((i for i, l in enumerate(lines[:30]) if l.lower().lstrip('·• ') == 'contact info'), None)
    if end is None:
        return '', ''
    top = [l for l in lines[start + 1:end]
           if l.strip('·• ') and not _DEGREE_RE.match(l.lstrip('·• ')) and not re.match(r'^\(?(he|she|they)/', l, re.I)]
    if not top:
        return '', ''
    if len(top) == 1:
        return (top[0], '') if looks_like_headline(top[0]) else ('', top[0])
    return ' '.join(top[:-1])[:250], top[-1][:120]


# Headings that end the top card of a profile page (LinkedIn in English).
_TOP_CARD_END = {'about', 'activity', 'highlights', 'experience', 'featured', 'services', 'education',
                 'analytics', 'suggested for you', 'more profiles for you', 'people you may know',
                 'people also viewed', 'sales insights'}


def top_card_state(text):
    """What the buttons at the top of a profile say, from its page text:
    'pending' (an invitation is outstanding), 'connectable' (Connect is offered)
    or '' when neither word stands there as a button."""
    top = []
    for line in [l.strip().lower() for l in (text or '').splitlines() if l.strip()][:90]:
        if line in _TOP_CARD_END:
            break
        top.append(line)
    if 'pending' in top:
        return 'pending'
    if 'connect' in top:
        return 'connectable'
    return ''


def people_search_url(keywords, network=None, geo_ids=None, title=None, page=None):
    """LinkedIn people search address (what search_people opens); with geo_ids
    (LinkedIn location ids) and title it uses LinkedIn's Locations and Title filters."""
    from urllib.parse import urlencode
    params = {'keywords': keywords or ''}
    if geo_ids:
        params['geoUrn'] = json.dumps([str(g) for g in geo_ids])
    if network:
        params['network'] = json.dumps(list(network))
    if title:
        params['titleFreeText'] = title
    params['origin'] = 'FACETED_SEARCH' if (geo_ids or title or network) else 'GLOBAL_SEARCH_HEADER'
    if page and page > 1:
        params['page'] = page
    return 'https://www.linkedin.com/search/results/people/?' + urlencode(params)


# Labels of LinkedIn's English interface on one's own profile page.
ENGLISH_PROFILE_LABELS = ('contact info', 'connections', 'followers', 'open to', 'add profile section',
                          'enhance profile', 'resources', 'analytics', 'profile views', 'about', 'experience',
                          'education', 'activity', 'show all', 'private to you', 'more')


def interface_language(text):
    """'en' when the own-profile page shows LinkedIn's English labels, 'other'
    when a readable page shows none of them, '' when there is too little text."""
    lines = [line.strip().lower() for line in (text or '').splitlines() if line.strip()]
    if len(lines) < 3:
        return ''
    short = [line for line in lines if len(line) <= 60]
    hits = {label for label in ENGLISH_PROFILE_LABELS for line in short
            if line == label or line.startswith(label + ' ') or line.endswith(' ' + label)}
    return 'en' if len(hits) >= 2 else 'other'


_MOJIBAKE_HINT = re.compile('[\u00c2-\u00f4][\u0080-\u00bf]')


def repair_mojibake(text):
    """Undo UTF-8 text that was decoded as Latin-1 ("â\x80¢ 3rd+" -> "• 3rd+").
    Only when that reverses cleanly, so correct text is never changed."""
    if not text or not _MOJIBAKE_HINT.search(text):
        return text
    try:
        fixed = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return fixed
