"""MCP tools of the Odoo endpoint (section 11.3).

Each tool has a fixed input schema. The controller authenticates the bearer
token and calls ``li.mcp.tools.call_tool``; every tool runs as the module's
technical user (group LinkedIn Sales / MCP Agent) through with_user().
"""
import logging

from odoo import _, api, models

from .li_common import WRITE_ORDER, iso_utc, local_now, utc_now

_logger = logging.getLogger(__name__)

READ = {'readOnlyHint': True, 'openWorldHint': False}
REPORT = {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False}

STR = {'type': 'string'}
INT = {'type': 'integer'}
BOOL = {'type': 'boolean'}

TOOLS = [
    {
        'name': 'li_overview',
        'title': 'LinkedIn agents overview',
        'description': 'LinkedIn profiles (key, name, state, execution mode), personas with agent states and '
                       'today\'s counts versus limits per agent. Use it for "how are my agents doing" questions '
                       'and to find the profile keys.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'annotations': READ,
    },
    {
        'name': 'li_get_work',
        'title': 'Get work allowed now',
        'description': 'Returns the work items allowed right now for one LinkedIn profile (daily limits, target '
                       'working days, send windows in each persona\'s time zone, delay gaps, takeover). Claude in '
                       'Chrome profiles: verify_account first, then check_inbox, analyse, handoff, message, '
                       'followup, check_acceptance, invite, search_prospects, each with browser instructions; '
                       'send items reserve their quota for 15 minutes. Built-in engine profiles: Odoo does the '
                       'LinkedIn work itself, so only writing items come back. An empty list means nothing to do now. '
                       + WRITE_ORDER,
        'inputSchema': {'type': 'object', 'properties': {
            'linkedin_profile': {'type': 'string', 'description': 'Profile key (or name) from li_overview.'},
            'max_items': {'type': 'integer', 'minimum': 1, 'maximum': 25,
                          'description': 'Default from Settings, at most 25.'},
        }, 'required': ['linkedin_profile'], 'additionalProperties': False},
        'annotations': {'readOnlyHint': False, 'destructiveHint': False, 'openWorldHint': False},
    },
    {
        'name': 'li_confirm_send',
        'title': 'Confirm a send',
        'description': 'Claude in Chrome: call right before clicking Send (invite or message). Re-checks '
                       'takeover, stage, daily limit, send window and delay gap. Send only if go is true. Pass '
                       'the exact text you will send so Odoo can validate it (note at most 200 characters, no '
                       'unfilled placeholders).',
        'inputSchema': {'type': 'object', 'properties': {
            'work_id': INT,
            'text': {'type': 'string', 'description': 'Note or message you are about to send (optional).'},
        }, 'required': ['work_id'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_report_result',
        'title': 'Report a send result',
        'description': 'Claude in Chrome: report a verify_account, invite, message, followup, handoff, '
                       'publish_post (status published + post_url, or failed) or post_stats (status ok + reactions, '
                       'comments, reposts) item. '
                       'Send statuses: sent, already_connected, pending, custom_note_limit_reached, '
                       'weekly_invite_limit, not_found, not_invitable, restricted, failed (retry_safe true only '
                       'when nothing was sent). verify_account statuses: verified (with linkedin_url), '
                       'wrong_account, not_logged_in. linkedin_profile must be the profile named in the item.',
        'inputSchema': {'type': 'object', 'properties': {
            'work_id': INT,
            'status': STR,
            'text_sent': STR,
            'note_sent': BOOL,
            'retry_safe': BOOL,
            'linkedin_profile': STR,
            'linkedin_url': {'type': 'string', 'description': 'verify_account: the address /in/me/ landed on.'},
            'post_url': {'type': 'string', 'description': 'publish_post: the address of the new post.'},
            'reactions': INT,
            'comments': INT,
            'reposts': INT,
            'error': STR,
        }, 'required': ['work_id', 'status', 'linkedin_profile'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_add_prospects',
        'title': 'Add people found by a search',
        'description': 'Claude in Chrome: report the people found for a search_prospects item. Odoo drops '
                       'duplicates and do-not-contact people and queues the rest.',
        'inputSchema': {'type': 'object', 'properties': {
            'work_id': INT,
            'linkedin_profile': STR,
            'people': {'type': 'array', 'maxItems': 100, 'items': {
                'type': 'object', 'properties': {
                    'name': STR, 'headline': STR, 'location': STR, 'linkedin_url': STR, 'username': STR,
                    'title': STR, 'company': STR,
                }, 'required': ['name']}},
        }, 'required': ['work_id', 'people'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_record_conversation',
        'title': 'Record a LinkedIn conversation',
        'description': 'Claude in Chrome: store one conversation thread read on LinkedIn (one call per thread). '
                       'Give every message in the thread, oldest first, with the sender name exactly as shown.',
        'inputSchema': {'type': 'object', 'properties': {
            'linkedin_profile': STR,
            'work_id': INT,
            'prospect_id': INT,
            'linkedin_url': STR,
            'messages': {'type': 'array', 'maxItems': 200, 'items': {
                'type': 'object', 'properties': {'sender_name': STR, 'text': STR, 'sent_at': STR},
                'required': ['sender_name', 'text']}},
        }, 'required': ['linkedin_profile', 'messages'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_mark_accepted',
        'title': 'Mark accepted invites',
        'description': 'Claude in Chrome: report which pending invites of a check_acceptance item are now '
                       '1st-degree connections.',
        'inputSchema': {'type': 'object', 'properties': {
            'work_id': INT,
            'accepted': {'type': 'array', 'items': INT, 'description': 'Prospect ids now connected.'},
            'linkedin_profile': STR,
        }, 'required': ['work_id', 'accepted'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_send_now',
        'title': 'Send connections and messages now',
        'description': 'Built-in engine profiles: when the user asks to send connections (invites) and/or messages '
                       'now. Odoo checks each persona (agent state, today\'s limit, send window, texts ready or still '
                       'to write) and starts its engine sending at once, one at a time with the delay gap, never '
                       'above the limits; every message goes out only after a fresh read of its conversation. Returns '
                       'the plan per persona. If notes, messages or analyses are still to write, do them (li_get_work '
                       '+ li_submit_text / li_record_analysis) and call again. start_agents true runs stopped or '
                       'paused agents: only when the user asked for that.',
        'inputSchema': {'type': 'object', 'properties': {
            'linkedin_profile': {'type': 'string', 'description': 'Profile key (or name) from li_overview.'},
            'persona': {'type': 'string', 'description': 'Only this persona (name or id). Default: all.'},
            'what': {'type': 'string', 'enum': ['all', 'invites', 'messages'],
                     'description': 'invites, messages (incl. follow-ups and handoffs) or all (default).'},
            'start_agents': BOOL,
        }, 'required': ['linkedin_profile'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_invite_person',
        'title': 'Invite one person',
        'description': 'When the user asks to invite (connect with) a specific LinkedIn person by link. Odoo adds '
                       'the person to a persona\'s queue (refusing the account itself, do-not-contact people and '
                       'people already invited or connected) and, for built-in engine profiles, starts sending at '
                       'once within the same limits and send window. Pass a note (at most 200 characters) when the '
                       'persona sends notes.',
        'inputSchema': {'type': 'object', 'properties': {
            'linkedin_url': {'type': 'string', 'description': 'The person\'s LinkedIn profile link.'},
            'linkedin_profile': {'type': 'string', 'description': 'Profile key; needed when there are several.'},
            'persona': {'type': 'string', 'description': 'Persona name or id; needed when there are several.'},
            'name': {'type': 'string', 'description': 'The person\'s name, if known.'},
            'note': {'type': 'string', 'description': 'Connection note, at most 200 characters.'},
        }, 'required': ['linkedin_url'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_check_inbox_now',
        'title': 'Read replies now',
        'description': 'Built-in engine profiles: when the user asks to check or answer replies now. Odoo reads the '
                       'LinkedIn inbox and the changed conversations at once (1–3 minutes); then li_get_work returns '
                       'new replies to analyse and answers to write. ' + WRITE_ORDER,
        'inputSchema': {'type': 'object', 'properties': {
            'linkedin_profile': {'type': 'string', 'description': 'Profile key (or name) from li_overview.'},
        }, 'required': ['linkedin_profile'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_sending_status',
        'title': 'Sending status',
        'description': 'Built-in engine profiles: invites and messages sent today per persona (who, when, note or text), '
                       'what is still queued, recent errors and when the engine runs next. Use it for "did it send?".',
        'inputSchema': {'type': 'object', 'properties': {
            'linkedin_profile': {'type': 'string', 'description': 'Profile key (or name) from li_overview.'},
            'persona': STR,
        }, 'required': ['linkedin_profile'], 'additionalProperties': False},
        'annotations': READ,
    },
    {
        'name': 'li_submit_text',
        'title': 'Submit a written text',
        'description': 'Built-in engine profiles: answer an invite_note, message, followup or handoff writing item '
                       'with the exact text (one paragraph). Odoo queues it and sends it itself in the send window, '
                       'after re-reading the conversation; if the conversation changed meanwhile the text is '
                       'dropped and a fresh item comes later. Before writing: ' + WRITE_ORDER,
        'inputSchema': {'type': 'object', 'properties': {
            'work_id': INT,
            'text': STR,
        }, 'required': ['work_id', 'text'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_submit_post_draft',
        'title': 'Submit a post draft',
        'description': 'Answer a post_draft item with the post text (at most 3000 characters, line breaks allowed) '
                       'and optionally a better title. A person approves it before it is published.',
        'inputSchema': {'type': 'object', 'properties': {
            'work_id': INT,
            'text': STR,
            'title': STR,
        }, 'required': ['work_id', 'text'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_record_analysis',
        'title': 'Record a conversation analysis',
        'description': 'Answer an analyse item: sentiment, answers per question step, whether the pivot '
                       'criteria are met, and a short summary. Read prospect.profile first, then the reply, and '
                       'judge the nature of the reply in the light of who the person is.',
        'inputSchema': {'type': 'object', 'properties': {
            'work_id': INT,
            'sentiment': {'type': 'string', 'enum': ['positive', 'neutral', 'negative', 'opt_out']},
            'answers': {'type': 'object', 'additionalProperties': {'type': 'string'}},
            'pivot': BOOL,
            'pivot_reason': STR,
            'summary': STR,
        }, 'required': ['work_id', 'sentiment', 'pivot', 'summary'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_report_error',
        'title': 'Report an error',
        'description': 'Claude in Chrome: report a LinkedIn error. session_expired true when LinkedIn shows a '
                       'sign-in page; restricted true when LinkedIn says the account is restricted or asks for '
                       'identity verification. Odoo pauses that profile\'s agents and tells the owner.',
        'inputSchema': {'type': 'object', 'properties': {
            'linkedin_profile': STR,
            'work_id': INT,
            'error': STR,
            'session_expired': BOOL,
            'restricted': BOOL,
        }, 'required': ['linkedin_profile', 'error'], 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_take_over',
        'title': 'Take over a prospect',
        'description': 'Manual takeover from chat ("take over Ali Raza"): every agent stops for that prospect only.',
        'inputSchema': {'type': 'object', 'properties': {
            'prospect_id': INT,
            'linkedin_url': STR,
            'name': {'type': 'string', 'description': 'Prospect name, if id and URL are unknown.'},
        }, 'additionalProperties': False},
        'annotations': REPORT,
    },
    {
        'name': 'li_finish_run',
        'title': 'Finish the run',
        'description': 'Call once li_get_work returns no items for every profile you worked on. Records the '
                       'run (shown on the dashboard), releases unused items and returns totals for your summary. '
                       'Pass the errors you met, one line each.',
        'inputSchema': {'type': 'object', 'properties': {
            'summary': STR,
            'errors': {'type': 'array', 'items': STR, 'maxItems': 50},
            'linkedin_profile': STR,
        }, 'additionalProperties': False},
        'annotations': REPORT,
    },
]
TOOLS_BY_NAME = {tool['name']: tool for tool in TOOLS}

_JSON_TYPES = {'string': str, 'integer': int, 'boolean': bool, 'array': list, 'object': dict}


class ToolError(Exception):
    """A refusal Claude can act on: returned as isError with this text."""

    def __init__(self, message, data=None):
        super().__init__(message)
        self.data = data or {}


def _check_type(value, schema, path):
    expected = schema.get('type')
    if not expected:
        return
    pytype = _JSON_TYPES[expected]
    if (expected == 'integer' and isinstance(value, bool)) or not isinstance(value, pytype):
        if not (expected == 'integer' and isinstance(value, float) and value.is_integer()):
            raise ToolError('%(path)s must be of type %(type)s' % {'path': path, 'type': expected})
    if 'enum' in schema and value not in schema['enum']:
        raise ToolError('%(path)s must be one of %(values)s' % {'path': path, 'values': ', '.join(schema['enum'])})
    if expected == 'array':
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            raise ToolError('%(path)s has more than %(n)s items' % {'path': path, 'n': schema['maxItems']})
        for index, item in enumerate(value):
            _check_type(item, schema.get('items', {}), '%s[%s]' % (path, index))
    if expected == 'object':
        validate_args(value, schema, path)


def validate_args(args, schema, path='arguments'):
    if not isinstance(args, dict):
        raise ToolError('%s must be an object' % path)
    props = schema.get('properties', {})
    for key in schema.get('required', []):
        if args.get(key) in (None, ''):
            raise ToolError('%(path)s.%(key)s is required' % {'path': path, 'key': key})
    if schema.get('additionalProperties') is False:
        unknown = set(args) - set(props)
        if unknown:
            raise ToolError('Unknown argument(s): %s' % ', '.join(sorted(unknown)))
    for key, value in args.items():
        if value is None:
            continue
        if key in props:
            _check_type(value, props[key], '%s.%s' % (path, key))
        elif isinstance(schema.get('additionalProperties'), dict):
            _check_type(value, schema['additionalProperties'], '%s.%s' % (path, key))


class LiMcpTools(models.AbstractModel):
    _name = 'li.mcp.tools'
    _description = 'LinkedIn Sales MCP tools'

    @api.model
    def list_tools(self):
        return TOOLS

    @api.model
    def call_tool(self, name, arguments):
        """Validate and run a tool. Returns the structured result (dict).
        Raises ToolError for refusals."""
        tool = TOOLS_BY_NAME.get(name)
        if not tool:
            raise ToolError(_('Unknown tool: %s', name))
        arguments = arguments or {}
        validate_args(arguments, tool['inputSchema'])
        tech_user = self.env['li.mcp.token']._technical_user()
        tools = self.with_user(tech_user).with_context(active_test=True, allowed_company_ids=tech_user.company_ids.ids)
        method = getattr(tools, '_tool_%s' % name, None)
        if method is None:
            raise ToolError(_('%s is not available yet.', name))
        return method(**arguments)

    # ------------------------------------------------------------------
    # content[0].text: a short plain summary (the JSON is in structuredContent)
    # ------------------------------------------------------------------
    SUMMARY_MAX = 400

    @api.model
    def _summarize(self, name, result):
        builder = getattr(self, '_summary_%s' % name, None)
        text = builder(result) if builder else None
        text = text or result.get('message') or 'Done.'
        text = ' '.join(str(text).split())
        return text if len(text) <= self.SUMMARY_MAX else text[:self.SUMMARY_MAX - 1] + '…'

    def _summary_li_overview(self, result):
        personas = result.get('personas', [])
        active = sum(1 for p in personas if p['status'] == 'active')
        invites = sum(p['connection_agent']['invites_today'] for p in personas)
        invite_cap = sum(p['connection_agent']['daily_limit'] for p in personas)
        messages = sum(p['chat_agent']['messages_today'] for p in personas)
        message_cap = sum(p['chat_agent']['daily_limit'] for p in personas)
        followup = result.get('followup_agent', {})
        text = '%s profiles, %s personas (%s active). Today: %s/%s invites, %s/%s messages, %s/%s follow-ups.' % (
            len(result.get('profiles', [])), len(personas), active, invites, invite_cap, messages, message_cap,
            followup.get('sent_last_24h', 0), followup.get('daily_limit', 0))
        modes = {'engine': 'built-in engine', 'chrome': 'Claude in Chrome'}
        text += ' Profiles: %s.' % '; '.join('%s (%s, %s)' % (
            p['linkedin_profile'], modes.get(p.get('execution_mode'), p.get('execution_mode')),
            p['state'].replace('_', ' ')) for p in result.get('profiles', []))
        reconnect = [p['name'] for p in result.get('profiles', []) if p['state'] == 'reconnect_needed']
        if reconnect:
            text += ' Reconnect needed: %s.' % ', '.join(reconnect)
        restricted = [p['name'] for p in result.get('profiles', []) if p['state'] == 'restricted']
        if restricted:
            text += ' Restricted: %s.' % ', '.join(restricted)
        overdue = result.get('activity_agent', {}).get('overdue_reply_activities')
        if overdue:
            text += ' %s reply activities overdue.' % overdue
        return text

    def _summary_li_get_work(self, result):
        items = result.get('items', [])
        if not items and result.get('execution_mode') == 'engine':
            return result.get('message')
        if not items:
            reasons = result.get('reasons') or []
            text = 'No work allowed right now; call li_finish_run.'
            if reasons:
                text += ' %s.' % '; '.join(reasons[:3])
            return text
        kinds = {}
        for item in items:
            kinds[item['type']] = kinds.get(item['type'], 0) + 1
        accounts = sorted({i['linkedin_profile'] for i in items})
        return '%s work item(s): %s, on %s. Do them in order.' % (
            len(items), ', '.join('%s %s' % (n, k) for k, n in kinds.items()), ', '.join(accounts))

    def _summary_li_confirm_send(self, result):
        if result.get('go'):
            return 'go'
        if result.get('reason') == 'wait':
            return 'wait %s s (delay gap): do other items first, then confirm again.' % result.get('wait_seconds')
        return 'stop: %s' % result.get('reason', '')

    def _summary_li_submit_text(self, result):
        return result.get('message')

    def _summary_li_add_prospects(self, result):
        skipped = sum(result.get(k, 0) for k in ('duplicates', 'contacted_elsewhere', 'do_not_contact', 'excluded',
                                                   'invalid'))
        return '%s prospects queued, %s skipped.' % (result.get('created', 0), skipped)

    def _summary_li_finish_run(self, result):
        parts = []
        for acc in result.get('accounts', []):
            if any(acc[k] for k in ('invites', 'accepted', 'messages', 'followups', 'replies', 'warm_leads', 'errors')):
                parts.append('%s: %s invites, %s messages, %s follow-ups, %s replies, %s warm leads, %s errors' % (
                    acc['linkedin_profile'], acc['invites'], acc['messages'], acc['followups'], acc['replies'],
                    acc['warm_leads'], acc['errors']))
        text = 'Run recorded: %s written, %s done, %s errors; %s unused item(s) released.' % (
            result.get('written', 0), result.get('done', 0), result.get('errors', 0), result.get('released_items', 0))
        return text + (' ' + '. '.join(parts) + '.' if parts else ' No activity since the last run.')

    # ------------------------------------------------------------------
    # li_overview
    # ------------------------------------------------------------------
    def _tool_li_overview(self):
        WorkItem = self.env['li.work.item']
        profiles = []
        for profile in self.env['li.profile'].search([]):
            profiles.append({
                'name': profile.name,
                'linkedin_profile': profile.account_key,
                'execution_mode': profile.execution_mode,
                'state': profile.connection_state,
                'account_type': profile.account_type,
            })
        personas = []
        for persona in self.env['li.persona'].search([]):
            con, chat = persona.connection_agent_id, persona.chat_agent_id
            now = local_now(persona.target_timezone)
            personas.append({
                'name': persona.name,
                'linkedin_profile': persona.linkedin_profile_id.name,
                'service': persona.service_id.name,
                'status': persona.state,
                'target_timezone': persona.target_timezone,
                'local_time': now.strftime('%a %H:%M'),
                'connection_agent': {'state': con.state,
                                     'invites_today': WorkItem._quota_used_today(persona, 'connection'),
                                     'daily_limit': con.daily_limit},
                'chat_agent': {'state': chat.state,
                               'messages_today': WorkItem._quota_used_today(persona, 'chat'),
                               'daily_limit': chat.daily_limit},
                'prospects': persona.prospect_count,
                'accepted': persona.accepted_count,
                'warm_leads': persona.lead_count,
                'meetings': persona.meeting_count,
            })
        followup = self.env['li.followup.agent']._get()
        activity = self.env['li.activity.agent']._get()
        overdue = self.env['li.prospect'].search_count([('reply_overdue', '=', True)])
        return {
            'profiles': profiles,
            'personas': personas,
            'followup_agent': {'state': followup.state, 'sent_last_24h': WorkItem._followup_used(),
                               'daily_limit': followup.daily_limit},
            'activity_agent': {'state': activity.state, 'overdue_reply_activities': overdue},
            'generated_at': iso_utc(utc_now()),
        }
