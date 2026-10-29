from datetime import timedelta

from odoo import fields
from odoo.tests import BaseCase, freeze_time, tagged

from .test_background import MONDAY_10_UTC, BackgroundCase
from ..models.li_geo import place_in_target, understand_place
from ..models.li_targeting import names_found, title_found, title_patterns


def people_data(*people):
    """A LinkedIn people search answer: (username, name, headline, location)."""
    lines, refs = [], []
    for username, name, headline, location in people:
        lines += [name, '• 2nd', headline, location]
        refs.append({'kind': 'person', 'url': '/in/%s/' % username, 'text': name})
    return {'data': {'url': 'https://www.linkedin.com/search/results/people/',
                     'sections': {'search_results': '\n'.join(lines)}, 'references': {'search_results': refs}}}


US_GEO = {'data': {'status': 'ok', 'query': 'United States', 'candidates': [
    {'id': '105080838', 'name': 'New York, United States'},
    {'id': '103644278', 'name': 'United States'}]}}


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestPlacesAndTitles(BaseCase):
    """Locations typed any way, and job titles found as whole words."""

    def test_country_typed_any_way(self):
        for text in ('USA', 'America', 'United state of america', 'U.S.A.', 'the US', 'United States',
                     'Untied States'):
            place = understand_place(text)
            self.assertEqual((place['country'], place['precision']), ('US', 'country'), text)
        self.assertTrue(understand_place('Untied States')['guessed'])
        self.assertFalse(understand_place('USA')['guessed'])

    def test_cities_and_regions(self):
        self.assertEqual(understand_place('Dubai')['precision'], 'city')
        self.assertEqual(understand_place('NYC')['label'].split(',')[0], 'New York City')
        self.assertEqual(understand_place('California')['precision'], 'region')
        self.assertEqual(understand_place('Londn')['label'].split(',')[0], 'London')
        self.assertIsNone(understand_place('Remote'))

    def test_people_inside_or_outside_a_target(self):
        def target(text):
            place = understand_place(text)
            return dict(place, region=place['region'])
        usa, dubai, california = target('USA'), target('Dubai'), target('California')
        inside = lambda where, t: place_in_target(where, [t])[0]
        self.assertFalse(inside('Lahore, Punjab, Pakistan', usa))
        self.assertTrue(inside('Austin, Texas, United States', usa))
        self.assertTrue(inside('San Francisco Bay Area', usa))
        self.assertFalse(inside('Toronto, Ontario, Canada', usa))
        self.assertTrue(inside('Greater Dubai Area', dubai))
        self.assertFalse(inside('Abu Dhabi, United Arab Emirates', dubai))
        self.assertFalse(inside('United Arab Emirates', dubai))          # a country only: not this city
        self.assertTrue(inside('Los Angeles Metropolitan Area', california))
        self.assertFalse(inside('New York City Metropolitan Area', california))
        self.assertFalse(inside('', usa))                                 # unknown: never assumed inside
        self.assertTrue(place_in_target('Springfield Hub', [{'text': 'Springfield Hub'}])[0])

    def test_job_titles_as_whole_words(self):
        patterns = title_patterns('Founders, Owners, CEO, Head of Operations')
        self.assertEqual(title_found('Co-Founder & CTO at Brand X', patterns), 'Founders')
        self.assertEqual(title_found('Business Owner | Retail', patterns), 'Owners')
        self.assertEqual(title_found('Chief Executive Officer, Acme', patterns), 'CEO')
        self.assertEqual(title_found('Head of Operations at Shopify brand', patterns), 'Head of Operations')
        self.assertEqual(title_found('I help founders scale their teams', patterns), '')   # "founders" ≠ a role
        self.assertEqual(title_found('Software Engineer at Google', patterns), '')
        self.assertEqual(title_found('Operations Manager', patterns), '')
        self.assertEqual(title_found('Product Owner at a bank', title_patterns('CEO')), '')

    def test_company_names(self):
        self.assertEqual(names_found('Founder at Acme Automation LLC', ['Acme Automation']), 'Acme Automation')
        self.assertEqual(names_found('Founder at Acmeautomation', ['Acme Automation']), '')


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestTargeting(BackgroundCase):
    """Only the persona's people are invited, and never too many."""

    def _tag(self, name):
        Tag = self.env['li.target.tag']
        return Tag.search([('name', '=', name), ('kind', '=', 'location')]) or Tag.create(
            {'name': name, 'kind': 'location'})

    # ------------------------------------------------------------------
    # Locations: LinkedIn's own location filter
    # ------------------------------------------------------------------
    def test_location_tag_understood_and_reset_on_rename(self):
        tag = self._tag('United state of america')
        self.assertEqual((tag.geo_country, tag.geo_precision), ('US', 'country'))
        self.assertIn('United state of america → ', tag.geo_summary)
        tag.write({'linkedin_geo_id': '103644278', 'linkedin_geo_name': 'United States'})
        self.assertIn('LinkedIn filter: United States (103644278)', tag.geo_summary)
        tag.name = 'Dubai'
        self.assertEqual((tag.geo_precision, tag.linkedin_geo_id), ('city', False))
        persona = self._persona(run=(), location_ids=[(6, 0, tag.ids)])
        self.assertIn('Dubai → Dubai', persona.location_summary)

    @freeze_time(MONDAY_10_UTC)
    def test_search_uses_linkedin_location_and_title_filters_and_checks_everyone(self):
        self._start()
        usa = self._tag('USA')
        persona = self._persona(job_titles='Founders, Owners', location_ids=[(6, 0, usa.ids)],
                                exclude_companies='Acme Automation', fit_check=False)
        self._script(lookup_location=[US_GEO], search_people_filtered=[people_data(
            ('ali-raza', 'Ali Raza', 'Founder at Brand X', 'Austin, Texas, United States'),
            ('bilal', 'Bilal Khan', 'Founder at Lahore Foods', 'Lahore, Punjab, Pakistan'),
            ('sam', 'Sam Lee', 'Software Engineer at Google', 'San Francisco Bay Area'),
            ('rival', 'Rita Val', 'Founder at Acme Automation', 'New York, United States'),
            ('owner', 'Olga Owens', 'Business Owner | Bakery', 'Chicago, Illinois, United States'),
            ('nowhere', 'No Where', 'Founder at Mystery', ''))])
        self._run()
        lookup = self._calls(tool='lookup_location')
        self.assertEqual(lookup, [{'tool': 'lookup_location', 'args': {'query': 'United States'}}])
        self.assertEqual((usa.linkedin_geo_id, usa.linkedin_geo_name), ('103644278', 'United States'))
        search = self._calls(tool='search_people_filtered')[0]['args']
        self.assertEqual((search['geo_ids'], search['title'], search['network'], search['page']),
                         (['103644278'], 'Founders', ['S', 'O'], 1))
        queued = self.env['li.prospect'].search([('persona_id', '=', persona.id)])
        self.assertEqual(sorted(queued.mapped('linkedin_username')), ['ali-raza', 'owner'])
        self.assertIn('location United States, title Founders', queued.filtered(lambda p: p.linkedin_username == 'ali-raza').fit_reason)
        detail = self._actions(action='search').detail
        self.assertIn('4 outside the persona', detail)
        self.assertIn('Bilal Khan: location "Lahore, Punjab, Pakistan" is outside', detail)
        self.assertIn('Rita Val: works at Acme Automation', detail)
        self.assertIn('Sam Lee: no Founders / Owners', detail)
        # the next search asks for the next job title
        persona.connection_agent_id.last_search_date = fields.Datetime.now() - timedelta(hours=2)
        queued.write({'stage': 'invited'})
        self._run()
        self.assertEqual(self._calls(tool='search_people_filtered')[-1]['args']['title'], 'Owners')

    @freeze_time(MONDAY_10_UTC)
    def test_location_linkedin_does_not_know_is_reported(self):
        self._start()
        tag = self._tag('Dubai')
        self._persona(location_ids=[(6, 0, tag.ids)])
        self._script(lookup_location=[{'data': {'status': 'ok', 'query': 'Dubai', 'candidates': [
            {'id': '1', 'name': 'Dubai, Georgia'}]}}])        # a place of the same name elsewhere: not taken
        self._run()
        self.assertFalse(tag.linkedin_geo_id)
        self.assertIn('enter the LinkedIn location ID by hand', tag.geo_lookup_note)
        # still searched, and still checked person by person
        self.assertEqual(len(self._calls(tool='search_people_filtered')), 1)
        self.assertNotIn('geo_ids', self._calls(tool='search_people_filtered')[0]['args'])

    @freeze_time(MONDAY_10_UTC)
    def test_old_engine_falls_back_to_plain_search_and_still_filters(self):
        self._start()
        usa = self._tag('USA')
        usa.linkedin_geo_id = '103644278'
        persona = self._persona(job_titles='Founder', location_ids=[(6, 0, usa.ids)], fit_check=False)
        self._script(search_people_filtered=[{'error': 'Unknown tool: search_people_filtered'}],
                     search_people=[people_data(
                         ('ali-raza', 'Ali Raza', 'Founder at Brand X', 'Austin, Texas, United States'),
                         ('bilal', 'Bilal Khan', 'Founder at Lahore Foods', 'Lahore, Punjab, Pakistan'))])
        self._run()
        self.assertEqual(self._calls(tool='search_people')[0]['args'], {'keywords': 'Founder'})
        self.assertEqual(self.env['li.prospect'].search([('persona_id', '=', persona.id)]).mapped('linkedin_username'),
                         ['ali-raza'])

    @freeze_time(MONDAY_10_UTC)
    def test_own_search_url_is_used_with_paging(self):
        self._start()
        url = 'https://www.linkedin.com/search/results/people/?geoUrn=%5B%22103644278%22%5D&keywords=founder'
        self._persona(search_url=url)
        self._run()
        self.assertEqual(self._calls(tool='search_people_filtered')[0]['args'], {'url': url, 'page': 1})

    # ------------------------------------------------------------------
    # Fit check by Claude before any invitation
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_fit_check_decides_who_is_invited(self):
        self._start()
        persona = self._persona(job_titles='Founder', exclude_companies='Acme Automation')
        self._script(search_people_filtered=[people_data(
            ('ali-raza', 'Ali Raza', 'Founder at Brand X (fashion, Shopify)', 'Lahore'),
            ('ai-guy', 'Ai Guy', 'Founder at AI Automation Agency', 'Lahore'))])
        self._run()
        people = self.env['li.prospect'].search([('persona_id', '=', persona.id)])
        self.assertEqual(set(people.mapped('stage')), {'screening'})
        self.assertFalse(self._calls(tool='connect_with_person'))       # nobody invited before the check
        items = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'screen']
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item['report_with'], 'li_record_fit')
        self.assertEqual(item['criteria']['job_titles'], 'Founder')
        self.assertEqual(item['criteria']['exclude_companies'], 'Acme Automation')
        self.assertEqual({p['name'] for p in item['people']}, {'Ali Raza', 'Ai Guy'})
        ali = people.filtered(lambda p: p.linkedin_username == 'ali-raza')
        rival = people - ali
        result = self.call('li_record_fit', work_id=item['work_id'], decisions=[
            {'prospect_id': ali.id, 'invite': True, 'reason': 'fashion brand founder'},
            {'prospect_id': rival.id, 'invite': False, 'reason': 'sells automation: a competitor'}])
        self.assertEqual((result['to_invite'], result['not_a_fit']), (1, 1))
        self.assertEqual((ali.stage, rival.stage), ('queued', 'unfit'))
        self.assertIn('competitor', rival.fit_reason)
        self.assertTrue(rival.is_closed if hasattr(rival, 'is_closed') else rival.stage == 'unfit')
        self.assertFalse([i for i in self.call('li_get_work', linkedin_profile='taha')['items']
                          if i['type'] == 'screen'])
        self._run()
        self.assertEqual([c['args']['linkedin_username'] for c in self._calls(tool='connect_with_person')],
                         ['ali-raza'])
        self.assertEqual(rival.stage, 'unfit')

    def test_repair_checks_people_queued_before(self):
        usa = self._tag('USA')
        persona = self._persona(run=(), job_titles='Founder', location_ids=[(6, 0, usa.ids)])
        good = self._prospect(persona, 'good', 'Good One', headline='Founder at X', location='Austin, Texas, United States')
        wrong_place = self._prospect(persona, 'pk', 'Pk One', headline='Founder at Y', location='Karachi, Pakistan')
        wrong_job = self._prospect(persona, 'eng', 'Eng One', headline='Engineer', location='Boston, MA, United States')
        self.env['li.prospect']._li_check_queued_fit(force=True)
        self.assertEqual((good.stage, wrong_place.stage, wrong_job.stage), ('screening', 'unfit', 'unfit'))
        self.assertIn('outside', wrong_place.fit_reason)

    # ------------------------------------------------------------------
    # Never too many invitations from one account
    # ------------------------------------------------------------------
    def _log_invites(self, count, persona=None, when=None):
        Action = self.env['li.engine.action']
        for i in range(count):
            prospect = self._prospect(persona or self._persona('Logged %s' % i, run=()), 'logged-%s-%s' % (
                count, i), stage='invited')
            Action.create({'linkedin_profile_id': self.profile.id, 'action': 'invite', 'status': 'ok',
                           'prospect_id': prospect.id, 'persona_id': prospect.persona_id.id,
                           'date': when or fields.Datetime.now()})

    @freeze_time(MONDAY_10_UTC)
    def test_account_daily_cap_covers_all_personas_and_every_try(self):
        self._start()
        self.profile.invite_daily_cap = 3
        first = self._persona('First', con_daily_limit=15, fit_check=False)
        second = self._persona('Second', con_daily_limit=15, fit_check=False)
        for persona in (first, second):
            for i in range(4):
                self._prospect(persona, '%s-%s' % (persona.id, i), 'Person %s' % i)
        # LinkedIn answers "pending" every time: the persona quota is given back, but each try still counts
        self._script(connect_with_person=[{'data': {'status': 'pending', 'message': 'Pending.'}}] * 8)
        for _round in range(8):
            self._run()
        tried = {c['args']['linkedin_username'] for c in self._calls(tool='connect_with_person')}
        self.assertEqual(len(tried), 3)
        self.assertEqual(self.profile._invites_left()[0], 0)
        self.assertIn('account limit of 3 invitations today', self.profile._invites_left()[1])

    @freeze_time(MONDAY_10_UTC)
    def test_account_weekly_cap_applies_when_persona_weekly_is_zero(self):
        self._start()
        self.profile.write({'invite_daily_cap': 50, 'invite_weekly_cap': 5})
        persona = self._persona(con_daily_limit=15, con_weekly_limit=0, fit_check=False)
        self._log_invites(5, when=fields.Datetime.now() - timedelta(days=3))
        self._prospect(persona)
        self._run()
        self.assertFalse(self._calls(tool='connect_with_person'))
        self.assertIn('7 days', self.profile._invites_left()[1])
        # a week later there is room again
        with freeze_time('2026-10-16 10:01:00'):
            self.assertEqual(self.profile._invites_left()[0], 5)

    @freeze_time(MONDAY_10_UTC)
    def test_persona_daily_limit_counts_every_try(self):
        self._start()
        self.profile.invite_daily_cap = 50
        persona = self._persona(con_daily_limit=2, fit_check=False)
        for i in range(5):
            self._prospect(persona, 'p-%s' % i, 'Person %s' % i)
        self._script(connect_with_person=[{'data': {'status': 'pending', 'message': 'Pending.'}}] * 5)
        for _round in range(6):
            self._run()
        self.assertEqual(len({c['args']['linkedin_username'] for c in self._calls(tool='connect_with_person')}), 2)

    # ------------------------------------------------------------------
    # Chat Agent: why nobody gets a message
    # ------------------------------------------------------------------
    @freeze_time(MONDAY_10_UTC)
    def test_get_work_says_why_nobody_is_messaged(self):
        persona = self._persona(run=('chat',))
        self._prospect(persona, 'inv', 'Invited One', stage='invited')
        unread = self._accepted(persona, username='unread', name='Unread One', profile_text=False,
                                profile_read_at=False)
        later = self._accepted(persona, username='later', name='Later One')
        persona.chat_agent_id.first_message_delay = 6
        result = self.call('li_get_work', linkedin_profile='taha')
        self.assertFalse([i for i in result['items'] if i['type'] == 'message'])
        waiting = result['chat_waiting']
        why = {p['name']: p['why'] for p in waiting['people']}
        self.assertIn('profile is read first', why['Unread One'])
        self.assertIn('due at', why['Later One'])
        self.assertTrue(any('1 invited people have not accepted yet' in line for line in waiting['personas']))
        self.assertIn('chat_waiting', result['message'])
        self.assertTrue(unread and later)

    def test_chat_agent_warns_when_first_step_waits_for_a_reply(self):
        persona = self._persona(run=())
        persona.chat_agent_id.step_ids.filtered(lambda s: s.sequence == 1).trigger = 'after_reply'
        answer = persona.action_chat_run()
        self.assertEqual(answer['tag'], 'display_notification')
        self.assertIn('After accept', answer['params']['message'])
        self.assertEqual(persona.chat_agent_id.state, 'running')

    @freeze_time(MONDAY_10_UTC)
    def test_accepted_people_never_messaged_come_first(self):
        persona = self._persona(run=('chat',))
        busy = self._accepted(persona, username='busy', name='Busy One')
        busy.write({'stage': 'messaged', 'date_first_message': fields.Datetime.now() - timedelta(days=3),
                    'current_step_id': persona.chat_agent_id.step_ids.sorted('sequence')[:1].id})
        busy.last_activity_date = fields.Datetime.now() - timedelta(days=30)
        new = self._accepted(persona, username='new', name='New One')
        new.last_activity_date = fields.Datetime.now()
        # set to Accepted by hand: no acceptance date, still written to
        manual = self._prospect(persona, 'manual', 'Manual One', stage='accepted', profile_text='Founder at Y',
                                profile_read_at=fields.Datetime.now(),
                                date_invited=fields.Datetime.now() - timedelta(days=2))
        queue = self.Tools._chat_queue([('persona_id', '=', persona.id), ('stage', 'in', ('accepted', 'messaged'))])
        self.assertEqual(queue[:2], new | manual)
        self.assertEqual(queue[2:], busy)
        items = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'message']
        self.assertEqual({i['prospect']['id'] for i in items[:2]}, {new.id, manual.id})

    def test_chat_waiting_names_a_stopped_chat_agent(self):
        persona = self._persona(run=())
        self._accepted(persona)
        waiting = self.Tools._chat_waiting(self.profile)
        self.assertTrue(any('1 accepted people never got a message' in line for line in waiting['personas']))
