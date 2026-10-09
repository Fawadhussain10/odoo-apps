"""Chat Agent rules (6.2), conversation recording, analysis and pivot (6.3)."""
import json
from collections import Counter
from datetime import timedelta

from odoo import _, fields, models

from .li_common import CLOSED_STAGES, linkedin_username, normalize_message, normalize_name, utc_now
from .li_engine import BROWSER_RULES, CHAT_METHOD_CHROME, GUARDRAILS
from .li_mcp_tools import ToolError

TRACKED_STAGES = ('accepted', 'messaged', 'replied', 'warm', 'meeting')
SEND_IN_CHROME = ('In Chrome open the prospect linkedin_url and click Message; read the open thread first. If it has '
                  'a message that is not in "conversation" above, send nothing: call li_record_conversation with the '
                  'whole thread instead (Odoo plans again). Otherwise call li_confirm_send with work_id and the exact '
                  'text; only if go is true, type exactly that text and click Send; then li_report_result with '
                  'status sent and text_sent (failed with error and retry_safe if it did not go out). '
                  + BROWSER_RULES)
CHAT_STAGES = ('accepted', 'messaged', 'replied')
SELF_NAMES = {'you', 'me', 'moi', 'ich'}


def _parse_sent_at(value):
    """LinkedIn rarely gives a usable timestamp ("2h", "Mon"): only full ISO
    dates are used, anything else means "now"."""
    if not value:
        return None
    try:
        parsed = fields.Datetime.to_datetime(value.replace('T', ' ').replace('Z', '')[:19])
    except (ValueError, TypeError, AttributeError):
        return None
    return parsed


