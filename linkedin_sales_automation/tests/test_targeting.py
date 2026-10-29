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
        # a state wins over a small town of the same name; a big city wins over its region
        for state in ('Florida', 'Virginia', 'Delaware', 'Texas'):
            self.assertEqual(understand_place(state)['label'], '%s, United States' % state)
        self.assertEqual(understand_place('Georgia, USA')['label'], 'Georgia, United States')
        self.assertEqual(understand_place('Dubai')['label'], 'Dubai, United Arab Emirates')

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
        replied = self._replied(persona, 'sunaan', 'Sunaan Mushtaq')
        queue = self.Tools._chat_queue([('persona_id', '=', persona.id),
                                        ('stage', 'in', ('accepted', 'messaged', 'replied'))])
        self.assertEqual(queue[:1], replied)                 # who replied comes first
        self.assertEqual(queue[1:3], new | manual)           # then first messages
        self.assertEqual(queue[3:], busy)
        items = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'message']
        self.assertEqual(items[0]['prospect']['id'], replied.id)
        self.assertEqual({i['prospect']['id'] for i in items[1:3]}, {new.id, manual.id})

    def _replied(self, persona, username, name):
        """Someone who answered our first message and waits for our answer."""
        prospect = self._accepted(persona, username=username, name=name)
        prospect.write({'stage': 'replied', 'current_step_id': persona.chat_agent_id.step_ids.sorted('sequence')[:1].id,
                        'date_first_message': fields.Datetime.now() - timedelta(days=2),
                        'last_outbound_date': fields.Datetime.now() - timedelta(days=2),
                        'last_inbound_date': fields.Datetime.now() - timedelta(days=1),
                        'last_activity_date': fields.Datetime.now() - timedelta(days=1)})
        return prospect

    @freeze_time(MONDAY_10_UTC)
    def test_replies_are_written_and_sent_before_first_messages(self):
        self._start()
        persona = self._persona(run=('chat',), chat_daily_limit=2)
        first = self._accepted(persona, username='first-a', name='First A')
        second = self._accepted(persona, username='first-b', name='First B')
        third = self._accepted(persona, username='first-c', name='First C')
        written = [i for i in self.call('li_get_work', linkedin_profile='taha')['items'] if i['type'] == 'message']
        self.assertEqual(len(written), 2)                    # the day's room: 2 first messages
        for item in written:
            self.assertTrue(self.call('li_submit_text', work_id=item['work_id'], text='Hi there, thanks for '
                                      'connecting. Glad to be in touch.')['ok'])
        # Sunaan replies now: the room is full of first messages, his answer is still written
        sunaan = self._replied(persona, 'sunaan', 'Sunaan Mushtaq')
        result = self.call('li_get_work', linkedin_profile='taha')
        items = [i for i in result['items'] if i['type'] == 'message']
        self.assertEqual([i['prospect']['id'] for i in items], [sunaan.id])
        why = {p['name']: p['why'] for p in result['chat_waiting']['people']}
        self.assertIn("today's message limit (2) is taken", why[(first | second | third).filtered(
            lambda p: p.id not in [w['prospect']['id'] for w in written]).name])
        self.assertTrue(self.call('li_submit_text', work_id=items[0]['work_id'],
                                  text='Thanks Sunaan, happy to explain what I wanted to ask.')['ok'])
        # and sent first, before the first messages written earlier; the daily limit holds at sending
        for _round in range(4):
            self._run()
        sent = [c['args']['linkedin_username'] for c in self._calls(tool='send_message')]
        self.assertEqual(sent[0], 'sunaan')
        self.assertEqual(len(sent), 2)
        left = self.env['li.work.item'].search([('persona_id', '=', persona.id), ('state', '=', 'queued')])
        self.assertEqual(len(left), 1)                       # waits for the next day, not thrown away

    def test_chat_waiting_names_a_stopped_chat_agent(self):
        persona = self._persona(run=())
        self._accepted(persona)
        waiting = self.Tools._chat_waiting(self.profile)
        self.assertTrue(any('1 accepted people never got a message' in line for line in waiting['personas']))

    def test_upgrade_understands_places_again(self):
        tag = self._tag('Florida')
        self.env.cr.execute("UPDATE li_target_tag SET geo_label = 'Florida, Cuba', geo_precision = 'city' "
                            "WHERE id = %s", (tag.id,))
        tag.invalidate_recordset()
        self.env['li.target.tag']._li_recompute_places()
        self.assertEqual((tag.geo_label, tag.geo_precision), ('Florida, United States', 'region'))


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestTakeoverAndInbound(BackgroundCase):
    """Taken over only when a person really wrote; handed back properly; other
    people who message us are answered too."""

    def _persona_chat(self):
        persona = self._persona(run=('chat',))
        self.profile.my_display_name = 'Taha Sohail'
        return persona

    def _sent(self, prospect, text):
        step = prospect.persona_id.chat_agent_id.step_ids.sorted('sequence')[0]
        item = self.Tools._queue_send('message', prospect, text=text, step=step)
        item.write({'state': 'done', 'confirmed': True, 'text_sent': text})
        return item

    def test_agent_message_shown_a_little_differently_is_no_takeover(self):
        persona = self._persona_chat()
        prospect = self._accepted(persona)
        self._sent(prospect, 'Salam Ali, thanks for connecting. How is payroll handled at your company today?')
        self.Tools._record_thread(self.profile, prospect, [
            {'sender_name': 'Taha Sohail',
             'text': 'Salam Ali,  thanks for connecting! How is payroll handled at your company today'},
            {'sender_name': 'Ali Raza', 'text': 'We use a spreadsheet.'}])
        self.assertFalse(prospect.is_taken_over)
        self.assertTrue(prospect.needs_analysis)
        self.assertEqual(prospect.message_ids_li.filtered(lambda m: m.direction == 'out').mapped('ai_generated'),
                         [True])

    def test_message_really_written_by_hand_takes_over_and_says_which(self):
        persona = self._persona_chat()
        prospect = self._accepted(persona)
        self._sent(prospect, 'Salam Ali, thanks for connecting. How is payroll handled at your company today?')
        self.Tools._record_thread(self.profile, prospect, [
            {'sender_name': 'Taha Sohail',
             'text': 'Salam Ali, thanks for connecting. How is payroll handled at your company today?'},
            {'sender_name': 'Taha Sohail', 'text': 'Can we have a call on Thursday at 3?'}])
        self.assertEqual((prospect.is_taken_over, prospect.takeover_reason), (True, 'human_message'))
        self.assertTrue(any('Can we have a call on Thursday at 3?' in (m.body or '') for m in prospect.message_ids))

    def test_take_over_tool_is_only_for_explicit_requests(self):
        from ..models.li_mcp_tools import TOOLS
        tool = [t for t in TOOLS if t['name'] == 'li_take_over'][0]
        self.assertIn('Never call it because the user looks at, opens', tool['description'])

    @freeze_time(MONDAY_10_UTC)
    def test_hand_back_answers_their_reply(self):
        persona = self._persona_chat()
        prospect = self._accepted(persona)
        self.Tools._record_thread(self.profile, prospect, [
            {'sender_name': 'Taha Sohail', 'text': 'Hi Ali, Taha here, can I ask you something about payroll?'}])
        self.assertTrue(prospect.is_taken_over)              # written by hand
        self.Tools._record_thread(self.profile, prospect, [
            {'sender_name': 'Taha Sohail', 'text': 'Hi Ali, Taha here, can I ask you something about payroll?'},
            {'sender_name': 'Ali Raza', 'text': 'Sure, go ahead.'}])
        self.assertFalse(prospect.needs_analysis)            # nobody answers while a person has it
        prospect.with_user(self.manager).action_return_to_agents()
        self.assertFalse(prospect.is_taken_over)
        self.assertEqual((prospect.needs_analysis, prospect.awaiting_reply, prospect.stage),
                         (True, False, 'replied'))
        self.assertTrue(prospect.thread_check_needed)        # read again in the next run
        self.assertIn('wrote to them by hand', prospect._situation_payload()['handled_by_a_person'])
        items = self.call('li_get_work', linkedin_profile='taha')['items']
        self.assertIn(prospect.id, [i['prospect']['id'] for i in items if i['type'] == 'analyse'])

    @freeze_time(MONDAY_10_UTC)
    def test_hand_back_after_our_message_waits_for_them(self):
        persona = self._persona_chat()
        prospect = self._accepted(persona)
        self.Tools._record_thread(self.profile, prospect, [
            {'sender_name': 'Ali Raza', 'text': 'Hello there'},
            {'sender_name': 'Taha Sohail', 'text': 'Hi Ali, Taha here, what does your team use for payroll?'}])
        prospect.with_user(self.manager).action_return_to_agents()
        self.assertEqual((prospect.needs_analysis, prospect.awaiting_reply), (False, True))

    # ------------------------------------------------------------------
    # Other people who message us
    # ------------------------------------------------------------------
    def _inbox(self, rows, threads):
        return {'data': {'sections': {'inbox': '\n'.join(rows)}, 'references': {'inbox': [
            {'kind': 'conversation', 'url': '/messaging/thread/%s/' % tid, 'text': name}
            for name, tid in threads]}}}

    @freeze_time(MONDAY_10_UTC)
    def test_other_people_who_message_us_are_answered(self):
        self._start()
        persona = self._persona_chat()
        threads = [('Old Friend', '2-old=='), ('Quiet One', '2-quiet=='), ('Ad Company', '2-ad=='),
                   ('Ali Raza, Sara Khan', '2-group==')]
        first = self._inbox(['Old Friend', 'Oct 1', 'Thanks for the help last year',
                             'Quiet One', 'Sep 3', 'You: See you'], threads)
        second = self._inbox(['Old Friend', '10:30 AM', 'Hi Taha, are you still doing payroll software?',
                              'Quiet One', '10:20 AM', 'You: Hi again',
                              'Ad Company', '10:10 AM', 'Sponsored', 'Try our product',
                              'Ali Raza, Sara Khan', '10:00 AM', 'Group hello'], threads)
        conversation = {'data': {'url': 'https://www.linkedin.com/messaging/thread/2-old==/', 'sections': {
            'conversation': 'Taha Sohail sent the following message at 9:00 AM\nTaha Sohail\nGood to see you here!\n'
                            'Old Friend sent the following message at 10:30 AM\nOld Friend\n'
                            'Hi Taha, are you still doing payroll software?'},
            'references': {'conversation': [{'kind': 'person', 'url': '/in/taha-test/', 'text': 'Taha Sohail'},
                                            {'kind': 'person', 'url': '/in/old-friend/', 'text': 'Old Friend'}]}}}
        self._script(get_inbox=[first, second], get_conversation=[conversation])
        self._run()                                          # first read: only notes what is there
        self.assertFalse(self._calls(tool='get_conversation'))
        self.profile.last_inbox_check = False
        self._run()
        reads = self._calls(tool='get_conversation')
        self.assertEqual(reads, [{'tool': 'get_conversation', 'args': {'thread_id': '2-old=='}}])
        friend = self.env['li.prospect'].search([('linkedin_username', '=', 'old-friend')])
        self.assertEqual((friend.persona_id, friend.from_inbox, friend.stage), (persona, True, 'replied'))
        self.assertFalse(friend.is_taken_over)               # our old message is history, not a takeover
        self.assertTrue(friend.needs_analysis)               # Claude analyses, then answers
        self.assertIn('existing contact', friend._situation_payload()['existing_connection_wrote_first'])
        self.assertEqual(friend.message_ids_li.sorted('id').mapped('direction'), ['out', 'in'])
        # nobody else: we wrote last, a sponsored message, a group chat
        self.assertEqual(self.env['li.prospect'].search_count([('from_inbox', '=', True)]), 1)

    @freeze_time(MONDAY_10_UTC)
    def test_other_messages_can_be_switched_off(self):
        self._start()
        self._persona_chat()
        self.profile.answer_other_messages = False
        self.assertFalse(self.profile._inbound_persona())
