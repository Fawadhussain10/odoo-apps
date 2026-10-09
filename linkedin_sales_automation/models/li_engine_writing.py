"""What Claude does for built-in engine profiles: writing only.

li_get_work hands out writing items (invite_note, message, followup, handoff,
analyse, post_draft) with everything Odoo knows; Claude answers with
li_submit_text / li_record_analysis / li_submit_post_draft. Each call is a few
database reads and writes. Texts go to the sending queue tied to the
conversation as Claude saw it: if it changes before the send, the text is
discarded (stale) and written again.

Posts work in both modes: Claude drafts them from an idea, a person approves,
then the engine (create_post) or Claude in Chrome (publish_post) publishes.
"""
from datetime import timedelta

from odoo import _, fields, models

from .li_common import (
    NOTE_MAX_CHARS, SEND_TYPES, WRITE_ORDER, format_hour, in_window, iso_utc, local_now, one_paragraph,
    unfilled_placeholders, utc_now,
)
from .li_engine import BROWSER_RULES, CHAT_METHOD, GUARDRAILS, ONE_PARAGRAPH
from .li_engine_chat import CHAT_STAGES
from .li_mcp_tools import ToolError
from .li_post import POST_MAX_CHARS, parse_post_stats

OPEN_STATES = ('released', 'queued', 'sending')
SUBMIT = ('Submit it with li_submit_text (work_id, text). Odoo sends it itself in the next send window, after '
          're-reading the conversation; if the conversation changed by then, the text is dropped and a new item '
          'comes.')


class LiClaudeRun(models.Model):
    """One Claude run, recorded by li_finish_run."""
    _name = 'li.claude.run'
    _description = 'Claude run'
    _order = 'date desc, id desc'

    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    linkedin_profile_ids = fields.Many2many('li.profile', string='LinkedIn Profiles')
    written = fields.Integer(help='Texts, analyses and post drafts Claude submitted in this run.')
    done = fields.Integer(help='Claude in Chrome items Claude reported done in this run.')
    errors = fields.Integer('Error count')
    error_text = fields.Text('Errors')
    summary = fields.Text()


