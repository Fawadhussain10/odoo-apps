"""Follow-up Agent (6.7), takeover-aware inbox tracking and Activity Agent (6.8)."""
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models

from .li_common import CLOSED_STAGES, local_now, utc_now
from .li_engine import GUARDRAILS
from .li_engine_chat import SEND_IN_CHROME, TRACKED_STAGES

FOLLOWUP_STAGES = ('accepted', 'messaged', 'replied')


def _hours(delta):
    hours = delta.total_seconds() / 3600.0
    return ('%.0f h' % hours) if hours >= 1 else ('%d min' % max(int(delta.total_seconds() // 60), 0))


class LiMcpEngineFollowup(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    # ------------------------------------------------------------------
    # check_inbox: taken-over prospects stay tracked while the Activity Agent runs
    # ------------------------------------------------------------------
    def _tracked_prospects(self, profile, limit=50):
        Prospect = self.env['li.prospect']
        followup = self.env['li.followup.agent']._get()
        activity = self.env['li.activity.agent']._get()
        chat_personas = profile.persona_ids.filtered(
            lambda p: p.chat_agent_id.state == 'running' or (followup.state == 'running' and followup._covers(p)))
        domain = [('linkedin_profile_id', '=', profile.id), ('do_not_contact', '=', False)]
        tracked = Prospect.search(domain + [('stage', 'in', TRACKED_STAGES), ('is_taken_over', '=', False),
                                            ('persona_id', 'in', chat_personas.ids)],
                                  order='last_activity_date desc', limit=limit)
        if activity.state == 'running':
            tracked |= Prospect.search(domain + [('is_taken_over', '=', True), ('stage', 'not in', CLOSED_STAGES)],
                                       order='last_activity_date desc', limit=limit)
        return tracked.sorted(lambda p: p.last_activity_date or p.create_date, reverse=True)[:limit]

    # ------------------------------------------------------------------
    # Follow-up Agent (6.7)
    # ------------------------------------------------------------------
    def _followup_step_for(self, prospect, agent):
        steps = agent._ordered_steps()
        if prospect.followup_count >= min(agent.max_followups, len(steps)):
            return self.env['li.followup.step']
        return steps[prospect.followup_count]

    def _followup_block(self, prospect, agent, step=None):
        """Reason the prospect may not get a follow-up now, or None."""
        if not agent._covers(prospect.persona_id):
            return 'persona not covered by the Follow-up Agent'
        if prospect.is_taken_over:
            return 'taken over'
        if prospect.stage not in FOLLOWUP_STAGES or prospect.do_not_contact or prospect.needs_check:
            return 'stage %s' % prospect.stage
        if not prospect.awaiting_reply or prospect.needs_analysis:
            return 'not waiting for a reply'
        last = prospect.message_ids_li.sorted('id')[-1:]
        if not last or last.direction != 'out' or not last.ai_generated:
            return 'the last message of the thread is not an agent message'
        nxt = self._next_step(prospect)
        if nxt and nxt.trigger == 'after_accept' and not prospect.sequence_stopped:
            return 'the Chat Agent sends the next step itself'
        step = step or self._followup_step_for(prospect, agent)
        if not step:
            return 'no follow-up left'
        due = (prospect.last_outbound_date or utc_now()) + timedelta(days=step.wait_days or 0)
        if utc_now() < due:
            return 'next follow-up due at %s' % due
        return None

    def _gen_followup(self, profile, ctx):
        agent = self.env['li.followup.agent']._get()
        if agent.state != 'running' or not agent.step_ids:
            return []
        quota = agent.daily_limit - self.env['li.work.item'].sudo()._followup_used()
        if quota <= 0:
            ctx['reasons'].append('Follow-up Agent daily limit (%s) reached' % agent.daily_limit)
            return []
        prospects = self.env['li.prospect'].search([
            ('linkedin_profile_id', '=', profile.id), ('stage', 'in', FOLLOWUP_STAGES), ('awaiting_reply', '=', True),
            ('is_taken_over', '=', False), ('do_not_contact', '=', False), ('needs_check', '=', False),
            ('followup_count', '<', agent.max_followups)], order='last_outbound_date asc', limit=100)
        busy = set(self.env['li.work.item'].search([('prospect_id', 'in', prospects.ids),
                                                    ('state', '=', 'released')]).mapped('prospect_id').ids)
        windows = {}
        items = []
        steps = agent._ordered_steps()
        for prospect in prospects:
            if min(ctx['left'], ctx['sends'][profile.id], quota) - len(items) <= 0:
                break
            if prospect.id in busy:
                continue
            persona = prospect.persona_id
            if persona.id not in windows:
                windows[persona.id] = self._window(persona, agent)
                if not windows[persona.id][0]:
                    ctx['reasons'].append(windows[persona.id][1])
            if not windows[persona.id][0]:
                continue
            step = self._followup_step_for(prospect, agent)
            if self._followup_block(prospect, agent, step):
                continue
            number = steps.ids.index(step.id) + 1
            silent_days = (utc_now() - (prospect.last_outbound_date or utc_now())).days
            items.append(self._create_item('followup', 'followup', profile, persona, prospect, quota=True,
                                           followup_step_id=step.id, payload={
                'followup': {'number': number, 'name': step.name, 'template': step.template or '',
                             'ai_personalise': step.ai_personalise, 'days_without_reply': silent_days},
                'draft': self._render(step.template, prospect),
                'conversation': prospect._conversation_payload(),
                'instructions': 'Follow-up %s (%s): the prospect has not answered for %s days. %s %s %s' % (
                                    number, step.name, silent_days,
                                    'Adapt the template to the conversation so far.' if step.ai_personalise
                                    else 'Keep the template wording, fill the placeholders.', SEND_IN_CHROME,
                                    GUARDRAILS),
            }))
        return items

    def _send_specific_block(self, item):
        if item.work_type == 'followup':
            agent = self.env['li.followup.agent']._get()
            if self._followup_step_for(item.prospect_id, agent) != item.followup_step_id:
                return 'follow-up step %s is no longer the next one' % item.followup_step_id.name
            reason = self._followup_block(item.prospect_id, agent, item.followup_step_id)
            if reason and not reason.startswith('next follow-up due'):
                return reason
            return None
        return super()._send_specific_block(item)

    def _apply_sent_followup(self, item, text, note_sent):
        prospect = item.prospect_id.sudo()
        agent = self.env['li.followup.agent']._get()
        silent = utc_now() - (prospect.last_outbound_date or utc_now())
        self._record_out(item, text, 'followup', followup_step_id=item.followup_step_id.id)
        count = prospect.followup_count + 1
        prospect.write({'followup_count': count, 'last_outbound_date': utc_now()})
        self._after_outbound(prospect)
        step = item.followup_step_id
        short = _('Follow-up %(n)s – %(step)s sent to %(name)s (no reply for %(days)s days)',
                  n=count, step=step.name, name=prospect.name, days=silent.days)
        self.env['li.event']._log('followup_sent', 'followup', persona=prospect.persona_id, prospect=prospect,
                                  detail=text, persona_body=short, prospect_body='%s: %s' % (short, text))
        agent.sudo().last_run = utc_now()
        return 'Follow-up %s to %s recorded.' % (count, prospect.name)

    def _after_outbound(self, prospect):
        """Schedule the next follow-up (display only; li_get_work decides)."""
        agent = self.env['li.followup.agent']._get()
        step = self._followup_step_for(prospect, agent)
        prospect.sudo().next_followup_date = (
            utc_now() + timedelta(days=step.wait_days or 0) if step and agent.state == 'running' else False)
        return True

    def _on_replies_logged(self, prospect, new_in):
        """A reply stops follow-ups; on_reply decides whether the Chat Agent continues."""
        agent = self.env['li.followup.agent']._get()
        vals = {'next_followup_date': False}
        if prospect.followup_count and agent.on_reply == 'stop' and not prospect.is_taken_over:
            vals['sequence_stopped'] = True
            line = _('%s replied to a follow-up — sequence stopped (Follow-up Agent setting)', prospect.name)
            prospect.message_post(body=line, author_id=self.env['li.event']._ai_partner().id,
                                  subtype_xmlid='mail.mt_note')
        prospect.write(vals)
        return super()._on_replies_logged(prospect, new_in)

    @api.model
    def _cron_close_no_response(self):
        """After the last follow-up plus its wait with no reply -> Closed (no response)."""
        agent = self.env['li.followup.agent']._get()
        steps = agent._ordered_steps()
        if not steps:
            return 0
        last_possible = min(agent.max_followups, len(steps))
        closed = 0
        prospects = self.env['li.prospect'].sudo().search([
            ('stage', 'in', FOLLOWUP_STAGES), ('awaiting_reply', '=', True), ('is_taken_over', '=', False),
            ('followup_count', '>=', last_possible), ('followup_count', '>', 0)])
        wait = timedelta(days=steps[last_possible - 1].wait_days or 0)
        for prospect in prospects:
            if prospect.last_outbound_date and utc_now() >= prospect.last_outbound_date + wait:
                prospect.write({'stage': 'no_response', 'next_followup_date': False})
                self.env['li.work.item'].sudo()._cancel_open([('prospect_id', '=', prospect.id)],
                                                             reason='no response')
                line = _('No reply from %(name)s after %(n)s follow-ups — closed (no response)',
                         name=prospect.name, n=prospect.followup_count)
                for record in (prospect, prospect.persona_id):
                    record.message_post(body=line, author_id=self.env['li.event']._ai_partner().id,
                                        subtype_xmlid='mail.mt_note')
                closed += 1
        return closed

    # ------------------------------------------------------------------
    # Activity Agent (6.8)
    # ------------------------------------------------------------------
    def _open_reply_activity(self, prospect):
        activity = prospect.reply_activity_id
        return activity if activity and activity.exists() and activity.active else self.env['mail.activity']

    def _on_inbound(self, prospect, msg):
        super()._on_inbound(prospect, msg)
        agent = self.env['li.activity.agent']._get()
        if not prospect.is_taken_over or agent.state != 'running':
            return
        Event = self.env['li.event']
        excerpt = msg.body if len(msg.body) <= 200 else msg.body[:199] + '…'
        activity = self._open_reply_activity(prospect)
        if activity:
            # no stacking: append to the open activity and keep its deadline
            activity.sudo().note = (activity.note or Markup('')) + Markup('<p>%s</p>') % (
                _('%(name)s replied again: %(text)s', name=prospect.name, text=excerpt))
            return
        target = prospect.crm_lead_id or prospect
        user = agent._assignee(prospect)
        now = utc_now()
        due_at = now + timedelta(hours=agent.deadline_hours or 48)
        due_local = due_at.replace(tzinfo=None)
        if user.tz:
            due_local = local_now(user.tz).replace(tzinfo=None) + (due_at - now)
        note = (agent.note_template or '{prospect} replied: {reply}').replace('{prospect}', prospect.name) \
            .replace('{reply}', excerpt).replace('{persona}', prospect.persona_id.name or '')
        activity = self.env['mail.activity'].sudo().create({
            'res_model_id': self.env['ir.model']._get_id(target._name),
            'res_id': target.id,
            'activity_type_id': agent.reply_activity_type_id.id,
            'summary': agent.reply_activity_type_id.summary or agent.reply_activity_type_id.name,
            'note': Markup('<p>%s</p>') % note,
            'user_id': user.id,
            'date_deadline': fields.Date.to_date(due_local.date()),
        })
        prospect.write({'reply_activity_id': activity.id, 'reply_activity_date': now, 'reply_due_at': due_at,
                        'reply_overdue_logged': False})
        line = _('%(name)s replied — %(type)s for %(user)s, due in %(hours)s h',
                 name=prospect.name, type=agent.reply_activity_type_id.name, user=user.name,
                 hours=agent.deadline_hours)
        Event._log('reply_activity_created', 'activity', persona=prospect.persona_id, prospect=prospect,
                   lead=prospect.crm_lead_id, detail=line, prospect_body=line, lead_body=line)

    def _on_our_message(self, prospect):
        """A message from our account after the reply closes the open reply activity."""
        super()._on_our_message(prospect)
        agent = self.env['li.activity.agent']._get()
        activity = self._open_reply_activity(prospect)
        if not activity or not agent.auto_done:
            return
        took = utc_now() - (prospect.reply_activity_date or utc_now())
        user = activity.user_id
        feedback = _('Replied after %s — closed automatically', _hours(took))
        activity.sudo().action_feedback(feedback=feedback)
        prospect.write({'reply_activity_id': False, 'reply_due_at': False})
        line = _('%(user)s replied after %(time)s — activity closed automatically', user=user.name, time=_hours(took))
        self.env['li.event']._log('reply_activity_done', 'activity', persona=prospect.persona_id, prospect=prospect,
                                  lead=prospect.crm_lead_id, detail='%s (%d s)' % (line, took.total_seconds()),
                                  prospect_body=line, lead_body=line)

    @api.model
    def _cron_reply_overdue(self):
        """Log reply_activity_overdue once per activity (Odoo shows it red)."""
        prospects = self.env['li.prospect'].sudo().search([
            ('reply_activity_id', '!=', False), ('reply_due_at', '<', utc_now()), ('reply_overdue_logged', '=', False)])
        agent = self.env['li.activity.agent']._get()
        for prospect in prospects:
            line = _('Reply to %(name)s overdue — no response within %(hours)s h',
                     name=prospect.name, hours=agent.deadline_hours)
            self.env['li.event']._log('reply_activity_overdue', 'activity', persona=prospect.persona_id,
                                      prospect=prospect, lead=prospect.crm_lead_id, detail=line,
                                      prospect_body=line, lead_body=line)
            prospect.reply_overdue_logged = True
        return len(prospects)
