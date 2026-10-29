"""Offline geocoding of LinkedIn location texts ("Lahore, Punjab, Pakistan",
"Greater London Area", "San Francisco Bay Area") for the prospects map.

Uses data/geo (GeoNames cities with 15,000+ people and first-level regions,
CC BY 4.0, and country centroids computed from Natural Earth, public domain).
Nothing is sent to any map or geocoding service.
"""
import csv
import difflib
import gzip
import math
import os
import re
import threading
import unicodedata

from odoo import api, fields, models

GEO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'geo')

COUNTRY_ALIASES = {
    'usa': 'US', 'us': 'US', 'u s': 'US', 'united states of america': 'US', 'america': 'US',
    'u s a': 'US', 'the us': 'US', 'the usa': 'US', 'the united states': 'US', 'united state': 'US',
    'united state of america': 'US', 'united states america': 'US', 'states': 'US',
    'uk': 'GB', 'u k': 'GB', 'england': 'GB', 'scotland': 'GB', 'wales': 'GB', 'northern ireland': 'GB',
    'great britain': 'GB', 'britain': 'GB', 'uae': 'AE', 'ksa': 'SA', 'saudi': 'SA', 'russia': 'RU',
    'south korea': 'KR', 'korea': 'KR', 'north korea': 'KP', 'vietnam': 'VN', 'iran': 'IR', 'syria': 'SY',
    'czech republic': 'CZ', 'czechia': 'CZ', 'turkey': 'TR', 'turkiye': 'TR', 'holland': 'NL',
    'the netherlands': 'NL', 'ivory coast': 'CI', 'cote d ivoire': 'CI', 'macau': 'MO', 'hong kong sar': 'HK',
    'taiwan': 'TW', 'laos': 'LA', 'moldova': 'MD', 'bolivia': 'BO', 'venezuela': 'VE', 'tanzania': 'TZ',
    'congo': 'CG', 'dr congo': 'CD', 'democratic republic of the congo': 'CD', 'palestine': 'PS',
    'brunei': 'BN', 'cape verde': 'CV', 'eswatini': 'SZ', 'north macedonia': 'MK', 'myanmar': 'MM',
    'burma': 'MM', 'the bahamas': 'BS', 'the gambia': 'GM', 'vatican': 'VA', 'kosovo': 'XK',
}
# LinkedIn metro areas that are not named after their main city
METRO_ALIASES = {
    'san francisco bay': 'san francisco', 'silicon valley': 'san jose', 'dallas fort worth': 'dallas',
    'dallas ft worth': 'dallas', 'washington dc baltimore': 'washington', 'washington dc': 'washington',
    'research triangle': 'raleigh', 'tampa bay': 'tampa', 'randstad': 'amsterdam', 'ruhr': 'essen',
    'new york city': 'new york city', 'nyc': 'new york city', 'la': 'los angeles', 'sf': 'san francisco',
    'greater toronto': 'toronto', 'gta': 'toronto', 'twin cities': 'minneapolis', 'hampton roads': 'norfolk',
    'inland empire': 'riverside', 'delhi ncr': 'new delhi', 'ncr': 'new delhi', 'national capital region': 'new delhi',
    'bengaluru': 'bengaluru', 'bangalore': 'bengaluru', 'bombay': 'mumbai', 'madras': 'chennai',
    'calcutta': 'kolkata', 'islamabad rawalpindi': 'islamabad',
}
_PREFIX = re.compile(r'^(greater|metropolitan|metro|city of)\s+')
_SUFFIX = re.compile(r'\s+(metropolitan area|metropolitan region|metro area|metroplex|bay area|area|region|'
                     r'urban area|and surrounding area|district|division|county|city|province|governorate)$')

_lock = threading.Lock()
_index = {}


def _key(text):
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def _load():
    with _lock:
        if _index:
            return _index
        cities, regions, countries, country_names = {}, {}, {}, {}
        with gzip.open(os.path.join(GEO_DIR, 'places.tsv.gz'), 'rt', encoding='utf-8') as data:
            for row in csv.DictReader(data, delimiter='\t', quoting=csv.QUOTE_NONE):
                place = (row['name'], row['cc'], _key(row['region']), float(row['lat']), float(row['lng']),
                         int(row['population']))
                for name in {_key(row['name']), _key(row['ascii'])}:
                    if name:
                        cities.setdefault(name, []).append(place)
                if row['region']:
                    # sorted by population: the first city seen is the region's main one
                    regions.setdefault((row['cc'], _key(row['region'])), (row['region'], place))
        with open(os.path.join(GEO_DIR, 'countries.tsv'), encoding='utf-8') as data:
            for row in csv.DictReader(data, delimiter='\t', quoting=csv.QUOTE_NONE):
                countries[row['cc']] = (row['name'], float(row['lat']), float(row['lng']))
                country_names[_key(row['name'])] = row['cc']
        country_names.update(COUNTRY_ALIASES)
        _index.update(cities=cities, regions=regions, countries=countries, country_names=country_names)
        return _index


def _city_keys(part):
    key = _key(part)
    seen = []
    for candidate in (key, METRO_ALIASES.get(key), _SUFFIX.sub('', _PREFIX.sub('', key))):
        if candidate and candidate not in seen:
            seen.append(candidate)
            alias = METRO_ALIASES.get(candidate)
            if alias and alias not in seen:
                seen.append(alias)
    return seen