class LiMcpWriting(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _busy_prospects(self, prospects):
        return set(self.env['li.work.item'].search([('prospect_id', 'in', prospects.ids),
                                                    ('state', 'in', OPEN_STATES)]).mapped('prospect_id').ids)

    def _writing_open(self, persona, work_type):
        return self.env['li.work.item'].search_count([('persona_id', '=', persona.id), ('work_type', '=', work_type),
                                                      ('writing', '=', True), ('state', 'in', OPEN_STATES)])

    def _writing_item(self, kind, work_type, agent_type, profile, persona, prospect, instructions, payload, **vals):
        payload = dict(payload, type=kind, report_with='li_submit_text',
                       instructions='%s %s %s' % (instructions, ONE_PARAGRAPH, SUBMIT))
        return self._create_item(work_type, agent_type, profile, persona, prospect, payload=payload, writing=True,
                                 conversation_version=max(prospect.message_ids_li.ids or [0]), **vals)

    def _window_text(self, persona, agent):
        now = local_now(persona.target_timezone)
        if persona._is_working_day(now) and in_window(now, agent.send_window_from, agent.send_window_to):
            return 'now'
        return '%s–%s %s on target working days' % (format_hour(agent.send_window_from),
                                                   format_hour(agent.send_window_to), persona.target_timezone)

    # ------------------------------------------------------------------
    # Writing items (engine profiles)
    # ------------------------------------------------------------------
    def _gen_w_handoff(self, profile, ctx):
        items = []
        personas = profile.persona_ids.filtered(lambda p: p.chat_agent_id.state == 'running')
        prospects = self.env['li.prospect'].search([
            ('persona_id', 'in', personas.ids), ('handoff_pending', '=', True), ('do_not_contact', '=', False),
            ('needs_check', '=', False)], limit=50)
        busy = self._busy_prospects(prospects)
        for prospect in prospects.filtered(lambda p: p.id not in busy and not p._profile_pending()):
            if ctx['left'] - len(items) <= 0:
                break
            chat = prospect.persona_id.chat_agent_id
            draft = self._render(chat.handoff_message, prospect)
            if chat.meeting_link and chat.meeting_link not in draft:
                draft = '%s %s' % (draft.rstrip(), chat.meeting_link)
            items.append(self._writing_item(
                'handoff', 'handoff', 'chat', profile, prospect.persona_id, prospect,
                'Write the handoff message from the draft, fitted to the conversation; keep the meeting link exactly. '
                + CHAT_METHOD + ' ' + GUARDRAILS,
                {'draft': draft, 'meeting_link': chat.meeting_link or '',
                 'conversation': prospect._conversation_payload(),
                 'situation': prospect._situation_payload()}))
        return items

    def _gen_w_message(self, profile, ctx):
        items = []
        now = utc_now()
        personas = profile.persona_ids.filtered(lambda p: p.chat_agent_id.state == 'running')
        prospects = self.env['li.prospect'].search([
            ('persona_id', 'in', personas.ids), ('stage', 'in', CHAT_STAGES), ('is_taken_over', '=', False),
            ('do_not_contact', '=', False), ('needs_check', '=', False), ('needs_analysis', '=', False),
            ('sequence_stopped', '=', False)], order='last_activity_date asc', limit=100)
        busy = self._busy_prospects(prospects)
        room = {p.id: p.chat_agent_id.daily_limit - self._writing_open(p, 'message') for p in personas}
        for prospect in prospects.filtered(lambda p: p.id not in busy):
            if ctx['left'] - len(items) <= 0:
                break
            if room[prospect.persona_id.id] <= 0 or prospect._profile_pending():
                continue                        # the profile is read first (next background run)
            step = self._next_step(prospect)
            if not step or not self._step_due(prospect, step, now)[0]:
                continue
            number = self._steps(prospect.persona_id).ids.index(step.id) + 1
            room[prospect.persona_id.id] -= 1
            items.append(self._writing_item(
                'message', 'message', 'chat', profile, prospect.persona_id, prospect,
                'Write step %s (%s) for this prospect from the objective and template%s, in the persona\'s tone and '
                'language, following the conversation so far. No placeholders left. %s %s' % (
                    number, step.name, ' (rewrite it for this person)' if step.ai_personalise
                    else ' (keep the template wording, fill the placeholders)',
                    CHAT_METHOD if step.ai_personalise else '', GUARDRAILS),
                {'step': dict(self._step_payload(step, number), template=step.template or '',
                              ai_personalise=step.ai_personalise),
                 'draft': self._render(step.template, prospect),
                 'conversation': prospect._conversation_payload(),
                 'situation': prospect._situation_payload(),
                 'answers_so_far': prospect._answers_dict()},
                step_id=step.id))
        return items

    def _gen_w_followup(self, profile, ctx):
        agent = self.env['li.followup.agent']._get()
        if agent.state != 'running' or not agent.step_ids:
            return []
        items = []
        steps = agent._ordered_steps()
        prospects = self.env['li.prospect'].search([
            ('linkedin_profile_id', '=', profile.id), ('awaiting_reply', '=', True), ('is_taken_over', '=', False),
            ('do_not_contact', '=', False), ('needs_check', '=', False),
            ('followup_count', '<', agent.max_followups)], order='last_outbound_date asc', limit=100)
        busy = self._busy_prospects(prospects)
        room = agent.daily_limit - self.env['li.work.item'].search_count([
            ('work_type', '=', 'followup'), ('writing', '=', True), ('state', 'in', OPEN_STATES)])
        for prospect in prospects.filtered(lambda p: p.id not in busy):
            if ctx['left'] - len(items) <= 0 or room - len(items) <= 0:
                break
            step = self._followup_step_for(prospect, agent)
            if not step or self._followup_block(prospect, agent, step):
                continue
            number = steps.ids.index(step.id) + 1
            silent_days = (utc_now() - (prospect.last_outbound_date or utc_now())).days
            items.append(self._writing_item(
                'followup', 'followup', 'followup', profile, prospect.persona_id, prospect,
                'Follow-up %s (%s): the prospect has not answered for %s days. %s %s' % (
                    number, step.name, silent_days,
                    'Adapt the template to the conversation so far. ' + CHAT_METHOD if step.ai_personalise
                    else 'Keep the template wording, fill the placeholders.', GUARDRAILS),
                {'followup': {'number': number, 'name': step.name, 'template': step.template or '',
                              'ai_personalise': step.ai_personalise, 'days_without_reply': silent_days},
                 'draft': self._render(step.template, prospect),
                 'conversation': prospect._conversation_payload(),
                 'situation': prospect._situation_payload()},
                followup_step_id=step.id))
        return items

    def _gen_w_invite_note(self, profile, ctx):
        items = []
        for persona in profile.persona_ids.filtered(lambda p: p.connection_agent_id.state == 'running'
                                                    and p.connection_agent_id.send_note):
            agent = persona.connection_agent_id
            room = agent.daily_limit - self._writing_open(persona, 'invite')
            prospects = self.env['li.prospect'].search([
                ('persona_id', '=', persona.id), ('stage', '=', 'queued'), ('needs_check', '=', False),
                ('is_taken_over', '=', False), ('do_not_contact', '=', False), ('invite_without_note', '=', False)],
                order='create_date asc, id asc', limit=50)
            busy = self._busy_prospects(prospects)
            for prospect in prospects.filtered(lambda p: p.id not in busy):
                if ctx['left'] - len(items) <= 0 or room <= 0:
                    break
                if self._is_do_not_contact(prospect):
                    continue
                room -= 1
                items.append(self._writing_item(
                    'invite_note', 'invite', 'connection', profile, persona, prospect,
                    'Write a personalised connection note of at most %s characters. First read who this person '
                    'is in prospect.profile (or the headline, title and company when it is empty) and fit the '
                    'note to their real role. %s %s' % (
                        NOTE_MAX_CHARS, agent.note_instructions or '', GUARDRAILS),
                    {'note_max_chars': NOTE_MAX_CHARS}, with_note=True))
        return items

    def _gen_post_draft(self, profile, ctx):
        items = []
        posts = self.env['li.post'].search([('linkedin_profile_id', '=', profile.id), ('state', '=', 'idea')],
                                           order='scheduled_at asc, id asc', limit=10)
        busy = set(self.env['li.work.item'].search([('post_id', 'in', posts.ids),
                                                    ('state', '=', 'released')]).mapped('post_id').ids)
        persona = profile.persona_ids[:1]
        for post in posts.filtered(lambda p: p.id not in busy):
            if ctx['left'] - len(items) <= 0:
                break
            service = post.service_id or persona.service_id
            items.append(self._create_item('post_draft', 'system', profile, post_id=post.id, payload={
                'post': post._payload(),
                'service': {'name': service.name or '', 'description': service.description or '',
                            'value_points': service.value_points or ''},
                'author': {'name': profile.my_display_name or profile.name, 'signature': profile.signature or ''},
                'tone': persona.tone or '', 'language': persona.language or '',
                'report_with': 'li_submit_post_draft',
                'instructions': 'Write a LinkedIn post from the idea: a strong first line, short paragraphs (line '
                                'breaks are fine), at most %s characters, no hashtag spam, no prices or promises '
                                'that are not in the data. Submit it with li_submit_post_draft (work_id, text). A '
                                'person approves it before it is published.' % POST_MAX_CHARS,
            }))
        return items

    # ------------------------------------------------------------------
    # Claude in Chrome post items
    # ------------------------------------------------------------------
    def _gen_publish_post(self, profile, ctx):
        Post = self.env['li.post']
        posts = Post.search(Post._due_domain(profile), order='scheduled_at asc, id asc', limit=5)
        busy = set(self.env['li.work.item'].search([('post_id', 'in', posts.ids),
                                                    ('state', '=', 'released')]).mapped('post_id').ids)
        post = posts.filtered(lambda p: p.id not in busy)[:1]
        if not post or ctx['sends'][profile.id] <= 0:
            return []
        payload = {
            'post': post._payload(),
            'image_url': post._signed_image_url(),
            'instructions': 'Call li_confirm_send with work_id; only if go is true: in Chrome open '
                            'https://www.linkedin.com/feed/, click Start a post, type the post text exactly (keep '
                            'its line breaks)%s, click Post, then open the new post from LinkedIn\'s "View post" '
                            'link and call li_report_result with status published and post_url = its address. '
                            'If you cannot tell whether it was published, report failed with retry_safe false. '
                            '%s' % (', attach the image: download it from image_url (a private link valid for 6 '
                                    'hours, no Odoo login needed) and add it with the photo button; if you cannot '
                                    'attach it, report failed with retry_safe true before clicking Post'
                                    if post.image else '', BROWSER_RULES),
        }
        return [self._create_item('publish_post', 'system', profile, post_id=post.id, payload=payload)]

    def _gen_post_stats(self, profile, ctx):
        Post = self.env['li.post']
        post = Post.search(Post._stats_domain(profile), order='stats_checked_at asc nulls first', limit=1)
        if not post or self._has_open([('post_id', '=', post.id), ('work_type', '=', 'post_stats')]):
            return []
        return [self._create_item('post_stats', 'system', profile, post_id=post.id, payload={
            'post_url': post.post_url,
            'instructions': 'In Chrome open post_url and read the numbers of reactions, comments and reposts under '
                            'the post. Call li_report_result with status ok and reactions, comments, reposts. '
                            'Read-only: click nothing. ' + BROWSER_RULES,
        })]

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    def _tool_li_submit_text(self, work_id, text):
        self._lock()
        item = self._get_item(work_id, SEND_TYPES)
        if not item.writing:
            raise ToolError('Work item %s is a Claude in Chrome item: send it in Chrome with li_confirm_send and '
                            'li_report_result.' % item.id)
        if item.state != 'released':
            raise ToolError('Work item %s is %s (%s). Call li_get_work for fresh items.' % (
                item.id, item.state, item.cancel_reason or 'claim expired'))
        text = one_paragraph(text)
        error = self._validate_text(item, text)
        if error:
            raise ToolError('Not queued: %s. Fix the text and submit again (the item stays yours).' % error)
        reason = self._prospect_block_reason(item)
        if reason:
            item._close('cancelled', cancel_reason=reason)
            return {'ok': False, 'queued': False, 'work_id': item.id, 'message': 'Not needed any more: %s.' % reason}
        if max(item.prospect_id.message_ids_li.ids or [0]) > item.conversation_version:
            item.write({'discarded_stale': True})
            item._close('cancelled', cancel_reason=_('the conversation changed while the text was written'))
            return {'ok': False, 'queued': False, 'work_id': item.id, 'stale': True,
                    'message': 'The conversation changed while you wrote: text dropped. Call li_get_work for a '
                               'fresh item.'}
        now = utc_now()
        item.write({'state': 'queued', 'text_confirmed': text, 'date_submitted': now, 'expires_at': now})
        agent = self._agent_of(item)
        when = self._window_text(item.persona_id, agent)
        return {'ok': True, 'queued': True, 'work_id': item.id, 'send_window': when,
                'message': 'Queued for %s: Odoo sends it %s.' % (
                    item.prospect_id.name, 'shortly' if when == 'now' else 'in the send window (%s)' % when)}

    def _tool_li_submit_post_draft(self, work_id, text, title=None):
        self._lock()
        item = self._get_item(work_id, ['post_draft'])
        if item.state != 'released':
            raise ToolError('Work item %s is %s. Call li_get_work for fresh items.' % (item.id, item.state))
        post = item.post_id.sudo()
        text = (text or '').strip()
        if not text or len(text) > POST_MAX_CHARS:
            raise ToolError('The post must hold 1 to %s characters (this one has %s).' % (POST_MAX_CHARS, len(text)))
        if unfilled_placeholders(text):
            raise ToolError('Fill the placeholders first: %s' % ', '.join(unfilled_placeholders(text)))
        if post.state != 'idea':
            item._close('cancelled', cancel_reason=_('the post is no longer an idea'))
            return {'ok': False, 'message': 'The post is %s now: nothing changed.' % post.state}
        values = {'text': text, 'state': 'draft'}
        if title:
            values['name'] = title[:120]
        post.write(values)
        item._close('done', result_status='drafted')
        item.date_submitted = utc_now()
        approver = post.linkedin_profile_id.owner_id
        post.activity_schedule('mail.mail_activity_data_todo', user_id=approver.id,
                               summary=_('Approve post: %s', post.name),
                               note=_('Claude drafted this post. Read it, edit if needed and press Approve.'))
        post.message_post(body=_('Draft written by Claude.'), author_id=self.env['li.event']._ai_partner().id,
                          subtype_xmlid='mail.mt_note')
        return {'ok': True, 'post_id': post.id,
                'message': 'Draft saved; %s approves it before it is published.' % approver.name}

    # -- Chrome post items through the existing tools ------------------------
    def _tool_li_confirm_send(self, work_id, text=None):
        item = self._get_item(work_id)
        if item.work_type != 'publish_post':
            return super()._tool_li_confirm_send(work_id, text)
        self._lock()
        self._check_chrome(item.linkedin_profile_id)
        post = item.post_id.sudo()
        if item.state != 'released' or item.confirmed:
            return self._stop(item, 'already confirmed or closed', cancel=False)
        if post.state not in ('approved', 'scheduled') or (post.scheduled_at and post.scheduled_at > utc_now()):
            return self._stop(item, 'the post is %s' % post.state)
        if item.linkedin_profile_id.connection_state != 'connected':
            return self._stop(item, 'the LinkedIn profile is %s' % item.linkedin_profile_id.connection_state)
        now = utc_now()
        post.write({'state': 'publishing', 'publish_started': now})
        item.write({'confirmed': True, 'date_confirmed': now, 'expires_at': now + self._claim_timeout()})
        return {'go': True, 'work_id': item.id, 'message': 'Publish it now in Chrome, then call li_report_result.'}

    def _tool_li_report_result(self, work_id, status, linkedin_profile, text_sent=None, note_sent=None,
                               retry_safe=None, error=None, linkedin_url=None, post_url=None, reactions=None,
                               comments=None, reposts=None):
        item = self._get_item(work_id)
        if item.work_type not in ('publish_post', 'post_stats'):
            return super()._tool_li_report_result(work_id, status, linkedin_profile, text_sent=text_sent,
                                                  note_sent=note_sent, retry_safe=retry_safe, error=error,
                                                  linkedin_url=linkedin_url)
        self._lock()
        self._check_connector(item, linkedin_profile, required=True)
        if item.state not in ('released', 'expired'):
            raise ToolError('Work item %s was already reported (%s)' % (item.id, item.state))
        status = (status or '').strip().lower()
        post = item.post_id.sudo()
        if item.work_type == 'post_stats':
            if status == 'ok':
                post._set_stats(int(reactions or 0), int(comments or 0), int(reposts or 0))
            else:
                post.stats_checked_at = utc_now()
            item._close('done', result_status=status)
            return {'ok': True, 'message': 'Stats of "%s" saved.' % post.name}
        if status in ('published', 'sent', 'ok'):
            item._close('done', result_status='published')
            post._mark_published(post_url)
            return {'ok': True, 'message': 'Post "%s" marked published.' % post.name}
        safe = bool(retry_safe) if retry_safe is not None else not item.confirmed
        item._close('failed', result_status=status or 'failed', error=error or status, retry_safe=safe)
        if status == 'restricted':
            item.linkedin_profile_id.sudo()._set_restricted(error or _('reported by Claude in Chrome'))
        post._publish_failed(error or status or 'failed', safe)
        return {'ok': True, 'message': 'Failure recorded%s.' % ('' if safe else '; the post is not retried')}

    # ------------------------------------------------------------------
    # li_finish_run: record the run
    # ------------------------------------------------------------------
    def _tool_li_finish_run(self, summary=None, errors=None, linkedin_profile=None):
        Run = self.env['li.claude.run'].sudo()
        last = Run.search([], limit=1)
        now = utc_now()
        since = max(last.date or now - timedelta(hours=24), now - timedelta(hours=24))
        WorkItem = self.env['li.work.item'].sudo()
        written = WorkItem.search([('date_submitted', '>=', since)])
        analysed = WorkItem.search([('work_type', '=', 'analyse'), ('state', '=', 'done'), ('date_done', '>=', since)])
        done = WorkItem.search([('writing', '=', False), ('state', '=', 'done'), ('date_done', '>=', since),
                                ('work_type', 'not in', ('analyse', 'post_draft'))])
        failed = WorkItem.search([('writing', '=', False), ('state', '=', 'failed'), ('date_done', '>=', since)])
        result = super()._tool_li_finish_run(summary=summary)
        profiles = (written | analysed | done | failed).mapped('linkedin_profile_id')
        if linkedin_profile:
            profiles |= self._profile_for(linkedin_profile)
        errors = [e for e in (errors or []) if e]
        run = Run.create({
            'date': now, 'linkedin_profile_ids': [(6, 0, profiles.ids)],
            'written': len(written) + len(analysed), 'done': len(done), 'errors': len(errors) + len(failed),
            'error_text': '\n'.join(errors + ['%s %s: %s' % (i.work_type, i.prospect_id.name or i.post_id.name or '',
                                                                 i.error or i.result_status or '') for i in failed])
                          or False,
            'summary': summary or False,
        })
        result.update({'run_id': run.id, 'written': run.written, 'done': run.done, 'errors': run.errors})
        return result

    # ------------------------------------------------------------------
    # li_overview: queue and posts per profile
    # ------------------------------------------------------------------
    def _tool_li_overview(self):
        result = super()._tool_li_overview()
        WorkItem = self.env['li.work.item']
        Post = self.env['li.post']
        by_key = {p.account_key: p for p in self.env['li.profile'].search([])}
        result['before_writing'] = WRITE_ORDER
        for entry in result['profiles']:
            profile = by_key.get(entry['linkedin_profile'])
            if not profile:
                continue
            entry['queued_texts'] = WorkItem.search_count([('linkedin_profile_id', '=', profile.id),
                                                           ('state', '=', 'queued')])
            entry['post_ideas'] = Post.search_count([('linkedin_profile_id', '=', profile.id), ('state', '=', 'idea')])
            entry['posts_to_approve'] = Post.search_count([('linkedin_profile_id', '=', profile.id),
                                                           ('state', '=', 'draft')])
            if profile.execution_mode == 'engine':
                entry['engine'] = profile.engine_state
                entry['linkedin_language'] = profile.interface_language or 'unknown'
                entry['last_successful_action'] = iso_utc(profile.last_success_at)
        return result
