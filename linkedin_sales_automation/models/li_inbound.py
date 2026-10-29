"""People outside our searches who message us (an earlier connection, someone
who found the profile): the Chat Agent answers them like any prospect who
replied. Odoo reads only the inbox list and, for such a person, the one
conversation they wrote in; never every conversation of the account.

* Answered only when the inbox row changed after the feature started (no old
  backlog) and the last message is theirs.
* Group conversations, sponsored messages and InMail offers are left alone.
* Our earlier messages in that conversation are history, never a takeover;
  only their messages after our last one wait for an answer.
* The person then follows the usual path: profile read first, reply analysed
  by Claude (nature, sentiment), then answered by Claude.
"""
import hashlib
import json
import re

from odoo import _, fields, models

from .li_common import linkedin_username, normalize_name, normalize_profile_url, utc_now
from .li_engine_parse import _clean_lines, _ref_username, parse_thread

NEW_CONTACTS_PER_RUN = 2
_SKIP_ROW_RE = re.compile(r'^(sponsored|inmail|promoted)\b', re.I)
_GROUP_NAME_RE = re.compile(r',|\band\b|\+\s*\d+', re.I)


def inbox_rows(data, threads):
    """[(name, thread_id, row_hash, last_from_them, skip)] for each inbox row
    that has a conversation link. last_from_them is False when the preview
    starts with "You:"; skip marks sponsored rows and group conversations."""
    lines = _clean_lines((data.get('sections') or {}).get('inbox', ''))
    rows = []
    for index, line in enumerate(lines):
        thread_id = threads.get(normalize_name(line))
        if not thread_id:
            continue
        row = lines[index:index + 4]
        rest = row[1:]
        ours = any(r.lower().startswith('you:') for r in rest)
        skip = bool(_GROUP_NAME_RE.search(line)) or any(_SKIP_ROW_RE.match(r) for r in rest)
        rows.append((line.strip(), thread_id, hashlib.sha1('\n'.join(row).encode()).hexdigest()[:16],
                     not ours, skip))
    return rows


class LiProfileInbound(models.Model):
    _inherit = 'li.profile'

    answer_other_messages = fields.Boolean(
        'Answer other people who message us', default=True,
        help='Someone who is not a prospect (an earlier connection, for example) writes to this account: the Chat '
             'Agent of the persona below reads their profile and their message, and Claude answers. Only new '
             'messages count, never old conversations; group chats and sponsored messages are left alone.')
    inbound_persona_id = fields.Many2one(
        'li.persona', 'Persona for other people who message us', domain="[('linkedin_profile_id', '=', id)]",
        help='Whose Chat Agent answers them. Empty: the first persona of this account with a running Chat Agent.')
    inbox_others_seen = fields.Text(readonly=True, copy=False,
                                    help='Inbox rows of people who are not prospects, as last seen (technical).')

    def _inbound_persona(self):
        self.ensure_one()
        if not self.answer_other_messages:
            return self.env['li.persona']
        if self.inbound_persona_id and self.inbound_persona_id.chat_agent_id.state == 'running':
            return self.inbound_persona_id
        if self.inbound_persona_id:
            return self.env['li.persona']       # chosen, but its Chat Agent does not run
        return self.persona_ids.filtered(lambda p: p.chat_agent_id.state == 'running')[:1]


class LiMcpInbound(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    def _bg_inbox_others(self, profile, data, deadline):
        """New messages in the inbox from people who are not prospects of this
        account. The first inbox read only notes what is there."""
        persona = profile.sudo()._inbound_persona()
        if not persona:
            return 0
        from .li_engine_parse import inbox_threads
        rows = inbox_rows(data, inbox_threads(data))
        Prospect = self.env['li.prospect'].sudo()
        known = Prospect.search([('linkedin_profile_id', '=', profile.id)])
        known_names = {normalize_name(p.name) for p in known}
        known_threads = set(known.filtered('li_thread_id').mapped('li_thread_id'))
        try:
            seen = json.loads(profile.inbox_others_seen or '{}')
        except ValueError:
            seen = {}
        started = bool(seen.get('__started'))
        calls = 0
        for name, thread_id, row_hash, last_from_them, skip in rows:
            if normalize_name(name) in known_names or thread_id in known_threads:
                continue
            if seen.get(thread_id) == row_hash:
                continue
            if started and last_from_them and not skip:
                if calls >= NEW_CONTACTS_PER_RUN or not self._bg_time_for(deadline) \
                        or self._bg_routine_left(profile) < 1:
                    continue                    # not marked as seen: taken in a later run
                calls += 1
                if not self._bg_new_contact(profile, persona, name, thread_id):
                    continue
            seen[thread_id] = row_hash
        seen['__started'] = True
        profile.sudo().inbox_others_seen = json.dumps(seen)
        return calls

    def _bg_new_contact(self, profile, persona, name, thread_id):
        """Read the conversation of someone new who wrote to us and make them a
        prospect of `persona` waiting for an answer. False when nothing was read
        (tried again later)."""
        data, kind, _text = self._bg_call(profile, 'get_conversation', {'thread_id': thread_id}, 'thread', reads=1,
                                          persona=persona)
        if kind:
            return kind not in ('refused', 'timeout', 'transport', 'rate_limit')
        own = linkedin_username(profile.linkedin_url)
        username = ''
        for ref in (data.get('references') or {}).get('conversation') or []:
            found = _ref_username(ref.get('url'))
            if not found or found == own:
                continue
            if normalize_name(ref.get('text')) == normalize_name(name) or not username:
                username = found
                if normalize_name(ref.get('text')) == normalize_name(name):
                    break
        Prospect = self.env['li.prospect'].sudo()
        others = Prospect.search([('linkedin_username', '=', username)]) if username else Prospect
        if not username or others.filtered('do_not_contact'):
            self._bg_last_action(profile).detail = _(
                '%(name)s wrote to us: %(why)s, not answered by an agent', name=name,
                why=_('no profile link in the conversation') if not username else _('on the do-not-contact list'))
            return True
        mine = others.filtered(lambda p: p.linkedin_profile_id == profile)
        if mine:                                # known under another name: read like any prospect
            mine[:1].write({'li_thread_id': thread_id, 'thread_check_needed': True})
            return True
        prospect = Prospect.create({
            'name': name, 'linkedin_url': normalize_profile_url(None, username), 'persona_id': persona.id,
            'stage': 'accepted', 'date_accepted': utc_now(), 'li_thread_id': thread_id, 'from_inbox': True,
            'fit_reason': _('Wrote to us first (not from a search)'),
        })
        prospect.message_post(body=_('%s wrote to us: added for the Chat Agent of %s, who answers after reading '
                                     'their profile and message.', name, persona.name),
                              author_id=self.env['li.event']._ai_partner().id, subtype_xmlid='mail.mt_note')
        conversation = (data.get('sections') or {}).get('conversation', '')
        messages = parse_thread(conversation, profile.my_display_name, name) or []
        prospect.write({'thread_check_needed': False, 'last_thread_read': utc_now()})
        if messages:
            self.with_context(li_history_import=True)._record_thread(profile, prospect, messages)
        self._bg_last_action(profile).detail = _('%(name)s wrote to us: added as a prospect of %(persona)s',
                                                 name=name, persona=persona.name)
        return True
