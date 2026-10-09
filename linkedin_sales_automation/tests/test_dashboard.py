from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo.tests import freeze_time, tagged

from .common import LiTransactionCase

NOW = datetime(2026, 10, 20, 12, 0, 0)  # UTC; 17:00 in Karachi


def utc(day, hour=10, minute=0):
    return datetime(2026, 10, day, hour, minute)


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
@freeze_time(NOW)
class TestDashboard(LiTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service2 = cls.env['li.service'].create({'name': 'Bookkeeping', 'description': 'Books.'})
        cls.p1 = cls._make_persona('PK founders', profile=cls.profile)
        cls.p2 = cls._make_persona('UK owners', profile=cls.profile2, service_id=cls.service2.id)
        cls.p1.date_activated = datetime(2026, 10, 1, 9, 0)
        cls.p2.date_activated = datetime(2026, 10, 10, 9, 0)
        Prospect = cls.env['li.prospect']
        mk = lambda persona, key: Prospect.create({'name': key.upper(), 'persona_id': persona.id,
                                                   'linkedin_url': 'https://www.linkedin.com/in/dash-%s/' % key})
        cls.pr = {k: mk(cls.p1, k) for k in 'abcd'}
        cls.pr.update({k: mk(cls.p2, k) for k in 'ef'})
        # (event_type, agent_type, persona, prospect key, date UTC)
        cls.fixture = [
            ('invite_sent', 'connection', cls.p1, 'a', utc(18, 10)),
            ('invite_sent', 'connection', cls.p1, 'b', utc(18, 11)),
            ('invite_sent', 'connection', cls.p1, 'c', utc(19, 9)),
            ('invite_sent', 'connection', cls.p1, 'd', utc(5, 9)),
            ('invite_sent', 'connection', cls.p2, 'e', utc(19, 8)),
            ('invite_sent', 'connection', cls.p2, 'f', utc(19, 19, 30)),  # 20 Oct 00:30 in Karachi
            ('invite_accepted', 'connection', cls.p1, 'd', utc(6, 9)),
            ('invite_accepted', 'connection', cls.p1, 'a', utc(19, 10)),
            ('invite_accepted', 'connection', cls.p2, 'e', utc(20, 8)),
            ('message_sent', 'chat', cls.p1, 'a', utc(19, 11)),
            ('message_sent', 'chat', cls.p1, 'd', utc(7, 9)),
            ('message_sent', 'chat', cls.p2, 'e', utc(20, 9)),
            ('followup_sent', 'followup', cls.p1, 'a', utc(19, 12)),
            ('followup_sent', 'followup', cls.p2, 'e', utc(20, 10)),
            ('reply_received', 'chat', cls.p1, 'a', utc(20, 9)),
            ('reply_received', 'chat', cls.p1, 'a', utc(20, 9, 30)),
            ('reply_received', 'chat', cls.p1, 'd', utc(8, 9)),
            ('warm_lead', 'chat', cls.p1, 'a', utc(20, 10)),
            ('meeting_booked', 'system', cls.p1, 'a', utc(20, 11)),
            ('agent_started', 'connection', cls.p1, None, utc(1, 9)),
        ]
        Event = cls.env['li.event'].sudo()
        for event_type, agent_type, persona, key, date in cls.fixture:
            Event.create({'event_type': event_type, 'agent_type': agent_type, 'persona_id': persona.id,
                          'linkedin_profile_id': persona.linkedin_profile_id.id,
                          'service_id': persona.service_id.id, 'prospect_id': cls.pr[key].id if key else False,
                          'date': date})
        cls.dash = cls.env['li.dashboard'].with_context(tz='Asia/Karachi')

    # ------------------------------------------------------------------
    # independent "manual count" over the fixture list
    # ------------------------------------------------------------------
    def _bounds(self, filters, tz):
        zone = ZoneInfo(tz)
        today = NOW.replace(tzinfo=timezone.utc).astimezone(zone).date()
        to_utc = lambda d: datetime.combine(d, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
        end = to_utc(today + timedelta(days=1))
        preset = filters.get('date_preset', 'since_active')
        start = {
            'today': lambda: to_utc(today),
            'last_7': lambda: to_utc(today - timedelta(days=6)),
            'last_30': lambda: to_utc(today - timedelta(days=29)),
            'this_month': lambda: to_utc(today.replace(day=1)),
        }.get(preset)
        if start:
            return start(), end
        if preset == 'custom':
            return to_utc(filters['date_from']), to_utc(filters['date_to'] + timedelta(days=1))
        personas = [p for p in (self.p1, self.p2) if not filters.get('persona_ids') or p.id in filters['persona_ids']]
        personas = [p for p in personas if self._in_scope(p, dict(filters, persona_ids=None))]
        return min(p.date_activated for p in personas), end

    def _in_scope(self, persona, filters):
        return ((not filters.get('profile_ids') or persona.linkedin_profile_id.id in filters['profile_ids'])
                and (not filters.get('persona_ids') or persona.id in filters['persona_ids'])
                and (not filters.get('service_ids') or persona.service_id.id in filters['service_ids']))

    def _agent_ok(self, agent_type, filters):
        agent = filters.get('agent', 'both')
        return agent == 'both' or (agent_type == 'connection') == (agent == 'connection')

    def _manual(self, filters, tz='Asia/Karachi'):
        start, end = self._bounds(filters, tz)
        scoped = [e for e in self.fixture if self._in_scope(e[2], filters) and self._agent_ok(e[1], filters)]
        ranged = [e for e in scoped if start <= e[4] < end]
        count = lambda t: sum(1 for e in ranged if e[0] == t)
        prospects = lambda rows, t: {e[3] for e in rows if e[0] == t}
        invited = prospects(ranged, 'invite_sent')
        accepted = invited & prospects(scoped, 'invite_accepted')
        messaged = prospects(ranged, 'message_sent')
        replied = messaged & prospects(scoped, 'reply_received')
        first_followup = {}
        for e in ranged:
            if e[0] == 'followup_sent':
                first_followup[e[3]] = min(first_followup.get(e[3], e[4]), e[4])
        followed_replied = {k for k, d in first_followup.items()
                            if any(e[0] == 'reply_received' and e[3] == k and e[4] >= d for e in scoped)}
        days = {e[4].replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).date()
                for e in ranged if e[0] == 'invite_sent'}
        rate = lambda a, b: round(100.0 * a / b, 1) if b else 0.0
        return {
            'connections_sent': count('invite_sent'),
            'connections_per_day': round(count('invite_sent') / len(days), 1) if days else 0.0,
            'messages_sent': count('message_sent'),
            'acceptance_rate': rate(len(accepted), len(invited)),
            'reply_rate': rate(len(replied), len(messaged)),
            'warm_lead_rate': rate(count('warm_lead'), count('invite_accepted')),
            'meeting_rate': rate(count('meeting_booked'), count('warm_lead')),
            'meetings_booked': count('meeting_booked'),
            'followups_sent': count('followup_sent'),
            'followup_reply_rate': rate(len(followed_replied), len(first_followup)),
        }, {'accepted': accepted, 'replied': replied, 'followed_replied': followed_replied}

    def _check(self, filters, tz='Asia/Karachi'):
        data = self.env['li.dashboard'].with_context(tz=tz).get_data(filters)
        expected, _sets = self._manual(filters, tz)
        for key, value in expected.items():
            self.assertEqual(data['kpis'][key], value, '%s with %s' % (key, filters))
        return data

    # ------------------------------------------------------------------
    def test_kpis_match_manual_counts(self):
        combos = [
            {},
            {'date_preset': 'last_7'},
            {'date_preset': 'last_7', 'profile_ids': [self.profile.id]},
            {'date_preset': 'today', 'agent': 'connection'},
            {'date_preset': 'last_30', 'agent': 'chat', 'service_ids': [self.service.id]},
            {'date_preset': 'this_month', 'persona_ids': [self.p2.id]},
            {'date_preset': 'custom', 'date_from': datetime(2026, 10, 18).date(),
             'date_to': datetime(2026, 10, 19).date()},
        ]
        for filters in combos:
            payload = dict(filters)
            for key in ('date_from', 'date_to'):
                if key in payload:
                    payload[key] = str(payload[key])
            self._check_payload(filters, payload)

    def _check_payload(self, filters, payload):
        data = self.dash.get_data(payload)
        expected, _sets = self._manual(filters)
        for key, value in expected.items():
            self.assertEqual(data['kpis'][key], value, '%s with %s' % (key, filters))

    def test_explicit_values(self):
        data = self.dash.get_data({'date_preset': 'last_7'})
        kpis = data['kpis']
        self.assertEqual(kpis['connections_sent'], 5)          # a, b, c, e, f (d is 5 Oct)
        self.assertEqual(kpis['connections_per_day'], 1.7)     # 5 invites over 18, 19, 20 Oct (Karachi)
        # cohort: a and e of the 5 invited in range accepted (d accepted, but was invited earlier)
        self.assertEqual(kpis['acceptance_rate'], 40.0)
        self.assertEqual(kpis['reply_rate'], 50.0)             # messaged a, e; a replied (twice: one prospect)
        self.assertEqual(kpis['followup_reply_rate'], 50.0)    # a replied after its follow-up, e did not
        self.assertEqual(kpis['warm_lead_rate'], 50.0)         # 1 warm / 2 accepted in range
        self.assertEqual(kpis['meeting_rate'], 100.0)
        since_active = self.dash.get_data({})['kpis']
        self.assertEqual(since_active['connections_sent'], 6)
        self.assertEqual(since_active['acceptance_rate'], 50.0)  # a, d, e of 6
        funnel = {row['key']: row['value'] for row in data['funnel']}
        self.assertEqual(funnel, {'sent': 5, 'accepted': 2, 'replied': 1, 'warm': 1, 'meetings': 1})

    def test_cohort_acceptance_counts_later_acceptances(self):
        # invited inside the custom range, accepted after it: still counts
        data = self.dash.get_data({'date_preset': 'custom', 'date_from': '2026-10-18', 'date_to': '2026-10-18'})
        self.assertEqual(data['kpis']['connections_sent'], 2)   # a, b
        self.assertEqual(data['kpis']['acceptance_rate'], 50.0)  # a accepted on the 19th
        self.assertEqual(data['details']['accepted_of_invited'], 1)

    def test_time_zone_day_boundaries(self):
        # f was invited at 19:30 UTC on the 19th = 00:30 on the 20th in Karachi, 15:30 on the 19th in New York
        karachi = self.env['li.dashboard'].with_context(tz='Asia/Karachi').get_data({'date_preset': 'today'})
        new_york = self.env['li.dashboard'].with_context(tz='America/New_York').get_data({'date_preset': 'today'})
        self.assertEqual(karachi['kpis']['connections_sent'], 1)   # f
        self.assertEqual(new_york['kpis']['connections_sent'], 0)  # its "today" (20th NY) starts 04:00 UTC
        self._check({'date_preset': 'today'}, tz='America/New_York')
        self._check({'date_preset': 'last_7'}, tz='America/New_York')
        days = [row['date'] for row in karachi['daily']['rows']]
        self.assertEqual(days, ['2026-10-20'])
        week = self.dash.get_data({'date_preset': 'last_7'})['daily']['rows']
        self.assertEqual({r['date']: (r['sent'], r['accepted']) for r in week},
                         {'2026-10-18': (2, 0), '2026-10-19': (2, 1), '2026-10-20': (1, 1)})

    def test_drill_down_matches_tiles(self):
        for filters in ({'date_preset': 'last_7'}, {'date_preset': 'last_30', 'profile_ids': [self.profile.id]}, {}):
            data = self.dash.get_data(filters)
            _expected, sets = self._manual(filters)
            for kpi, value in (('connections_sent', data['kpis']['connections_sent']),
                               ('messages_sent', data['kpis']['messages_sent']),
                               ('meetings_booked', data['kpis']['meetings_booked']),
                               ('followups_sent', data['kpis']['followups_sent'])):
                action = self.dash.get_action(kpi, filters)
                self.assertEqual(self.env[action['res_model']].search_count(action['domain']), value, kpi)
            for kpi, key, detail in (('acceptance_rate', 'accepted', 'accepted_of_invited'),
                                     ('reply_rate', 'replied', 'replied_of_messaged'),
                                     ('followup_reply_rate', 'followed_replied', 'replied_after_followup')):
                action = self.dash.get_action(kpi, filters)
                found = self.env['li.prospect'].search(action['domain'])
                self.assertEqual(len(found), data['details'][detail], kpi)
                self.assertEqual(set(found.ids), {self.pr[k].id for k in sets[key]}, kpi)

    def test_already_connected_is_not_an_accepted_invite(self):
        before = self.dash.get_data({'date_preset': 'last_7'})
        Prospect, Tools = self.env['li.prospect'], self.env['li.mcp.tools']
        known = Prospect.create({'name': 'Known', 'persona_id': self.p1.id,
                                 'linkedin_url': 'https://www.linkedin.com/in/dash-known/'})
        self.assertTrue(Tools._accept(known, note='already a 1st-degree connection'))
        self.pr['b'].write({'stage': 'invited', 'date_invited': utc(18, 11)})
        self.assertTrue(Tools._accept(self.pr['b']))
        events = self.env['li.event'].sudo().search([('event_type', '=', 'invite_accepted')], order='id desc', limit=2)
        flags = {e.prospect_id: e.without_invite for e in events}
        self.assertTrue(flags[known])              # queued, never invited
        self.assertFalse(flags[self.pr['b']])      # invited by Odoo on the 18th
        after = self.dash.get_data({'date_preset': 'last_7'})
        # b (invited on the 18th) now accepted: 3 of the 5 invited; Known is not an accepted invite
        self.assertEqual(after['kpis']['acceptance_rate'], 60.0)
        self.assertEqual(after['details']['already_connected'], before['details']['already_connected'] + 1)
        funnel = {row['key']: row['value'] for row in after['funnel']}
        self.assertEqual(funnel['accepted'], 3)
        self.assertEqual(after['details']['connected'], 4)
        self.assertEqual(after['kpis']['warm_lead_rate'], 25.0)  # 1 warm of 4 connected
        rows = {r['name']: r for r in after['personas']}
        self.assertEqual(rows['PK founders']['invite_accepted'], 2)  # a and b, not Known
        self.assertEqual(sum(r['accepted'] for r in after['daily']['rows']), 3)

    def test_already_connected_backfill(self):
        Event = self.env['li.event'].sudo()
        known = self.env['li.prospect'].create({'name': 'Old', 'persona_id': self.p1.id,
                                                'linkedin_url': 'https://www.linkedin.com/in/dash-old/'})
        old = Event.create({'event_type': 'invite_accepted', 'agent_type': 'connection', 'persona_id': self.p1.id,
                            'prospect_id': known.id, 'date': utc(19, 9)})
        self.env.flush_all()
        self.env.cr.execute("UPDATE li_event SET without_invite = NULL WHERE event_type = 'invite_accepted'")
        Event.init()
        self.env.invalidate_all()
        accepted = Event.search([('event_type', '=', 'invite_accepted')])
        self.assertEqual(accepted.filtered('without_invite'), old)   # a, d, e were invited first

    def test_persona_table_and_record_rules(self):
        rows = {r['name']: r for r in self.dash.get_data({'date_preset': 'last_7'})['personas']}
        self.assertEqual((rows['PK founders']['invite_sent'], rows['UK owners']['invite_sent']), (3, 2))
        self.assertEqual(rows['PK founders']['reply_rate'], 100.0)
        # the sales rep owns only the first profile: SQL keeps the record rules
        rep_data = self.env['li.dashboard'].with_user(self.rep).with_context(tz='Asia/Karachi').get_data(
            {'date_preset': 'last_7'})
        self.assertEqual(rep_data['kpis']['connections_sent'], 3)
        self.assertEqual([r['name'] for r in rep_data['personas']], ['PK founders'])

    def test_overdue_replies_live(self):
        prospect = self.pr['a']
        activity = prospect.activity_schedule('mail.mail_activity_data_todo', user_id=self.rep.id)
        prospect.sudo().write({'reply_activity_id': activity.id, 'reply_due_at': NOW - timedelta(hours=1)})
        self.assertEqual(self.dash.get_data({'date_preset': 'today'})['kpis']['overdue_replies'], 1)
        action = self.dash.get_action('overdue_replies', {})
        self.assertEqual(self.env['li.prospect'].search(action['domain']), prospect)

    def test_meeting_booked_once(self):
        persona = self.p1
        prospect = self.pr['c']
        prospect.action_push_to_crm()
        lead = prospect.crm_lead_id
        Meeting = self.env['calendar.event']
        start = datetime(2026, 10, 22, 10, 0)
        Meeting.create({'name': 'Intro call', 'start': start, 'stop': start + timedelta(hours=1),
                        'opportunity_id': lead.id})
        self.assertEqual(prospect.stage, 'meeting')
        later = Meeting.create({'name': 'Follow-up call', 'start': start + timedelta(days=2),
                                'stop': start + timedelta(days=2, hours=1)})
        later.opportunity_id = lead.id
        events = self.env['li.event'].search([('crm_lead_id', '=', lead.id), ('event_type', '=', 'meeting_booked')])
        self.assertEqual(len(events), 1)
        self.assertEqual(events.persona_id, persona)
        self.assertIn('Meeting booked on', lead.message_ids.mapped('body')[0])

    def test_multi_company(self):
        company_b = self.env['res.company'].create({'name': 'LI Company B'})
        profile_b = self.env['li.profile'].create({
            'name': 'Company B profile', 'linkedin_url': 'https://www.linkedin.com/in/company-b/',
            'owner_id': self.manager.id, 'account_key': 'compb',
            'my_display_name': 'B Rep', 'company_id': company_b.id, 'connection_state': 'connected'})
        persona_b = self._make_persona('Company B persona', profile=profile_b)
        self.assertEqual(persona_b.company_id, company_b)
        prospect_b = self.env['li.prospect'].create({'name': 'B One', 'persona_id': persona_b.id,
                                                    'linkedin_url': 'https://www.linkedin.com/in/b-one/'})
        self.assertEqual(prospect_b.company_id, company_b)
        event = self.env['li.event']._log('invite_sent', 'connection', persona=persona_b, prospect=prospect_b,
                                          date=utc(19, 10))
        self.assertEqual(event.company_id, company_b)
        main = self.env.company
        self.manager.write({'company_ids': [(6, 0, (main | company_b).ids)]})
        dash = self.env['li.dashboard'].with_user(self.manager).with_context(tz='Asia/Karachi')
        only_main = dash.with_context(allowed_company_ids=main.ids).get_data({'date_preset': 'last_7'})
        both = dash.with_context(allowed_company_ids=(main | company_b).ids).get_data({'date_preset': 'last_7'})
        self.assertEqual(only_main['kpis']['connections_sent'], 5)
        self.assertEqual(both['kpis']['connections_sent'], 6)
        self.assertNotIn('Company B persona', [r['name'] for r in only_main['personas']])
        self.assertNotIn('Company B profile', [o['name'] for o in only_main['options']['profiles']])
        # the MCP tools serve every company; the pivot lead lands in the profile's company
        self.assertIn(company_b, self.env['li.mcp.token']._technical_user().company_ids)
        prospect_b.stage = 'accepted'
        lead = prospect_b._pivot('asked for a call')
        self.assertEqual(lead.company_id, company_b)
        names = [p['name'] for p in self.call('li_overview')['personas']]
        self.assertIn('Company B persona', names)
