"""Who a persona really targets, checked before anyone is invited.

* Locations are understood however they are typed ("USA", "America", "Dubai",
  "NYC") and matched to LinkedIn's own location ids, so the search uses
  LinkedIn's "Locations" filter.
* Every person found (engine search, Claude's list, a search URL) passes the
  location, job title and competitor checks; then Claude's fit check against
  the ideal customer, unless the persona switches it off.
* One LinkedIn account never sends more invitations than its own daily and
  weekly caps, whatever its personas allow and whatever the outcome of each try.
* The Chat Agent says why nobody is due for a message.
"""
import re
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

from .li_common import local_now, safe_zone, utc_now
from .li_geo import place_in_target, understand_place
from .li_mcp_tools import ToolError

SCREEN_BATCH = 10
# the same job, however a headline writes it
TITLE_SYNONYMS = [
    ('ceo', 'chief executive officer', 'chief executive'),
    ('cto', 'chief technology officer', 'chief technical officer'),
    ('cfo', 'chief financial officer', 'chief finance officer'),
    ('coo', 'chief operating officer', 'chief operations officer'),
    ('cmo', 'chief marketing officer'),
    ('cio', 'chief information officer'),
    ('cpo', 'chief product officer'),
    ('cro', 'chief revenue officer'),
    ('chro', 'chief human resources officer', 'chief people officer'),
    ('vp', 'vice president', 'svp', 'evp', 'avp'),
    ('md', 'managing director'),
    ('founder', 'co founder', 'cofounder'),
    ('owner', 'co owner', 'business owner', 'proprietor'),
    ('president',),
    ('hr', 'human resources'),
]
FILLER_WORDS = {'of', 'and', 'the', 'for', 'at', 'in', 'a', 'an'}


def _words(text):
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).split()


def _singular(word):
    return word[:-1] if len(word) > 3 and word.endswith('s') and not word.endswith('ss') else word


def title_patterns(job_titles):
    """[(the title as typed, [word sequences that count as it])] for a
    persona's job titles ("Founder, Owners, CEO"). "Owners" also means "Owner";
    "CEO" also "Chief Executive Officer"."""
    patterns = []
    for title in (t.strip() for t in re.split(r'[,;\n]+', job_titles or '')):
        typed = [w for w in _words(title) if w not in FILLER_WORDS]
        if not typed:
            continue
        words = [_singular(w) for w in typed]
        phrase = ' '.join(words)
        alternatives = {phrase}
        if len(typed) > 1:
            alternatives.add(' '.join(typed))   # "Head of Operations" as typed too
        for group in TITLE_SYNONYMS:
            if phrase in group:
                alternatives.update(group)
        patterns.append((title, [alt.split() for alt in alternatives]))
    return patterns


def title_found(text, patterns):
    """The persona title the text holds as whole words, or ''. A one-word
    title must appear as a word ("Co-Founder & CEO" holds Founder and CEO;
    "I help founders" holds neither); a longer one needs all its words."""
    words = _words(text)
    joined = ' %s ' % ' '.join(words)
    present = set(words)
    for title, alternatives in patterns:
        for alt in alternatives:
            if (len(alt) == 1 and alt[0] in present) or (len(alt) > 1 and (
                    ' %s ' % ' '.join(alt) in joined or set(alt) <= present)):
                return title
    return ''


def names_found(text, names):
    """The first name of `names` that appears in the text as whole words."""
    joined = ' %s ' % ' '.join(_words(text))
    for name in names:
        key = ' '.join(_words(name))
        if key and ' %s ' % key in joined:
            return name
    return ''


def _count_invited_people(env, column, record_id, since):
    """People the engine tried to invite since `since` (one person may take
    several Connect routes: counted once). A try the engine refused before
    LinkedIn (busy, not running) does not count; every other one does."""
    assert column in ('linkedin_profile_id', 'persona_id')
    env['li.engine.action'].flush_model()
    env.cr.execute("""SELECT COUNT(DISTINCT COALESCE(prospect_id, -id)) FROM li_engine_action
                      WHERE %s = %%s AND action = 'invite' AND date >= %%s
                        AND COALESCE(status, '') != 'refused'""" % column, (record_id, since))
    return env.cr.fetchone()[0]