class LiMcpEngineChat(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------
    def _steps(self, persona):
        return persona.chat_agent_id.step_ids.sorted(lambda s: (s.sequence, s.id))

    def _step_number(self, prospect):
        steps = self._steps(prospect.persona_id)
        return (steps.ids.index(prospect.current_step_id.id) + 1) if prospect.current_step_id in steps else 0

    def _next_step(self, prospect):
        steps = self._steps(prospect.persona_id)
        if not prospect.current_step_id or prospect.current_step_id not in steps:
            return steps[:1]
        index = steps.ids.index(prospect.current_step_id.id)
        return steps[index + 1:index + 2]

    def _step_due(self, prospect, step, now):
        """(due, reason) for the next questionnaire step (6.2 / point 6)."""
        chat = prospect.persona_id.chat_agent_id
        wait = timedelta(days=step.wait_days or 0)
        if step.trigger == 'after_accept':
            if not prospect.current_step_id:
                if not prospect.date_accepted:
                    return False, 'not accepted yet'
                due = prospect.date_accepted + timedelta(hours=chat.first_message_delay or 0) + wait
            else:
                due = (prospect.last_outbound_date or prospect.date_accepted or now) + wait
            return now >= due, 'due at %s' % due
        # after_reply: only after a recorded, analysed reply to our last message
        if not prospect.last_inbound_date or prospect.awaiting_reply:
            return False, 'waiting for a reply'
        if prospect.needs_analysis:
            return False, 'reply not analysed yet'
        due = prospect.last_inbound_date + wait
        return now >= due, 'due at %s' % due

    def _render(self, template, prospect):
        values = {'first_name': prospect._first_name(), 'company': prospect.company or '',
                  'service': prospect.service_id.name or '', 'name': prospect.name,
                  'meeting_link': prospect.persona_id.chat_agent_id.meeting_link or ''}
        text = template or ''
        for key, value in values.items():
            if value or key == 'meeting_link':
                text = text.replace('{%s}' % key, value)
        return text

    def _step_payload(self, step, number):
        return {'number': number, 'name': step.name, 'objective': step.objective or '',
                'is_question': step.is_question, 'trigger': step.trigger}

    # ------------------------------------------------------------------
    # Generators (li_get_work order: check_inbox, analyse, handoff, message)
    # ------------------------------------------------------------------
    def _tracked_prospects(self, profile, limit=50):
        return self.env['li.prospect'].search([
            ('linkedin_profile_id', '=', profile.id), ('do_not_contact', '=', False),
            '|', ('stage', 'in', TRACKED_STAGES), ('is_taken_over', '=', True),
        ], order='last_activity_date desc', limit=limit)

    def _gen_check_inbox(self, profile, ctx):
        minutes = self._param('inbox_interval', 60)
        recent = self.env['li.work.item'].search_count([
            ('linkedin_profile_id', '=', profile.id), ('work_type', '=', 'check_inbox'),
            '|', ('state', '=', 'released'),
            '&', ('state', '=', 'done'), ('date_released', '>', utc_now() - timedelta(minutes=minutes))])
        if recent:
            return []
        followup = self.env['li.followup.agent']._get()
        activity = self.env['li.activity.agent']._get()
        if not (any(p.chat_agent_id.state == 'running' for p in profile.persona_ids)
                or followup.state == 'running' or activity.state == 'running'):
            return []
        tracked = self._tracked_prospects(profile)
        if not tracked:
            return []
        return [self._create_item('check_inbox', 'chat', profile, prospect_ids=[(6, 0, tracked.ids)], payload={
            'tracked_prospects': [dict(p._payload(), stage=p.stage) for p in tracked],
            'my_display_name': profile.my_display_name,
            'instructions': 'In Chrome open https://www.linkedin.com/messaging/ . For every tracked prospect with a '
                            'thread in the inbox (new or not), open the thread and call li_record_conversation once '
                            'per thread with prospect_id, work_id and every message of the thread, oldest first, '
                            'each with the sender name exactly as shown. Timestamps are optional. Read-only: type '
                            'and send nothing. ' + BROWSER_RULES,
        })]

    def _gen_analyse(self, profile, ctx):
        items = []
        prospects = self.env['li.prospect'].search([
            ('linkedin_profile_id', '=', profile.id), ('needs_analysis', '=', True),
            ('is_taken_over', '=', False), ('do_not_contact', '=', False),
            ('persona_id.chat_agent_id.state', '=', 'running')], order='last_inbound_date asc', limit=25)
        busy = set(self.env['li.work.item'].search([('prospect_id', 'in', prospects.ids), ('state', '=', 'released'),
                                                    ('work_type', '=', 'analyse')]).mapped('prospect_id').ids)
        for prospect in prospects:
            if ctx['left'] - len(items) <= 0:
                break
            if prospect.id in busy:
                continue
            chat = prospect.persona_id.chat_agent_id
            steps = self._steps(prospect.persona_id)
            number = self._step_number(prospect)
            remaining = [self._step_payload(s, i + 1) for i, s in enumerate(steps) if i + 1 > number and s.is_question]
            asked = [self._step_payload(s, i + 1) for i, s in enumerate(steps) if i + 1 <= number and s.is_question]
            pivot_allowed = number >= (chat.pivot_min_step or 0)
            items.append(self._create_item('analyse', 'chat', profile, prospect.persona_id, prospect, payload={
                'conversation': prospect._conversation_payload(),
                'current_step': self._step_payload(prospect.current_step_id, number) if prospect.current_step_id else None,
                'questions_asked': asked,
                'remaining_question_steps': remaining,
                'answers_so_far': prospect._answers_dict(),
                'pivot_criteria': chat.pivot_criteria or '',
                'pivot_min_step': chat.pivot_min_step or 0,
                'pivot_allowed_now': pivot_allowed,
                'instructions': 'First read who this person is in prospect.profile (role, company, about, '
                                'experience), then read the conversation and judge the nature of their last reply '
                                '(interested, curious, neutral, busy, sceptical, objection, question, not '
                                'interested) in the light of who they are; say it in the summary. Then call '
                                'li_record_analysis once: sentiment (positive, '
                                'neutral, negative, or opt_out when they ask not to be contacted), answers as '
                                '{question step name: answer} for every question answered so far, pivot true only '
                                'if the pivot criteria are met%s, a one-line pivot_reason and a 2–3 sentence '
                                'summary. Send nothing.' % ('' if pivot_allowed else
                                                            ' (pivot is not allowed before step %s)' % chat.pivot_min_step),
            }))
        return items

    def _chat_candidates(self, profile, ctx, domain):
        """Personas of the profile whose Chat Agent may send now, with quota left."""
        personas = {}
        for persona in profile.persona_ids.filtered(lambda p: p.chat_agent_id.state == 'running'):
            ok, reason = self._window(persona, persona.chat_agent_id)
            if not ok:
                ctx['reasons'].append(reason)
                continue
            left = self._quota_left(persona, 'chat')
            if left <= 0:
                self._notify_limit(persona, persona.chat_agent_id)
                ctx['reasons'].append('%s: Chat Agent daily limit (%s) reached' % (
                    persona.name, persona.chat_agent_id.daily_limit))
                continue
            personas[persona.id] = left
        if not personas:
            return self.env['li.prospect'], personas
        prospects = self.env['li.prospect'].search(domain + [('persona_id', 'in', list(personas))],
                                                   order='last_activity_date asc', limit=100)
        busy = set(self.env['li.work.item'].search([('prospect_id', 'in', prospects.ids),
                                                    ('state', '=', 'released')]).mapped('prospect_id').ids)
        return prospects.filtered(lambda p: p.id not in busy), personas

    def _gen_handoff(self, profile, ctx):
        items = []
        prospects, quota = self._chat_candidates(profile, ctx, [
            ('linkedin_profile_id', '=', profile.id), ('handoff_pending', '=', True),
            ('do_not_contact', '=', False), ('needs_check', '=', False)])
        for prospect in prospects:
            if min(ctx['left'], ctx['sends'][profile.id]) - len(items) <= 0:
                break
            if quota[prospect.persona_id.id] <= 0:
                continue
            chat = prospect.persona_id.chat_agent_id
            text = self._render(chat.handoff_message, prospect)
            if chat.meeting_link and chat.meeting_link not in text:
                text = '%s %s' % (text.rstrip(), chat.meeting_link)
            quota[prospect.persona_id.id] -= 1
            items.append(self._create_item('handoff', 'chat', profile, prospect.persona_id, prospect, quota=True,
                                           payload={
                'text': text,
                'meeting_link': chat.meeting_link or '',
                'conversation': prospect._conversation_payload(),
                'instructions': 'Send this handoff message (you may adjust the wording to the conversation, keep '
                                'the meeting link exactly). ' + SEND_IN_CHROME + ' ' + GUARDRAILS,
            }))
        return items

    def _gen_message(self, profile, ctx):
        items = []
        now = utc_now()
        prospects, quota = self._chat_candidates(profile, ctx, [
            ('linkedin_profile_id', '=', profile.id), ('stage', 'in', CHAT_STAGES),
            ('is_taken_over', '=', False), ('do_not_contact', '=', False), ('needs_check', '=', False),
            ('needs_analysis', '=', False), ('sequence_stopped', '=', False)])
        for prospect in prospects:
            if min(ctx['left'], ctx['sends'][profile.id]) - len(items) <= 0:
                break
            if quota[prospect.persona_id.id] <= 0:
                continue
            step = self._next_step(prospect)
            if not step:
                continue
            due, _why = self._step_due(prospect, step, now)
            if not due:
                continue
            steps = self._steps(prospect.persona_id)
            number = steps.ids.index(step.id) + 1
            quota[prospect.persona_id.id] -= 1
            items.append(self._create_item('message', 'chat', profile, prospect.persona_id, prospect, quota=True,
                                           step_id=step.id, payload={
                'step': dict(self._step_payload(step, number), template=step.template or '',
                             ai_personalise=step.ai_personalise),
                'draft': self._render(step.template, prospect),
                'conversation': prospect._conversation_payload(),
                'answers_so_far': prospect._answers_dict(),
                'instructions': 'Write step %s (%s) for this prospect from the objective and template%s, in the '
                                'persona\'s tone and language, following the conversation so far. No placeholders '
                                'left. %s %s %s' % (
                                    number, step.name, ' (rewrite it for this person)' if step.ai_personalise
                                    else ' (keep the template wording, fill the placeholders)',
                                    CHAT_METHOD_CHROME if step.ai_personalise else '', SEND_IN_CHROME,
                                    GUARDRAILS),
            }))
        return items

    # ------------------------------------------------------------------
    # Send checks and results
    # ------------------------------------------------------------------
    def _send_specific_block(self, item):
        prospect = item.prospect_id
        if item.work_type == 'message':
            if prospect.sequence_stopped:
                return 'the sequence is stopped for this prospect'
            if prospect.needs_analysis:
                return 'a new reply must be analysed first'
            if self._next_step(prospect) != item.step_id:
                return 'step %s is no longer the next step' % item.step_id.name
            return None
        return super()._send_specific_block(item)

    def _record_out(self, item, text, kind, **vals):
        now = utc_now()
        values = {'prospect_id': item.prospect_id.id, 'direction': 'out', 'kind': kind, 'body': text,
                  'ai_generated': True, 'date': now, 'state': 'sent', 'work_item_id': item.id,
                  'sender_name': item.linkedin_profile_id.my_display_name}
        values.update(vals)
        item.prospect_id.sudo().awaiting_reply = True
        message = self.env['li.message'].sudo().create(values)
        self._on_our_message(item.prospect_id.sudo())
        return message

    def _apply_sent_message(self, item, text, note_sent):
        prospect = item.prospect_id.sudo()
        step = item.step_id
        number = self._steps(prospect.persona_id).ids.index(step.id) + 1 if step else 0
        self._record_out(item, text, 'message', step_id=step.id)
        now = utc_now()
        vals = {'current_step_id': step.id, 'last_outbound_date': now, 'next_message_date': False}
        if prospect.stage in ('accepted', 'replied'):
            vals['stage'] = 'messaged'
        if not prospect.date_first_message:
            vals['date_first_message'] = now
        prospect.write(vals)
        nxt = self._next_step(prospect)
        if nxt and nxt.trigger == 'after_accept':
            prospect.next_message_date = now + timedelta(days=nxt.wait_days or 0)
        self._after_outbound(prospect)
        full = _('Step %(n)s – %(step)s sent: %(text)s', n=number, step=step.name, text=text)
        short = _('Step %(n)s – %(step)s sent to %(name)s', n=number, step=step.name, name=prospect.name)
        self.env['li.event']._log('message_sent', 'chat', persona=prospect.persona_id, prospect=prospect,
                                  detail=text, persona_body=short, prospect_body=full)
        return 'Step %s sent to %s recorded.' % (number, prospect.name)

    def _apply_sent_handoff(self, item, text, note_sent):
        prospect = item.prospect_id.sudo()
        self._record_out(item, text, 'handoff')
        prospect.write({'handoff_pending': False, 'last_outbound_date': utc_now()})
        full = _('Handoff sent: %s', text)
        short = _('Handoff message sent to %s', prospect.name)
        self.env['li.event']._log('message_sent', 'chat', persona=prospect.persona_id, prospect=prospect,
                                  lead=prospect.crm_lead_id, detail=text, persona_body=short, prospect_body=full,
                                  lead_body=full)
        return 'Handoff to %s recorded.' % prospect.name

    def _after_outbound(self, prospect):
        """Hook: follow-up scheduling (phase 4)."""
        return True

    # ------------------------------------------------------------------
    # li_record_conversation
    # ------------------------------------------------------------------
    def _find_thread_prospect(self, profile, prospect_id=None, linkedin_url=None):
        Prospect = self.env['li.prospect']
        if prospect_id:
            prospect = Prospect.browse(prospect_id).exists()
            if not prospect:
                raise ToolError('Unknown prospect_id %s' % prospect_id)
            if prospect.linkedin_profile_id != profile:
                raise ToolError('Wrong LinkedIn connector: prospect %s is handled by "%s". Nothing was recorded.'
                                % (prospect.name, prospect.linkedin_profile_id.account_key))
            return prospect
        username = linkedin_username(linkedin_url)
        if not username:
            raise ToolError('Give prospect_id or a LinkedIn profile URL')
        prospects = Prospect.search([('linkedin_username', '=', username), ('linkedin_profile_id', '=', profile.id)],
                                    order='last_activity_date desc')
        if not prospects:
            raise ToolError('%s is not a tracked prospect of %s: only record threads of tracked prospects'
                            % (linkedin_url, profile.account_key))
        return prospects[0]

    def _is_ours(self, profile, sender):
        name = normalize_name(sender)
        return name == normalize_name(profile.my_display_name) or name in SELF_NAMES

    def _confirmed_texts(self, prospect):
        """Normalised texts we confirmed or sent for this prospect (agent messages)."""
        items = self.env['li.work.item'].sudo().search([('prospect_id', '=', prospect.id), ('confirmed', '=', True)])
        return Counter(normalize_message(i.text_sent or i.text_confirmed) for i in items
                       if i.text_sent or i.text_confirmed)

    def _tool_li_record_conversation(self, linkedin_profile, messages, work_id=None, prospect_id=None,
                                     linkedin_url=None):
        self._lock()
        profile = self._profile_for(linkedin_profile, required=True)
        self._check_chrome(profile)
        item = self.env['li.work.item']
        if work_id:
            item = self._get_item(work_id, ['check_inbox'])
            self._check_connector(item, linkedin_profile, required=True)
        prospect = self._find_thread_prospect(profile, prospect_id, linkedin_url).sudo()
        result = self._record_thread(profile, prospect, messages)
        if item and item.state == 'released':
            item._close('done', result_status='ok')
        return result

    def _record_thread(self, profile, prospect, messages):
        """Store what is new in one conversation thread (read by Claude in Chrome
        or by the background reader) and react: replies, manual takeover,
        Activity Agent. A message marked after_link (a line under one of our
        messages holding a link, in the same group) that matches no agent text
        is the link preview, not a message written by hand."""
        stored = prospect.message_ids_li.sorted('id')
        incoming = []
        for raw in messages:
            body = (raw.get('text') or '').strip()
            if body:
                direction = 'out' if self._is_ours(profile, raw.get('sender_name')) else 'in'
                incoming.append((raw, body, (direction, normalize_message(body))))
        fresh = self._new_thread_messages(stored, incoming)
        agent_texts = self._confirmed_texts(prospect)
        for msg in stored.filtered(lambda m: m.direction == 'out' and m.ai_generated):
            key = normalize_message(msg.body)
            if agent_texts[key]:
                agent_texts[key] -= 1  # already matched by an agent row
        new_in, new_human_out, new_agent_out = [], [], []
        now = utc_now()
        Message = self.env['li.message'].sudo()
        for raw, body, key in fresh:
            direction = key[0]
            date = _parse_sent_at(raw.get('sent_at')) or now
            vals = {'prospect_id': prospect.id, 'direction': direction, 'body': body, 'date': date,
                    'state': 'sent', 'sender_name': raw.get('sender_name'), 'seen_in_thread': True}
            if direction == 'in':
                new_in.append(Message.create(dict(vals, kind='reply')))
                self._on_inbound(prospect, new_in[-1])
            elif agent_texts[key[1]] > 0:
                agent_texts[key[1]] -= 1
                new_agent_out.append(Message.create(dict(vals, kind='message', ai_generated=True)))
                prospect.awaiting_reply = True
                self._on_our_message(prospect)
            elif raw.get('after_link'):
                continue
            else:
                msg = Message.create(dict(vals, kind='manual', ai_generated=False))
                new_human_out.append(msg)
                self._on_human_outbound(prospect, msg, new_in)
        if new_in:
            self._after_new_replies(prospect, new_in)
        parts = []
        if new_in:
            parts.append('%s new repl%s' % (len(new_in), 'y' if len(new_in) == 1 else 'ies'))
        if new_human_out:
            parts.append('%s message(s) written by hand%s' % (
                len(new_human_out), ' — prospect taken over' if prospect.takeover_reason == 'human_message' else ''))
        if new_agent_out:
            parts.append('%s agent message(s) matched' % len(new_agent_out))
        return {'prospect_id': prospect.id, 'new_replies': len(new_in), 'new_manual_messages': len(new_human_out),
                'stage': prospect.stage, 'taken_over': prospect.is_taken_over,
                'needs_analysis': prospect.needs_analysis,
                'message': '%s: %s.' % (prospect.name, ', '.join(parts) if parts else 'nothing new')}

    @staticmethod
    def _new_thread_messages(stored, incoming):
        """Messages of the incoming thread that are not stored yet.

        LinkedIn may return the whole thread or only its latest part, with no
        usable timestamps. First align: the longest k where the first k incoming
        messages equal the last k stored ones (side + normalised text); what
        follows is new. Without any overlap, fall back to occurrence matching:
        the n-th occurrence of the same side + text is new only if fewer are
        stored."""
        stored_keys = [(m.direction, normalize_message(m.body)) for m in stored]
        incoming_keys = [key for _raw, _body, key in incoming]
        for k in range(min(len(stored_keys), len(incoming_keys)), 0, -1):
            if incoming_keys[:k] == stored_keys[-k:]:
                return incoming[k:]
        existing = Counter(stored_keys)
        seen = Counter()
        fresh = []
        for entry in incoming:
            key = entry[2]
            seen[key] += 1
            if seen[key] > existing[key]:
                fresh.append(entry)
        return fresh

    def _on_our_message(self, prospect):
        """Hook: a message from our account was recorded (Activity Agent, phase 4)."""
        return True

    def _on_inbound(self, prospect, msg):
        """Hook per new inbound message (Activity Agent, phase 4)."""
        prospect.write({'last_inbound_date': max(prospect.last_inbound_date or msg.date, msg.date, utc_now()),
                        'awaiting_reply': False})

    def _on_human_outbound(self, prospect, msg, new_in):
        """A message from our account that no agent sent: manual takeover (6.6)."""
        prospect.write({'last_outbound_date': utc_now(), 'awaiting_reply': True})
        self._on_our_message(prospect)
        if not prospect.is_taken_over:
            owner = prospect.persona_id.linkedin_profile_id.owner_id
            prospect._take_over(user=owner, reason='human_message')

    def _after_new_replies(self, prospect, new_in):
        now = utc_now()
        vals = {'last_inbound_date': now}
        if not prospect.date_first_reply:
            vals['date_first_reply'] = now
        if prospect.stage in ('invited', 'withdrawn', 'queued'):
            self._accept(prospect, note=_('detected from a reply'))
        if prospect.stage in ('accepted', 'messaged', 'replied', 'no_response'):
            vals['stage'] = 'replied'
        analysable = (not prospect.is_taken_over and not prospect.do_not_contact
                      and prospect.stage not in ('warm', 'meeting', 'not_interested', 'do_not_contact'))
        vals['needs_analysis'] = analysable
        prospect.write(vals)
        # a released message based on the old state must not go out
        self.env['li.work.item'].sudo()._cancel_open(
            [('prospect_id', '=', prospect.id), ('work_type', 'in', ('message', 'followup', 'analyse'))],
            reason='new reply received', stale=True)
        texts = ' / '.join(m.body for m in new_in)
        full = _('%(name)s replied: %(text)s', name=prospect.name, text=texts)
        short = _('%(name)s replied: %(text)s', name=prospect.name,
                  text=texts if len(texts) <= 120 else texts[:119] + '…')
        self.env['li.event']._log('reply_received', 'chat', persona=prospect.persona_id, prospect=prospect,
                                  lead=prospect.crm_lead_id, detail=texts, persona_body=short, prospect_body=full)
        self._on_replies_logged(prospect, new_in)

    def _on_replies_logged(self, prospect, new_in):
        """Hook: Follow-up / Activity Agents (phase 4)."""
        return True

    # ------------------------------------------------------------------
    # li_record_analysis
    # ------------------------------------------------------------------
    def _tool_li_record_analysis(self, work_id, sentiment, pivot, summary, answers=None, pivot_reason=None):
        self._lock()
        item = self._get_item(work_id, ['analyse'])
        if item.state not in ('released', 'expired'):
            raise ToolError('Work item %s is %s' % (item.id, item.state))
        prospect = item.prospect_id.sudo()
        if not prospect:
            raise ToolError('The prospect no longer exists')
        chat = prospect.persona_id.chat_agent_id
        merged = prospect._answers_dict()
        merged.update({k: v for k, v in (answers or {}).items() if v})
        prospect.write({'answers': json.dumps(merged, ensure_ascii=False), 'ai_summary': summary,
                        'last_sentiment': sentiment, 'needs_analysis': False})
        item._close('done', result_status=sentiment)
        Event = self.env['li.event']
        if sentiment == 'opt_out':
            prospect.write({'stage': 'not_interested', 'do_not_contact': True, 'sequence_stopped': True,
                            'handoff_pending': False})
            self.env['li.work.item'].sudo()._cancel_open([('prospect_id', '=', prospect.id)], reason='opt-out')
            line = _('%s asked not to be contacted — closed and added to the do-not-contact list', prospect.name)
            for record in (prospect, prospect.persona_id):
                record.message_post(body=line, author_id=Event._ai_partner().id, subtype_xmlid='mail.mt_note')
            return {'stage': prospect.stage, 'do_not_contact': True, 'message': line}
        if sentiment == 'negative' and chat.stop_on_negative:
            prospect.write({'stage': 'not_interested', 'sequence_stopped': True})
            line = _('%s is not interested — sequence stopped', prospect.name)
            for record in (prospect, prospect.persona_id):
                record.message_post(body=line, author_id=Event._ai_partner().id, subtype_xmlid='mail.mt_note')
            return {'stage': prospect.stage, 'message': line}
        number = self._step_number(prospect)
        if pivot:
            if number >= (chat.pivot_min_step or 0):
                lead = prospect._pivot(pivot_reason or summary)
                return {'stage': prospect.stage, 'crm_lead_id': lead.id, 'handoff_pending': prospect.handoff_pending,
                        'message': 'Pivot: %s is a warm lead (CRM lead #%s).%s' % (
                            prospect.name, lead.id, ' A handoff item follows.' if prospect.handoff_pending else '')}
            note = ' Pivot ignored: not allowed before step %s (current step %s).' % (chat.pivot_min_step, number)
        else:
            note = ''
        nxt = self._next_step(prospect)
        if nxt:
            prospect.next_message_date = (prospect.last_inbound_date or utc_now()) + timedelta(days=nxt.wait_days or 0)
            next_text = ' Next: step %s (%s).' % (number + 1, nxt.name)
        else:
            next_text = ' No questionnaire steps left.'
        return {'stage': prospect.stage, 'pivot': False,
                'message': 'Analysis recorded for %s (%s).%s%s' % (prospect.name, sentiment, note, next_text)}
