"""Analytics dashboard data (section 8), computed in SQL.

Each figure is one aggregate SQL statement over li_event. The FROM / WHERE part
of every statement comes from ``_search(domain)``, so the filters and the
record rules (users only see their own profiles) are applied exactly as in the
ORM; the aggregation itself (GROUP BY, COUNT DISTINCT, FILTER, cohorts) runs in
PostgreSQL on the indexed columns (date, event_type, persona, profile, service,
prospect). Nothing loops over event records in Python.
"""
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.tools import SQL

from .li_common import safe_zone

# acceptances of people who were already connected are not accepted invites
NOT_ALREADY_CONNECTED = [('without_invite', '=', False)]
COUNTED = ('invite_sent', 'invite_accepted', 'message_sent', 'reply_received', 'warm_lead', 'meeting_booked',
           'followup_sent')
MAX_DAILY_BARS = 92
EV = '"li_event"'


class LiDashboard(models.AbstractModel):
    _name = 'li.dashboard'
    _description = 'LinkedIn Sales dashboard'

    # ------------------------------------------------------------------
    # Filters -> domains
    # ------------------------------------------------------------------
    def _tz(self):
        return self.env.context.get('tz') or self.env.user.tz or 'UTC'

    def _local_day_start_utc(self, day):
        """Midnight of `day` in the user's time zone, as naive UTC."""
        local = datetime.combine(day, time.min).replace(tzinfo=safe_zone(self._tz()))
        return local.astimezone(safe_zone('UTC')).replace(tzinfo=None)

    def _scope_domain(self, filters, prefix=''):
        domain = []
        if filters.get('execution_mode') in ('engine', 'chrome'):
            domain.append((prefix + 'linkedin_profile_id.execution_mode', '=', filters['execution_mode']))
        for key, field in (('profile_ids', 'linkedin_profile_id'), ('persona_ids', 'persona_id'),
                           ('service_ids', 'service_id')):
            if filters.get(key):
                domain.append((prefix + field, 'in', [int(i) for i in filters[key]]))
        return domain

    def _date_range(self, filters):
        """(start, end) as naive UTC; day boundaries in the user's time zone."""
        preset = filters.get('date_preset') or 'since_active'
        today = fields.Datetime.now().replace(tzinfo=safe_zone('UTC')).astimezone(safe_zone(self._tz())).date()
        end = self._local_day_start_utc(today + timedelta(days=1))
        if preset == 'today':
            return self._local_day_start_utc(today), end
        if preset == 'last_7':
            return self._local_day_start_utc(today - timedelta(days=6)), end
        if preset == 'last_30':
            return self._local_day_start_utc(today - timedelta(days=29)), end
        if preset == 'this_month':
            return self._local_day_start_utc(today.replace(day=1)), end
        if preset == 'custom':
            date_from = fields.Date.to_date(filters.get('date_from')) or today
            date_to = fields.Date.to_date(filters.get('date_to')) or today
            return self._local_day_start_utc(date_from), self._local_day_start_utc(date_to + timedelta(days=1))
        # since active: earliest date_activated of the selected personas
        Persona = self.env['li.persona'].with_context(active_test=False)
        persona_domain = ([('id', 'in', [int(i) for i in filters['persona_ids']])] if filters.get('persona_ids')
                          else self._scope_domain({k: v for k, v in filters.items() if k != 'persona_ids'}))
        query = Persona._search(persona_domain + [('date_activated', '!=', False)])
        self.env.cr.execute(query.select(SQL('min("li_persona"."date_activated")')))
        start = self.env.cr.fetchone()[0]
        return start, end

    def _agent_domain(self, filters):
        agent = filters.get('agent') or 'both'
        if agent == 'connection':
            return [('agent_type', '=', 'connection')]
        if agent == 'chat':
            return [('agent_type', '!=', 'connection')]
        return []

    def _event_domain(self, filters, with_dates=True):
        domain = self._scope_domain(filters) + self._agent_domain(filters)
        if with_dates:
            start, end = self._date_range(filters)
            if start:
                domain.append(('date', '>=', start))
            domain.append(('date', '<', end))
        return domain

    # ------------------------------------------------------------------
    # SQL helpers
    # ------------------------------------------------------------------
    def _query(self, domain):
        """ORM query (filters + record rules) on li_event, ready for SQL."""
        return self.env['li.event']._search(domain)

    def _rows(self, domain, select, groupby=None):
        query = self._query(domain)
        if groupby:
            query.groupby = SQL(groupby)
        self.env.cr.execute(query.select(*[SQL(s) for s in select]))
        return self.env.cr.fetchall()

    def _prospect_subquery(self, domain):
        """(SELECT prospect_id FROM li_event WHERE <domain>) as an SQL object."""
        return self._query(domain + [('prospect_id', '!=', False)]).subselect(SQL('%s."prospect_id"' % EV))

    def _day_bucket(self, granularity='day'):
        # stored dates are naive UTC: bucket them on the user's local calendar
        return SQL("date_trunc(%s, timezone(%s, timezone('UTC', " + EV + '."date")))', granularity, self._tz())

    # ------------------------------------------------------------------
    # Aggregations (one statement each)
    # ------------------------------------------------------------------
    def _count_by_type(self, domain):
        counts = dict.fromkeys(COUNTED, 0)
        counts.update(dict(self._rows(domain + [('event_type', 'in', COUNTED)] + NOT_ALREADY_CONNECTED,
                                      ['%s."event_type"' % EV, 'count(*)'], '%s."event_type"' % EV)))
        return counts

    def _already_connected(self, domain):
        """Prospects marked accepted without an invite (already 1st-degree connections)."""
        rows = self._rows(domain + [('event_type', '=', 'invite_accepted'), ('without_invite', '=', True)],
                          ['count(*)'])
        return rows[0][0] if rows else 0

    def _invite_days(self, domain):
        query = self._query(domain + [('event_type', '=', 'invite_sent')])
        self.env.cr.execute(SQL('SELECT count(DISTINCT %s) FROM %s WHERE %s', self._day_bucket(),
                                query.from_clause, query.where_clause))
        return self.env.cr.fetchone()[0]

    def _cohort_counts(self, filters, domain, sent_type, outcome_type):
        """Distinct prospects with `sent_type` in range, and how many of them
        have `outcome_type` at any time (same scope filters, no dates)."""
        sent = self._prospect_subquery(domain + [('event_type', '=', sent_type)])
        outcome = self._prospect_subquery(self._event_domain(filters, with_dates=False)
                                          + [('event_type', '=', outcome_type)])
        self.env.cr.execute(SQL(
            'SELECT count(*), count(*) FILTER (WHERE s.pid IN %s) '
            'FROM (SELECT DISTINCT x.prospect_id AS pid FROM %s AS x) s', outcome, sent))
        return self.env.cr.fetchone()

    def _cohort_ids(self, filters, domain, sent_type, outcome_type):
        sent = self._prospect_subquery(domain + [('event_type', '=', sent_type)])
        outcome = self._prospect_subquery(self._event_domain(filters, with_dates=False)
                                          + [('event_type', '=', outcome_type)])
        self.env.cr.execute(SQL('SELECT DISTINCT x.prospect_id FROM %s AS x WHERE x.prospect_id IN %s',
                                sent, outcome))
        return [row[0] for row in self.env.cr.fetchall()]

    def _followup_reply_sql(self, filters, domain):
        first = self._query(domain + [('event_type', '=', 'followup_sent'), ('prospect_id', '!=', False)])
        first.groupby = SQL('%s."prospect_id"' % EV)
        replies = self._query(self._event_domain(filters, with_dates=False)
                              + [('event_type', '=', 'reply_received'), ('prospect_id', '!=', False)])
        replies.groupby = SQL('%s."prospect_id"' % EV)
        return SQL('WITH f AS (%s), r AS (%s) ',
                   first.select(SQL('%s."prospect_id" AS pid' % EV), SQL('min(%s."date") AS d' % EV)),
                   replies.select(SQL('%s."prospect_id" AS pid' % EV), SQL('max(%s."date") AS d' % EV)))

    def _followup_reply_counts(self, filters, domain):
        self.env.cr.execute(SQL('%s SELECT count(*), count(*) FILTER (WHERE r.d >= f.d) '
                                'FROM f LEFT JOIN r ON r.pid = f.pid', self._followup_reply_sql(filters, domain)))
        return self.env.cr.fetchone()

    def _followup_reply_ids(self, filters, domain):
        self.env.cr.execute(SQL('%s SELECT f.pid FROM f JOIN r ON r.pid = f.pid WHERE r.d >= f.d',
                                self._followup_reply_sql(filters, domain)))
        return [row[0] for row in self.env.cr.fetchall()]

    def _distinct_prospects(self, domain, event_type):
        rows = self._rows(domain + [('event_type', '=', event_type)], ['count(DISTINCT %s."prospect_id")' % EV])
        return rows[0][0] if rows else 0

    def _overdue_domain(self, filters):
        return self._scope_domain(filters) + [('reply_overdue', '=', True)]

    @staticmethod
    def _rate(numerator, denominator):
        return round(100.0 * numerator / denominator, 1) if denominator else 0.0

    # ------------------------------------------------------------------
    # Public API (called by the OWL client action)
    # ------------------------------------------------------------------
    @api.model
    def get_data(self, filters=None):
        filters = dict(filters or {})
        self.env.flush_all()            # the SQL below reads the tables directly
        domain = self._event_domain(filters)
        start, end = self._date_range(filters)
        counts = self._count_by_type(domain)
        invite_days = self._invite_days(domain)
        invited, accepted = self._cohort_counts(filters, domain, 'invite_sent', 'invite_accepted')
        messaged, replied = self._cohort_counts(filters, domain, 'message_sent', 'reply_received')
        followed, followed_replied = self._followup_reply_counts(filters, domain)
        overdue = self.env['li.prospect'].search_count(self._overdue_domain(filters))
        already_connected = self._already_connected(domain)
        connected = counts['invite_accepted'] + already_connected

        kpis = {
            'connections_sent': counts['invite_sent'],
            'connections_per_day': round(counts['invite_sent'] / invite_days, 1) if invite_days else 0.0,
            'messages_sent': counts['message_sent'],
            'acceptance_rate': self._rate(accepted, invited),
            'reply_rate': self._rate(replied, messaged),
            'warm_lead_rate': self._rate(counts['warm_lead'], connected),
            'meeting_rate': self._rate(counts['meeting_booked'], counts['warm_lead']),
            'meetings_booked': counts['meeting_booked'],
            'followups_sent': counts['followup_sent'],
            'followup_reply_rate': self._rate(followed_replied, followed),
            'overdue_replies': overdue,
        }
        details = {
            'invited_prospects': invited, 'accepted_of_invited': accepted,
            'messaged_prospects': messaged, 'replied_of_messaged': replied,
            'followed_up_prospects': followed, 'replied_after_followup': followed_replied,
            'invite_days': invite_days, 'accepted_events': counts['invite_accepted'],
            'warm_leads': counts['warm_lead'], 'already_connected': already_connected, 'connected': connected,
        }
        funnel = [
            {'key': 'sent', 'label': _('Sent'), 'value': counts['invite_sent']},
            {'key': 'accepted', 'label': _('Accepted'), 'value': counts['invite_accepted']},
            {'key': 'replied', 'label': _('Replied'), 'value': self._distinct_prospects(domain, 'reply_received')},
            {'key': 'warm', 'label': _('Warm leads'), 'value': counts['warm_lead']},
            {'key': 'meetings', 'label': _('Meetings'), 'value': counts['meeting_booked']},
        ]
        return {
            'kpis': kpis,
            'details': details,
            'funnel': funnel,
            'daily': self._daily(domain, start, end),
            'personas': self._persona_table(domain),
            'range': {'start': fields.Datetime.to_string(start) if start else False,
                      'end': fields.Datetime.to_string(end), 'tz': self._tz()},
            'options': self._options(),
            'health': self._health(filters),
            'queue': self._queue(filters),
            'last_run': self._last_run(filters),
            'posts': self._post_kpis(filters, start, end),
            'map': self._map(filters),
        }

    def _daily(self, domain, start, end):
        """Invites sent vs accepted per local day (per week for long ranges)."""
        first = start
        if not first:
            rows = self._rows(domain, ['min(%s."date")' % EV])
            first = rows[0][0] if rows and rows[0][0] else end
        granularity = 'day' if (end - first).days <= MAX_DAILY_BARS else 'week'
        query = self._query(domain + [('event_type', 'in', ('invite_sent', 'invite_accepted'))]
                            + NOT_ALREADY_CONNECTED)
        bucket = self._day_bucket(granularity)
        self.env.cr.execute(SQL(
            'SELECT %s AS bucket, count(*) FILTER (WHERE ' + EV + '."event_type" = %s), '
            'count(*) FILTER (WHERE ' + EV + '."event_type" = %s) FROM %s WHERE %s GROUP BY 1 ORDER BY 1',
            bucket, 'invite_sent', 'invite_accepted', query.from_clause, query.where_clause))
        rows = [{'date': fields.Date.to_string(day.date()), 'sent': sent, 'accepted': acc}
                for day, sent, acc in self.env.cr.fetchall()]
        return {'granularity': granularity, 'rows': rows}

    def _persona_table(self, domain):
        """One row per persona: counts per event type and distinct prospects."""
        query = self._query(domain + [('event_type', 'in', COUNTED), ('persona_id', '!=', False)]
                            + NOT_ALREADY_CONNECTED)
        event_type = SQL.identifier('li_event', 'event_type')
        prospect = SQL.identifier('li_event', 'prospect_id')
        columns = [SQL('count(*) FILTER (WHERE %s = %s)', event_type, name) for name in COUNTED]
        columns += [SQL('count(DISTINCT %s) FILTER (WHERE %s = %s)', prospect, event_type, name)
                    for name in ('message_sent', 'reply_received')]
        self.env.cr.execute(SQL('SELECT %s, %s FROM %s WHERE %s GROUP BY 1', SQL.identifier('li_event', 'persona_id'),
                                SQL(', ').join(columns), query.from_clause, query.where_clause))
        fetched = self.env.cr.fetchall()
        personas = self.env['li.persona'].with_context(active_test=False).browse([r[0] for r in fetched])
        names = {p.id: (p.name, p.linkedin_profile_id.name, p.service_id.name) for p in personas}
        result = []
        for row in fetched:
            values = dict(zip(COUNTED, row[1:1 + len(COUNTED)]))
            messaged, replied = row[1 + len(COUNTED):]
            name, profile, service = names.get(row[0], ('?', '', ''))
            result.append(dict(values, id=row[0], name=name, profile=profile, service=service,
                               acceptance_rate=self._rate(values['invite_accepted'], values['invite_sent']),
                               reply_rate=self._rate(replied, messaged)))
        return sorted(result, key=lambda r: (-r['invite_sent'], r['name']))

    # ------------------------------------------------------------------
    # Operations: account health, work queue, last Claude run, posts
    # ------------------------------------------------------------------
    def _profile_domain(self, filters):
        domain = []
        if filters.get('profile_ids'):
            domain.append(('id', 'in', [int(i) for i in filters['profile_ids']]))
        if filters.get('execution_mode') in ('engine', 'chrome'):
            domain.append(('execution_mode', '=', filters['execution_mode']))
        return domain

    def _today_start(self):
        today = fields.Datetime.now().replace(tzinfo=safe_zone('UTC')).astimezone(safe_zone(self._tz())).date()
        return self._local_day_start_utc(today)

    def _health(self, filters):
        """One entry per visible profile: mode, state, last successful action."""
        profiles = self.env['li.profile'].search(self._profile_domain(filters))
        if not profiles:
            return []
        # last Claude in Chrome item reported done, per profile (one statement)
        query = self.env['li.work.item']._search([('linkedin_profile_id', 'in', profiles.ids), ('state', '=', 'done')])
        self.env.cr.execute(SQL('SELECT %s, max(%s) FROM %s WHERE %s GROUP BY 1',
                                SQL.identifier('li_work_item', 'linkedin_profile_id'),
                                SQL.identifier('li_work_item', 'date_done'), query.from_clause, query.where_clause))
        last_done = dict(self.env.cr.fetchall())
        now = fields.Datetime.now()
        result = []
        for profile in profiles:
            agents = profile.persona_ids.connection_agent_id
            weekly = agents.filtered(lambda a: a.state == 'paused' and a.paused_until and a.paused_until > now)
            if profile.connection_state == 'restricted':
                state, tone = _('Restricted'), 'bad'
            elif profile.connection_state == 'reconnect_needed':
                state, tone = _('Reconnect needed'), 'bad'
            elif profile.connection_state == 'not_connected':
                state, tone = _('Not connected'), 'warn'
            elif profile.execution_mode == 'engine' and profile.interface_language == 'other':
                state, tone = _('LinkedIn not in English'), 'bad'
            elif weekly:
                state, tone = _('Paused – LinkedIn invite limit'), 'warn'
            elif profile.execution_mode == 'engine' and profile.engine_state != 'running':
                state, tone = (_('Engine failed') if profile.engine_state == 'failed' else _('Stopped')), \
                    ('bad' if profile.engine_state == 'failed' else 'warn')
            elif profile.execution_mode == 'engine':
                state, tone = _('Running'), 'ok'
            else:
                state, tone = _('Connected'), 'ok'
            last = profile.last_success_at if profile.execution_mode == 'engine' else max(
                filter(None, [profile.chrome_verified_at, last_done.get(profile.id)]), default=False)
            result.append({'id': profile.id, 'name': profile.name, 'key': profile.account_key,
                           'mode': profile.execution_mode, 'state': state, 'tone': tone,
                           'last_action': fields.Datetime.to_string(last) if last else False,
                           'paused_until': fields.Datetime.to_string(min(weekly.mapped('paused_until')))
                           if weekly else False})
        return result

    def _queue_item_domain(self, filters):
        return self._scope_domain({k: v for k, v in filters.items() if k in ('profile_ids', 'execution_mode')})

    def _waiting_domain(self, filters):
        """Prospects with writing waiting for Claude: an analysis, a handoff, or a
        step or follow-up that is due."""
        now = fields.Datetime.now()
        return self._scope_domain(filters) + [
            ('do_not_contact', '=', False),
            '|', '|', '|', ('needs_analysis', '=', True), ('handoff_pending', '=', True),
            '&', '&', ('next_message_date', '<=', now), ('is_taken_over', '=', False), ('stage', 'in', ('accepted', 'messaged', 'replied')),
            '&', ('next_followup_date', '<=', now), ('is_taken_over', '=', False)]

    def _queue(self, filters):
        WorkItem = self.env['li.work.item']
        base = self._queue_item_domain(filters)
        today = self._today_start()
        waiting = self.env['li.prospect'].search_count(self._waiting_domain(filters))
        ideas = self.env['li.post'].search_count(self._post_domain(filters) + [('state', '=', 'idea')])
        queued_domain = base + [('state', '=', 'queued')]
        queued = WorkItem.search(queued_domain, order='id asc')
        next_window = False
        if queued:
            first = queued[0]
            next_window = self.env['li.mcp.tools']._window_text(first.persona_id, self.env['li.mcp.tools']._agent_of(first))
        sent = self._rows(self._scope_domain(filters) + [('date', '>=', today),
                                                          ('event_type', 'in', ('invite_sent', 'message_sent',
                                                                                'followup_sent'))], ['count(*)'])
        stale = WorkItem.search_count(base + [('discarded_stale', '=', True), ('date_done', '>=', today)])
        return {'writing_waiting': waiting + ideas, 'writing_prospects': waiting, 'post_ideas': ideas,
                'approved_waiting': len(queued), 'next_window': next_window,
                'sent_today': sent[0][0] if sent else 0, 'stale_today': stale}

    def _last_run(self, filters):
        visible = self.env['li.profile'].search(self._profile_domain(filters))
        runs = self.env['li.claude.run'].sudo().search([], limit=20)
        for run in runs:
            if not run.linkedin_profile_ids or run.linkedin_profile_ids & visible:
                return {'date': fields.Datetime.to_string(run.date),
                        'profiles': ', '.join((run.linkedin_profile_ids & visible).mapped('name')) or '',
                        'written': run.written, 'done': run.done, 'errors': run.errors,
                        'error_text': run.error_text or '', 'summary': run.summary or ''}
        return False

    def _post_domain(self, filters):
        domain = []
        if filters.get('profile_ids'):
            domain.append(('linkedin_profile_id', 'in', [int(i) for i in filters['profile_ids']]))
        if filters.get('execution_mode') in ('engine', 'chrome'):
            domain.append(('linkedin_profile_id.execution_mode', '=', filters['execution_mode']))
        if filters.get('service_ids'):
            domain.append(('service_id', 'in', [int(i) for i in filters['service_ids']]))
        return domain

    def _post_published_domain(self, filters, start, end):
        domain = self._post_domain(filters) + [('state', '=', 'published'), ('published_at', '<', end)]
        if start:
            domain.append(('published_at', '>=', start))
        return domain

    def _post_kpis(self, filters, start, end):
        query = self.env['li.post']._search(self._post_published_domain(filters, start, end))
        self.env.cr.execute(SQL('SELECT count(*), COALESCE(sum(%s), 0), COALESCE(sum(%s), 0), COALESCE(sum(%s), 0) '
                                'FROM %s WHERE %s', SQL.identifier('li_post', 'reactions'),
                                SQL.identifier('li_post', 'comments'), SQL.identifier('li_post', 'reposts'),
                                query.from_clause, query.where_clause))
        published, reactions, comments, reposts = self.env.cr.fetchone()
        to_approve = self.env['li.post'].search_count(self._post_domain(filters) + [('state', '=', 'draft')])
        return {'published': published, 'reactions': reactions, 'comments': comments, 'reposts': reposts,
                'to_approve': to_approve}

    # ------------------------------------------------------------------
    # Prospects map
    # ------------------------------------------------------------------
    MAP_GROUPS = {
        'hot': ('warm', 'meeting'),
        'engaged': ('accepted', 'messaged', 'replied'),
        'pipeline': ('queued', 'invited', 'followed'),
    }
    MAP_MAX_PLACES = 3000

    def _map_domain(self, filters):
        return self._scope_domain(filters) + [('geo_place', '!=', False)]

    def _map(self, filters):
        """Prospects per map place (one statement), with how many are hot,
        engaged or in the pipeline. Not date-filtered: where the prospects are."""
        query = self.env['li.prospect']._search(self._map_domain(filters))
        col = lambda name: SQL.identifier('li_prospect', name)
        groups = [SQL('count(*) FILTER (WHERE %s IN %s)', col('stage'), stages) for stages in self.MAP_GROUPS.values()]
        self.env.cr.execute(SQL('SELECT %s, %s, %s, count(*), %s FROM %s WHERE %s GROUP BY 1, 2, 3 '
                                'ORDER BY 4 DESC LIMIT %s', col('geo_lat'), col('geo_lng'), col('geo_place'),
                                SQL(', ').join(groups), query.from_clause, query.where_clause, self.MAP_MAX_PLACES))
        places = []
        for lat, lng, place, count, hot, engaged, pipeline in self.env.cr.fetchall():
            # the largest group colours the spot (ties go to the hotter one)
            closed = count - hot - engaged - pipeline
            tone = max((hot, 3, 'hot'), (engaged, 2, 'engaged'), (pipeline, 1, 'pipeline'), (closed, 0, 'closed'))[2]
            places.append({'lat': lat, 'lng': lng, 'place': place, 'count': count, 'hot': hot,
                           'engaged': engaged, 'pipeline': pipeline, 'tone': tone})
        total = self.env['li.prospect'].search_count(self._scope_domain(filters))
        located = sum(p['count'] for p in places)
        self.env.cr.execute(SQL('SELECT count(DISTINCT %s) FROM %s WHERE %s', col('geo_country'),
                                query.from_clause, query.where_clause))
        return {'places': places, 'located': located, 'total': total, 'countries': self.env.cr.fetchone()[0]}

    @api.model
    def get_map_place(self, lat, lng, filters=None, limit=12):
        """The prospects of one map place, for the popup."""
        filters = dict(filters or {})
        self.env.flush_all()
        domain = self._map_domain(filters) + [('geo_lat', '=', lat), ('geo_lng', '=', lng)]
        Prospect = self.env['li.prospect']
        stages = dict(Prospect._fields['stage']._description_selection(self.env))
        prospects = Prospect.search(domain, order='last_activity_date desc', limit=limit)
        return {
            'count': Prospect.search_count(domain),
            'prospects': [{'id': p.id, 'name': p.name, 'headline': p.headline or p.title or '',
                           'company': p.company or '', 'location': p.location or '', 'stage': p.stage,
                           'stage_label': stages.get(p.stage, p.stage), 'persona': p.persona_id.name,
                           'url': p.linkedin_url} for p in prospects],
        }

    def _map_action(self, filters, lat, lng):
        return {'type': 'ir.actions.act_window', 'name': _('Prospects'), 'res_model': 'li.prospect',
                'views': [(False, 'list'), (False, 'kanban'), (False, 'form')],
                'domain': self._map_domain(filters) + [('geo_lat', '=', lat), ('geo_lng', '=', lng)]}

    @api.model
    def get_map_action(self, lat, lng, filters=None):
        return self._map_action(dict(filters or {}), lat, lng)

    def _options(self):
        return {
            'profiles': [{'id': p.id, 'name': p.name} for p in self.env['li.profile'].search([])],
            'personas': [{'id': p.id, 'name': p.name, 'profile_id': p.linkedin_profile_id.id}
                         for p in self.env['li.persona'].search([])],
            'services': [{'id': s.id, 'name': s.name} for s in self.env['li.service'].search([])],
        }

    # ------------------------------------------------------------------
    # Drill-down: the list behind a tile, with the same filters
    # ------------------------------------------------------------------
    EVENT_KPIS = {
        'connections_sent': 'invite_sent', 'connections_per_day': 'invite_sent',
        'messages_sent': 'message_sent', 'meetings_booked': 'meeting_booked',
        'followups_sent': 'followup_sent', 'warm_lead_rate': 'warm_lead', 'meeting_rate': 'meeting_booked',
    }

    OPERATION_KPIS = ('writing_waiting', 'approved_waiting', 'sent_today', 'stale_today', 'posts_published',
                      'posts_to_approve')

    def _operation_action(self, kpi, filters):
        today = self._today_start()
        if kpi == 'writing_waiting':
            return {'type': 'ir.actions.act_window', 'name': _('Waiting for Claude'), 'res_model': 'li.prospect',
                    'views': [(False, 'list'), (False, 'form')], 'domain': self._waiting_domain(filters)}
        if kpi in ('approved_waiting', 'stale_today'):
            domain = self._queue_item_domain(filters) + (
                [('state', '=', 'queued')] if kpi == 'approved_waiting'
                else [('discarded_stale', '=', True), ('date_done', '>=', today)])
            return {'type': 'ir.actions.act_window', 'name': _('Work items'), 'res_model': 'li.work.item',
                    'views': [(False, 'list'), (False, 'form')], 'domain': domain}
        if kpi == 'sent_today':
            return {'type': 'ir.actions.act_window', 'name': _('Sent today'), 'res_model': 'li.event',
                    'views': [(False, 'list'), (False, 'form')],
                    'domain': self._scope_domain(filters) + [('date', '>=', today), ('event_type', 'in', (
                        'invite_sent', 'message_sent', 'followup_sent'))]}
        start, end = self._date_range(filters)
        domain = (self._post_published_domain(filters, start, end) if kpi == 'posts_published'
                  else self._post_domain(filters) + [('state', '=', 'draft')])
        return {'type': 'ir.actions.act_window', 'name': _('Posts'), 'res_model': 'li.post',
                'views': [(False, 'list'), (False, 'form')], 'domain': domain}

    @api.model
    def get_action(self, kpi, filters=None):
        filters = dict(filters or {})
        domain = self._event_domain(filters)
        if kpi in self.EVENT_KPIS:
            return {
                'type': 'ir.actions.act_window', 'name': _('LinkedIn events'), 'res_model': 'li.event',
                'views': [(False, 'list'), (False, 'form')],
                'domain': domain + [('event_type', '=', self.EVENT_KPIS[kpi])],
            }
        if kpi in self.OPERATION_KPIS:
            return self._operation_action(kpi, filters)
        if kpi == 'overdue_replies':
            prospect_domain = self._overdue_domain(filters)
        elif kpi == 'acceptance_rate':
            prospect_domain = [('id', 'in', self._cohort_ids(filters, domain, 'invite_sent', 'invite_accepted'))]
        elif kpi == 'reply_rate':
            prospect_domain = [('id', 'in', self._cohort_ids(filters, domain, 'message_sent', 'reply_received'))]
        elif kpi == 'followup_reply_rate':
            prospect_domain = [('id', 'in', self._followup_reply_ids(filters, domain))]
        else:
            raise ValueError('Unknown KPI %s' % kpi)
        return {
            'type': 'ir.actions.act_window', 'name': _('Prospects'), 'res_model': 'li.prospect',
            'views': [(False, 'list'), (False, 'kanban'), (False, 'form')],
            'domain': prospect_domain,
        }