class LiTargetTagGeo(models.Model):
    _inherit = 'li.target.tag'

    geo_label = fields.Char('Understood as', compute='_compute_place', store=True)
    geo_country = fields.Char('Country code', size=2, compute='_compute_place', store=True)
    geo_precision = fields.Selection([('city', 'City'), ('region', 'Region'), ('country', 'Country')],
                                     compute='_compute_place', store=True)
    geo_lat = fields.Float(digits=(9, 4), compute='_compute_place', store=True)
    geo_lng = fields.Float(digits=(9, 4), compute='_compute_place', store=True)
    geo_region = fields.Char(compute='_compute_place', store=True)
    geo_query = fields.Char(compute='_compute_place', store=True)
    geo_guessed = fields.Boolean(compute='_compute_place', store=True)
    linkedin_geo_id = fields.Char(
        'LinkedIn location ID',
        help='LinkedIn\'s own id of this place, used as its "Locations" filter in searches. Found automatically '
             'by the built-in engine; you can also copy it from a LinkedIn people search filtered on this place: '
             'the number in geoUrn=["…"] of the address.')
    linkedin_geo_name = fields.Char('LinkedIn location', readonly=True)
    geo_lookup_date = fields.Datetime(readonly=True)
    geo_lookup_note = fields.Char(readonly=True)
    geo_summary = fields.Char('Location', compute='_compute_geo_summary')

    @api.depends('name', 'kind')
    def _compute_place(self):
        for tag in self:
            place = understand_place(tag.name) if tag.kind == 'location' and tag.name else None
            if place:
                tag.update({'geo_label': place['label'], 'geo_country': place['country'],
                            'geo_precision': place['precision'], 'geo_lat': place['lat'], 'geo_lng': place['lng'],
                            'geo_region': place['region'], 'geo_query': place['query'],
                            'geo_guessed': place['guessed']})
            else:
                tag.update({'geo_label': False, 'geo_country': False, 'geo_precision': False, 'geo_lat': 0.0,
                            'geo_lng': 0.0, 'geo_region': False, 'geo_query': False, 'geo_guessed': False})

    @api.depends('name', 'geo_label', 'geo_guessed', 'linkedin_geo_id', 'linkedin_geo_name', 'geo_lookup_note')
    def _compute_geo_summary(self):
        for tag in self:
            if not tag.geo_label:
                understood = _('%s: not a known place, matched by its words only', tag.name)
            else:
                understood = '%s → %s%s' % (tag.name, tag.geo_label, _(' (closest match, check it)')
                                             if tag.geo_guessed else '')
            if tag.linkedin_geo_id:
                filter_text = _('LinkedIn filter: %(name)s (%(id)s)', name=tag.linkedin_geo_name or tag.geo_label
                                or tag.name, id=tag.linkedin_geo_id)
            else:
                filter_text = tag.geo_lookup_note or _('LinkedIn filter: looked up before the next search')
            tag.geo_summary = '%s · %s' % (understood, filter_text)

    @api.model
    def _li_recompute_places(self):
        """On every upgrade: places understood again with the current rules."""
        tags = self.sudo().search([('kind', '=', 'location')])
        self.env.add_to_compute(self._fields['geo_label'], tags)
        tags._recompute_recordset()
        return len(tags)

    def write(self, vals):
        if 'name' in vals and 'linkedin_geo_id' not in vals:
            vals = dict(vals, linkedin_geo_id=False, linkedin_geo_name=False, geo_lookup_date=False,
                        geo_lookup_note=False)
        return super().write(vals)

    def _target(self):
        self.ensure_one()
        if not self.geo_country:
            return {'text': self.name}
        return {'label': self.geo_label, 'country': self.geo_country, 'precision': self.geo_precision,
                'lat': self.geo_lat, 'lng': self.geo_lng, 'region': self.geo_region or '',
                'query': self.geo_query or self.name}

    def _pick_linkedin_place(self, candidates):
        """The LinkedIn suggestion that is this place: same name, and for a city
        or region the same country in its text. None when none fits."""
        self.ensure_one()
        query = ' '.join(_words(self.geo_query or self.name))
        country = ' '.join(_words(self.geo_label.split(',')[-1])) if self.geo_label else ''
        best = None
        for candidate in candidates:
            name = ' '.join(_words(candidate.get('name')))
            if not name or not str(candidate.get('id') or '').isdigit():
                continue
            if self.geo_precision == 'country' or not self.geo_precision:
                if name == query or (country and name == country):
                    return candidate
                continue
            if not name.startswith(query):
                continue
            if country and country not in name:
                continue
            if name == '%s %s' % (query, country) or best is None:
                best = candidate
        return best