def geocode(location):
    """(lat, lng, label, precision, country code) for a LinkedIn location text,
    or None. precision: city, region or country."""
    found = _geocode(location)
    return found[:5] if found else None


def _geocode(location):
    """geocode() plus the region key of the place ('' for a country)."""
    parts = [p.strip() for p in (location or '').split(',') if p.strip()]
    if not parts:
        return None
    index = _load()
    cc = None
    last = _key(parts[-1])
    if last in index['country_names']:
        cc = index['country_names'][last]
        parts = parts[:-1]
    hints = {_key(p) for p in parts[1:]} | {_SUFFIX.sub('', _key(p)) for p in parts[1:]}
    for part in parts[:2]:
        for name in _city_keys(part):
            candidates = [c for c in index['cities'].get(name, []) if not cc or c[1] == cc]
            if candidates:
                best = max(candidates, key=lambda c: (c[2] in hints, c[5]))
                return best[3], best[4], '%s, %s' % (best[0], best[1]), 'city', best[1], best[2]
    for part in parts:
        region_key = _SUFFIX.sub('', _key(part))
        matches = [value for (code, key), value in index['regions'].items()
                   if key in (region_key, _key(part)) and (not cc or code == cc)] if region_key else []
        if matches:
            region, place = max(matches, key=lambda m: m[1][5])
            return place[3], place[4], '%s, %s' % (region, place[1]), 'region', place[1], _key(region)
    if not cc and len(parts) == 1 and _key(parts[0]) in index['country_names']:
        cc = index['country_names'][_key(parts[0])]
    if cc:
        if cc in index['countries']:
            name, lat, lng = index['countries'][cc]
            return lat, lng, name, 'country', cc, ''
        biggest = max((c for cities in index['cities'].values() for c in cities if c[1] == cc),
                      key=lambda c: c[5], default=None)
        if biggest:
            return biggest[3], biggest[4], cc, 'country', cc, ''
    return None


CITY_RADIUS_KM = 60          # a city target also covers its metro area ("Greater Dubai Area", "Brooklyn, NY")


def distance_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(min(1.0, math.sqrt(a)))


def understand_place(text):
    """What a place typed on a persona means, however it is written ("USA",
    "America", "United State of America", "Dubai", "NYC"): a dict with label,
    country (ISO code), country_name, precision (city, region, country), lat,
    lng and query (the name to ask LinkedIn), or None. A small typo is forgiven
    by the closest known country or city name."""
    found = _geocode(text)
    guessed = ''
    if not found:
        key = _key(text)
        index = _load()
        names = list(index['country_names']) + list(index['cities'])
        close = difflib.get_close_matches(key, names, n=1, cutoff=0.86) if key else []
        if close:
            guessed = close[0]
            found = _geocode(close[0])
    if not found:
        return None
    lat, lng, label, precision, cc, region = found
    index = _load()
    country_name = index['countries'].get(cc, (cc,))[0]
    if precision == 'country':
        label, query = country_name, country_name
    else:
        place = label.split(',')[0].strip()
        label = '%s, %s' % (place, country_name)
        query = place
    return {'label': label, 'country': cc, 'country_name': country_name, 'precision': precision,
            'lat': lat, 'lng': lng, 'query': query, 'region': region, 'guessed': bool(guessed)}


def place_in_target(location, targets):
    """(True, target label) when a person's LinkedIn location lies in one of the
    targets (dicts from understand_place, or {'text': ...} for a place that
    could not be understood, matched by its words). A person who only gives a
    country is not inside a city target."""
    if not location:
        return False, ''
    found = _geocode(location)
    words = ' %s ' % _key(location)
    for target in targets:
        if 'text' in target:
            if _key(target['text']) and ' %s ' % _key(target['text']) in words:
                return True, target['text']
            continue
        if not found or found[4] != target['country']:
            continue
        if target['precision'] == 'country':
            return True, target['label']
        if found[3] == 'country':
            continue
        far = distance_km(found[0], found[1], target['lat'], target['lng'])
        if target['precision'] == 'city' and far <= CITY_RADIUS_KM:
            return True, target['label']
        if target['precision'] == 'region' and (found[5] == target.get('region')
                                                or ' %s ' % _key(target['query']) in words):
            return True, target['label']
    return False, ''


class LiProspectGeo(models.Model):
    _inherit = 'li.prospect'

    geo_lat = fields.Float('Latitude', digits=(9, 4), compute='_compute_geo', store=True)
    geo_lng = fields.Float('Longitude', digits=(9, 4), compute='_compute_geo', store=True)
    geo_place = fields.Char('Map place', compute='_compute_geo', store=True,
                            help='Where the prospect is shown on the dashboard map (from the LinkedIn location).')
    geo_precision = fields.Selection([('city', 'City'), ('region', 'Region'), ('country', 'Country')],
                                     compute='_compute_geo', store=True)
    geo_country = fields.Char('Map country', size=2, compute='_compute_geo', store=True)

    @api.depends('location')
    def _compute_geo(self):
        for prospect in self:
            found = geocode(prospect.location) if prospect.location else None
            if found:
                (prospect.geo_lat, prospect.geo_lng, prospect.geo_place, prospect.geo_precision,
                 prospect.geo_country) = found
            else:
                prospect.geo_lat = prospect.geo_lng = 0.0
                prospect.geo_place = prospect.geo_precision = prospect.geo_country = False
