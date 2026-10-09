"""Offline geocoding of LinkedIn location texts ("Lahore, Punjab, Pakistan",
"Greater London Area", "San Francisco Bay Area") for the prospects map.

Uses data/geo (GeoNames cities with 15,000+ people and first-level regions,
CC BY 4.0, and country centroids computed from Natural Earth, public domain).
Nothing is sent to any map or geocoding service.
"""
import csv
import gzip
import os
import re
import threading
import unicodedata

from odoo import api, fields, models

GEO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'geo')

COUNTRY_ALIASES = {
    'usa': 'US', 'us': 'US', 'u s': 'US', 'united states of america': 'US', 'america': 'US',
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
                return best[3], best[4], '%s, %s' % (best[0], best[1]), 'city', best[1]
    for part in parts:
        region_key = _SUFFIX.sub('', _key(part))
        matches = [value for (code, key), value in index['regions'].items()
                   if key in (region_key, _key(part)) and (not cc or code == cc)] if region_key else []
        if matches:
            region, place = max(matches, key=lambda m: m[1][5])
            return place[3], place[4], '%s, %s' % (region, place[1]), 'region', place[1]
    if not cc and len(parts) == 1 and _key(parts[0]) in index['country_names']:
        cc = index['country_names'][_key(parts[0])]
    if cc:
        if cc in index['countries']:
            name, lat, lng = index['countries'][cc]
            return lat, lng, name, 'country', cc
        biggest = max((c for cities in index['cities'].values() for c in cities if c[1] == cc),
                      key=lambda c: c[5], default=None)
        if biggest:
            return biggest[3], biggest[4], cc, 'country', cc
    return None


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
