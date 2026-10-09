from datetime import datetime

from odoo.tests import BaseCase, freeze_time, tagged

from .common import LiTransactionCase
from ..models.li_geo import geocode


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestGeocode(BaseCase):

    def test_linkedin_location_texts(self):
        cases = {
            'Lahore, Punjab, Pakistan': ('Lahore, PK', 'city'),
            'Greater London Area': ('London, GB', 'city'),
            'San Francisco Bay Area': ('San Francisco, US', 'city'),
            'London, Ontario, Canada': ('London, CA', 'city'),
            'Dallas-Fort Worth Metroplex': ('Dallas, US', 'city'),
            'Karachi Division, Sindh, Pakistan': ('Karachi, PK', 'city'),
            'Punjab, Pakistan': ('Punjab, PK', 'region'),
            'Pakistan': ('Pakistan', 'country'),
            'Bahrain': ('Bahrain', 'country'),
            'Paris, Île-de-France, France': ('Paris, FR', 'city'),
        }
        for text, (label, precision) in cases.items():
            found = geocode(text)
            self.assertTrue(found, text)
            self.assertEqual((found[2], found[3]), (label, precision), text)
        self.assertIsNone(geocode('Remote'))
        self.assertIsNone(geocode(''))
        lat, lng = geocode('Lahore, Punjab, Pakistan')[:2]
        self.assertAlmostEqual(lat, 31.56, places=1)
        self.assertAlmostEqual(lng, 74.35, places=1)


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestDashboardOperations(LiTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.persona = cls._make_persona('Map persona')
        cls.persona2 = cls._make_persona('Other persona', profile=cls.profile2)
        Prospect = cls.env['li.prospect']
        cls.lahore = Prospect.create([{
            'name': 'Lahore %s' % i, 'persona_id': cls.persona.id, 'location': 'Lahore, Punjab, Pakistan',
            'linkedin_url': 'https://www.linkedin.com/in/lahore-%s/' % i, 'stage': stage}
            for i, stage in enumerate(['warm', 'messaged', 'messaged', 'queued'])])
        cls.london = Prospect.create({'name': 'Londoner', 'persona_id': cls.persona2.id,
                                      'location': 'Greater London Area',
                                      'linkedin_url': 'https://www.linkedin.com/in/londoner/', 'stage': 'invited'})
        cls.nowhere = Prospect.create({'name': 'Nomad', 'persona_id': cls.persona.id, 'location': 'Remote',
                                       'linkedin_url': 'https://www.linkedin.com/in/nomad/'})
        cls.Dashboard = cls.env['li.dashboard']

    def test_prospects_are_located_when_the_location_is_set(self):
        self.assertEqual(self.lahore[0].geo_place, 'Lahore, PK')
        self.assertEqual(self.lahore[0].geo_country, 'PK')
        self.assertFalse(self.nowhere.geo_place)
        self.nowhere.location = 'Dubai, United Arab Emirates'
        self.assertEqual(self.nowhere.geo_place, 'Dubai, AE')

    def test_map_groups_places_in_sql(self):
        data = self.Dashboard.get_data({})['map']
        places = {p['place']: p for p in data['places']}
        lahore = places['Lahore, PK']
        self.assertEqual((lahore['count'], lahore['hot'], lahore['engaged'], lahore['pipeline']), (4, 1, 2, 1))
        self.assertEqual(lahore['tone'], 'engaged')                # the largest group colours the spot
        self.assertEqual(places['London, GB']['tone'], 'pipeline')
        self.assertEqual((data['located'], data['total'], data['countries']), (5, 6, 2))
        popup = self.Dashboard.get_map_place(lahore['lat'], lahore['lng'], {})
        self.assertEqual(popup['count'], 4)
        self.assertEqual({p['name'] for p in popup['prospects']}, set(self.lahore.mapped('name')))
        self.assertEqual(self.Dashboard.get_map_action(lahore['lat'], lahore['lng'], {})['res_model'], 'li.prospect')

    def test_map_follows_filters_and_record_rules(self):
        only_taha = self.Dashboard.get_data({'profile_ids': [self.profile.id]})['map']
        self.assertEqual([p['place'] for p in only_taha['places']], ['Lahore, PK'])
        as_rep = self.Dashboard.with_user(self.rep).get_data({})['map']     # rep owns taha only
        self.assertEqual([p['place'] for p in as_rep['places']], ['Lahore, PK'])
        self.profile2.execution_mode = 'engine'
        engine = self.Dashboard.get_data({'execution_mode': 'engine'})['map']
        self.assertEqual([p['place'] for p in engine['places']], ['London, GB'])

    @freeze_time('2026-10-12 10:00:00')
    def test_health_queue_last_run_and_posts(self):
        self.profile.execution_mode = 'chrome'
        self.profile2.write({'execution_mode': 'engine', 'connection_state': 'reconnect_needed'})
        WorkItem = self.env['li.work.item']
        queued = self.env['li.mcp.tools']._queue_send('invite', self.lahore[3])
        self.persona.action_connection_run()
        stale = self.env['li.mcp.tools']._queue_send('message', self.lahore[1], text='Hello')
        stale.write({'discarded_stale': True})
        stale._close('cancelled', cancel_reason='changed')
        self.lahore[2].write({'needs_analysis': True})
        self.env['li.event']._log('invite_sent', 'connection', persona=self.persona, prospect=self.lahore[3])
        self.env['li.claude.run'].create({'linkedin_profile_ids': [(6, 0, self.profile.ids)], 'written': 4,
                                          'done': 2, 'errors': 1, 'error_text': 'x'})
        self.env['li.post'].create({'name': 'P1', 'linkedin_profile_id': self.profile.id, 'state': 'draft',
                                    'text': 'Draft'})
        published = self.env['li.post'].create({'name': 'P2', 'linkedin_profile_id': self.profile.id,
                                                'text': 'Live', 'state': 'published'})
        published.sudo().write({'published_at': '2026-10-12 09:00:00', 'reactions': 12, 'comments': 3})
        data = self.Dashboard.get_data({'date_preset': 'today'})
        health = {h['key']: h for h in data['health']}
        self.assertEqual((health['taha']['state'], health['taha']['tone']), ('Connected', 'ok'))
        self.assertEqual((health['rep1']['state'], health['rep1']['tone']), ('Reconnect needed', 'bad'))
        queue = data['queue']
        self.assertEqual(queue['approved_waiting'], 1)
        self.assertEqual(queue['stale_today'], 1)
        self.assertEqual(queue['sent_today'], 1)
        self.assertEqual(queue['writing_prospects'], 1)
        self.assertEqual((data['last_run']['written'], data['last_run']['errors']), (4, 1))
        self.assertEqual(data['posts'], {'published': 1, 'reactions': 12, 'comments': 3, 'reposts': 0,
                                         'to_approve': 1})
        action = self.Dashboard.get_action('approved_waiting', {'date_preset': 'today'})
        self.assertEqual(WorkItem.search(action['domain']), queued)
        # weekly invite limit shows on the strip
        self.persona.connection_agent_id._pause_until(datetime(2026, 10, 19), 'weekly invitation limit')
        health = {h['key']: h for h in self.Dashboard.get_data({})['health']}
        self.assertEqual(health['taha']['state'], 'Paused – LinkedIn invite limit')
        # the mode filter keeps only engine profiles
        self.assertEqual([h['key'] for h in self.Dashboard.get_data({'execution_mode': 'engine'})['health']],
                         ['rep1'])

    def test_garbled_text_is_repaired(self):
        bad = lambda text: text.encode('utf-8').decode('latin-1')
        prospect = self.env['li.prospect'].create({
            'name': bad('Zoë Awan'), 'persona_id': self.persona.id, 'headline': bad('• 3rd+'),
            'location': bad('Lahore, Punjab, Pakistan • '), 'linkedin_url': 'https://www.linkedin.com/in/zoe-awan/'})
        self.assertEqual(self.env['li.prospect']._li_repair_mojibake() >= 1, True)
        self.assertEqual((prospect.name, prospect.headline), ('Zoë Awan', False))
        self.assertEqual(prospect.geo_place, 'Lahore, PK')
        self.assertEqual(self.env['li.prospect']._li_repair_mojibake(), 0)      # nothing left to fix

    def test_rep_sees_only_own_queue(self):
        self.env['li.mcp.tools']._queue_send('invite', self.london)
        self.assertEqual(self.Dashboard.get_data({})['queue']['approved_waiting'], 1)
        self.assertEqual(self.Dashboard.with_user(self.rep).get_data({})['queue']['approved_waiting'], 0)