class LiPersonaTargeting(models.Model):
    _inherit = 'li.persona'

    exclude_companies = fields.Text(
        'Exclude companies / competitors',
        help='Comma separated company names. Nobody whose headline or company names one of them is invited.')
    fit_check = fields.Boolean(
        'Claude checks each person before the invite', default=True,
        help='Every person who passes the location, job title and competitor checks waits in "Fit check" until '
             'Claude compares their headline with the ideal customer, industries, seniority and company size. '
             'Only people Claude approves are invited. Claude must run for invites to go out.')
    location_summary = fields.Text('Locations understood', compute='_compute_location_summary')

    @api.depends('location_ids.geo_summary')
    def _compute_location_summary(self):
        for persona in self:
            persona.location_summary = '\n'.join(persona.location_ids.mapped('geo_summary')) or False

    def _target_check(self, person):
        """(True, what matched) or (False, why not) for one person found for this
        persona: location, job title, competitor."""
        self.ensure_one()
        headline = ' '.join(filter(None, [person.get('headline'), person.get('title')]))
        notes = []
        if self.location_ids:
            inside, label = place_in_target(person.get('location') or '',
                                            [tag._target() for tag in self.location_ids])
            if not inside:
                return False, _('location "%(where)s" is outside %(targets)s',
                                where=person.get('location') or _('unknown'),
                                targets=', '.join(self.location_ids.mapped(lambda t: t.geo_label or t.name)))
            notes.append(_('location %s', label))
        patterns = title_patterns(self.job_titles)
        if patterns:
            title = title_found(headline, patterns)
            if not title:
                return False, _('no %(titles)s in "%(headline)s"', titles=' / '.join(p[0] for p in patterns),
                                headline=headline or _('empty headline'))
            notes.append(_('title %s', title))
        competitor = names_found(' '.join(filter(None, [headline, person.get('company')])),
                                 [c.strip() for c in re.split(r'[,;\n]+', self.exclude_companies or '') if c.strip()])
        if competitor:
            return False, _('works at %s (excluded company)', competitor)
        return True, ', '.join(notes)

    def _criteria_payload(self):
        """What Claude checks a person against in a fit check."""
        self.ensure_one()
        return {
            'ideal_customer': self.icp_description or '',
            'pain_points': self.pain_points or '',
            'job_titles': self.job_titles or '',
            'industries': self.industry_ids.mapped('name'),
            'seniority': self.seniority_ids.mapped('name'),
            'company_size': self.company_size_ids.mapped('name'),
            'locations': self.location_ids.mapped(lambda t: t.geo_label or t.name),
            'include_keywords': self.include_keywords or '',
            'exclude_keywords': self.exclude_keywords or '',
            'exclude_companies': self.exclude_companies or '',
            'our_service': self.service_id.name or '',
            'our_service_pitch': self.service_id.description or '',
        }


class LiProspectFit(models.Model):
    _inherit = 'li.prospect'

    fit_reason = fields.Text('Why (not) invited', readonly=True,
                             help='What matched the persona, or why this person is not a fit.')
    fit_checked_at = fields.Datetime('Fit checked on', readonly=True)

    @api.model
    def _li_check_queued_fit(self, force=False):
        """Once: people queued before the targeting checks existed pass them now:
        outside the persona's locations, titles or companies -> Not a fit;
        the others wait for Claude's fit check when the persona asks for it."""
        if not self._li_once('li_sales.queued_fit_checked', force):
            return 0
        busy = self.env['li.work.item'].sudo().search([('state', 'in', ('released', 'queued', 'sending')),
                                                       ('work_type', '=', 'invite')]).mapped('prospect_id')
        count = 0
        for prospect in self.sudo().search([('stage', '=', 'queued')]) - busy:
            ok, why = prospect.persona_id._target_check({
                'headline': prospect.headline, 'title': prospect.title, 'company': prospect.company,
                'location': prospect.location})
            if not ok:
                prospect.write({'stage': 'unfit', 'fit_reason': why, 'fit_checked_at': utc_now()})
            elif prospect.persona_id.fit_check:
                prospect.write({'stage': 'screening', 'fit_reason': why})
            else:
                continue
            count += 1
        return count


class LiProfileCaps(models.Model):
    _inherit = 'li.profile'

    invite_daily_cap = fields.Integer(
        'Invitations per day (whole account)', default=20,
        help='Never more invitations a day from this LinkedIn account, all personas together, counted on the '
             'account\'s own calendar day (home time zone). Every Connect try counts, whatever LinkedIn answered.')
    invite_weekly_cap = fields.Integer(
        'Invitations per 7 days (whole account)', default=100,
        help='Never more invitations in any 7 days from this account, all personas together. LinkedIn restricts '
             'accounts that send much more.')

    def _invite_attempts(self, since):
        """Connect tries that reached LinkedIn since `since` (naive UTC)."""
        self.ensure_one()
        if self.execution_mode == 'chrome':
            return self.env['li.work.item'].sudo().search_count([
                ('linkedin_profile_id', '=', self.id), ('work_type', '=', 'invite'),
                ('date_confirmed', '>=', since)])
        return _count_invited_people(self.env, 'linkedin_profile_id', self.id, since)

    def _account_day_start(self):
        zone = safe_zone(self.home_timezone)
        start = datetime.combine(local_now(self.home_timezone).date(), time(0), tzinfo=zone)
        return start.astimezone(safe_zone('UTC')).replace(tzinfo=None)

    def _invites_left(self):
        """(invitations this account may still send now, why not when 0)."""
        self.ensure_one()
        daily = self.invite_daily_cap if self.invite_daily_cap > 0 else 20
        weekly = self.invite_weekly_cap if self.invite_weekly_cap > 0 else 100
        today = self._invite_attempts(self._account_day_start())
        week = self._invite_attempts(utc_now() - timedelta(days=7))
        left = min(daily - today, weekly - week)
        if left > 0:
            return left, ''
        if today >= daily:
            return 0, _('%(account)s: account limit of %(n)s invitations today reached (all personas)',
                        account=self.name, n=daily)
        return 0, _('%(account)s: account limit of %(n)s invitations in 7 days reached (all personas)',
                    account=self.name, n=weekly)


class LiMcpTargeting(models.AbstractModel):
    _inherit = 'li.mcp.tools'

    # ------------------------------------------------------------------
    # Persona-level invitation counting: every Connect try counts
    # ------------------------------------------------------------------
    def _invite_tries_today(self, persona):
        zone = safe_zone(persona.target_timezone)
        start = datetime.combine(local_now(persona.target_timezone).date(), time(0), tzinfo=zone)
        start = start.astimezone(safe_zone('UTC')).replace(tzinfo=None)
        if persona.linkedin_profile_id.execution_mode == 'chrome':
            return self.env['li.work.item'].sudo().search_count([
                ('persona_id', '=', persona.id), ('work_type', '=', 'invite'), ('date_confirmed', '>=', start)])
        return _count_invited_people(self.env, 'persona_id', persona.id, start)

    def _quota_left(self, persona, agent_type, exclude=None):
        left = super()._quota_left(persona, agent_type, exclude=exclude)
        if agent_type == 'connection':
            agent = self._agent_of('connection', persona)
            left = min(left, agent.daily_limit - self._invite_tries_today(persona))
        return left

    # ------------------------------------------------------------------
    # Fit check (screen items): Claude approves each person before the invite
    # ------------------------------------------------------------------
    def _gen_w_screen(self, profile, ctx):
        items = []
        personas = profile.persona_ids.filtered(lambda p: p.fit_check and p.connection_agent_id.state == 'running')
        open_items = self.env['li.work.item'].search([('work_type', '=', 'screen'), ('state', '=', 'released'),
                                                      ('linkedin_profile_id', '=', profile.id)])
        busy = set(open_items.mapped('prospect_ids').ids)
        for persona in personas:
            if ctx['left'] - len(items) <= 0:
                break
            people = self.env['li.prospect'].search([
                ('persona_id', '=', persona.id), ('stage', '=', 'screening'), ('id', 'not in', list(busy))],
                order='create_date asc, id asc', limit=SCREEN_BATCH)
            if not people:
                continue
            items.append(self._create_item('screen', 'connection', profile, persona, payload={
                'criteria': persona._criteria_payload(),
                'people': [{'prospect_id': p.id, 'name': p.name, 'headline': p.headline or '',
                            'title': p.title or '', 'company': p.company or '', 'location': p.location or '',
                            'linkedin_url': p.linkedin_url, 'checked_by_odoo': p.fit_reason or ''}
                           for p in people],
                'instructions': (
                    'Fit check before any invitation. Odoo already checked location, job title and excluded '
                    'companies (checked_by_odoo). For each person decide whether they are this persona\'s ideal '
                    'customer: the right role and seniority, an industry and company type the criteria target, a '
                    'company size that fits when the headline shows it. Never invite a competitor (someone who '
                    'sells the same kind of service as ours), a recruiter, a student, a job seeker or someone '
                    'whose headline does not show the targeted role, unless the criteria ask for them. When in '
                    'doubt, invite false. Answer every person with li_record_fit: invite true or false and a '
                    'reason of a few words.'),
            }, prospect_ids=[(6, 0, people.ids)]))
        return items

    def _tool_li_record_fit(self, work_id, decisions):
        self._lock()
        item = self._get_item(work_id, ['screen'])
        if item.state != 'released':
            raise ToolError('Work item %s is %s. Call li_get_work for fresh items.' % (item.id, item.state))
        listed = item.prospect_ids
        invited = rejected = 0
        now = utc_now()
        for decision in decisions or []:
            prospect = listed.filtered(lambda p: p.id == int(decision.get('prospect_id') or 0))
            if not prospect or prospect.stage != 'screening':
                continue
            reason = (decision.get('reason') or '').strip()[:300]
            checked = prospect.fit_reason or ''
            if decision.get('invite'):
                prospect.sudo().write({'stage': 'queued', 'fit_checked_at': now,
                                       'fit_reason': _('Fit (Claude): %(why)s%(odoo)s', why=reason or _('fits'),
                                                       odoo=' · %s' % checked if checked else '')})
                invited += 1
            else:
                prospect.sudo().write({'stage': 'unfit', 'fit_checked_at': now,
                                       'fit_reason': _('Not a fit (Claude): %s', reason or _('no reason given'))})
                rejected += 1
        left = listed.filtered(lambda p: p.stage == 'screening')
        item._close('done', result_status='checked')
        line = _('Fit check by Claude: %(ok)s to invite, %(no)s not a fit', ok=invited, no=rejected)
        if invited or rejected:
            item.persona_id.sudo().message_post(body=line, author_id=self.env['li.event']._ai_partner().id,
                                                subtype_xmlid='mail.mt_note')
        return {'ok': True, 'work_id': item.id, 'to_invite': invited, 'not_a_fit': rejected,
                'not_answered': len(left),
                'message': '%s.%s' % (line, ' %s not answered: they come back in a later fit check.' % len(left)
                                      if left else '')}

    # ------------------------------------------------------------------
    # Chat Agent: why nobody is due for a message
    # ------------------------------------------------------------------
    def _chat_waiting(self, profile, limit=20):
        """For a Chat Agent with nothing to write: per person, why no message is
        due now, and per persona what blocks it. Never empty when something
        waits."""
        from .li_engine_chat import CHAT_STAGES
        now = utc_now()
        WorkItem = self.env['li.work.item']
        people, personas = [], []
        for persona in profile.persona_ids.filtered(lambda p: p.chat_agent_id.state != 'running'):
            unmessaged = self.env['li.prospect'].search_count([
                ('persona_id', '=', persona.id), ('stage', '=', 'accepted'), ('date_first_message', '=', False)])
            if unmessaged:
                personas.append(_('%(persona)s: %(n)s accepted people never got a message because its Chat Agent '
                                  'is %(state)s', persona=persona.name, n=unmessaged,
                                  state=persona.chat_agent_id.state or _('missing')))
        for persona in profile.persona_ids.filtered(lambda p: p.chat_agent_id.state == 'running'):
            chat = persona.chat_agent_id
            steps = self._steps(persona)
            if not steps:
                personas.append(_('%s: the Chat Agent has no questionnaire steps, so it never writes', persona.name))
                continue
            if steps[0].trigger != 'after_accept':
                personas.append(_('%s: the first chat step waits for a reply ("after reply"), so nobody gets a first '
                                  'message; set it to "after accept"', persona.name))
            if self._quota_left(persona, 'chat') <= 0:
                personas.append(_('%(persona)s: daily message limit (%(n)s) reached', persona=persona.name,
                                  n=chat.daily_limit))
            invited = self.env['li.prospect'].search_count([('persona_id', '=', persona.id),
                                                            ('stage', '=', 'invited')])
            if invited:
                personas.append(_('%(persona)s: %(n)s invited people have not accepted yet (acceptances are '
                                  'checked every %(m)s minutes)', persona=persona.name, n=invited,
                                  m=self._param('connections_every', 15)))
            prospects = self.env['li.prospect'].search([('persona_id', '=', persona.id),
                                                        ('stage', 'in', CHAT_STAGES)],
                                                       order='date_accepted desc, id desc', limit=limit)
            for prospect in prospects:
                why = self._chat_wait_reason(prospect, now, WorkItem)
                if why:
                    people.append({'name': prospect.name, 'persona': persona.name, 'stage': prospect.stage,
                                   'why': why})
        return {'personas': personas, 'people': people[:limit]}

    def _chat_wait_reason(self, prospect, now, WorkItem):
        if prospect.is_taken_over:
            return _('taken over by %s (a person writes to them)', prospect.taken_over_by.name or _('a person'))
        if prospect.do_not_contact:
            return _('do not contact')
        if prospect.needs_check:
            return _('flagged for a person to check: %s', prospect.needs_check_reason or '')
        if prospect.needs_analysis:
            return _('their reply waits for Claude\'s analysis (analyse item)')
        if prospect.sequence_stopped:
            return _('conversation closed (sequence stopped)')
        if WorkItem.search_count([('prospect_id', '=', prospect.id), ('state', 'in', ('queued', 'sending'))]):
            return _('a message is written and waits to be sent (send window and gap between sends)')
        if WorkItem.search_count([('prospect_id', '=', prospect.id), ('state', '=', 'released')]):
            return _('a message item is already open for Claude')
        if prospect._profile_pending():
            return _('their LinkedIn profile is read first, in the next background run')
        if prospect.awaiting_reply:
            return _('waiting for their reply')
        step = self._next_step(prospect)
        if not step:
            return _('questionnaire finished: nothing more to send unless they write')
        due, why = self._step_due(prospect, step, now)
        if not due:
            if why.startswith('due at '):
                return _('next message (%(step)s) due at %(when)s UTC', step=step.name, when=why[7:23])
            return why
        return ''
