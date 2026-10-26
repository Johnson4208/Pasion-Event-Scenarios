"""Immutable public outcome observations; collection never authorizes a model.

Latest-vintage series lack historical publication timestamps. They are useful
for retrospective labels, but must not be backdated into a point-in-time
training set. News and missing rows never become realized event outcomes.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PROFILES = {
    'vietnam-inflation': dict(provider='WORLD_BANK', category='Economy', factor='Inflation', focus='Vietnam',
        metric='FP.CPI.TOTL.ZG', unit='annual CPI inflation, percent', frequency='ANNUAL', country='VNM',
        measurement='World Bank annual inflation series; not a monthly endpoint or a release-vintage archive.'),
    'vietnam-gdp': dict(provider='WORLD_BANK', category='Economy', factor='GDP growth', focus='Vietnam',
        metric='NY.GDP.MKTP.KD.ZG', unit='annual real GDP growth, percent', frequency='ANNUAL', country='VNM',
        measurement='World Bank annual GDP growth series; revisions are retained as separate retrievals.'),
    'us-cpi': dict(provider='FRED', category='Economy', factor='Inflation', focus='United States',
        metric='CPIAUCSL', unit='CPI index, 1982–1984 = 100', frequency='MONTHLY',
        measurement='US CPI index level. An inflation-rate outcome requires an explicitly reviewed transformation.'),
    'us-gdp': dict(provider='FRED', category='Economy', factor='GDP growth', focus='United States',
        metric='GDPC1', unit='real GDP, billions of chained dollars', frequency='QUARTERLY',
        measurement='US real GDP level, latest vintage; not a historical first-release forecast feature.'),
    'us-labor': dict(provider='FRED', category='Economy', factor='Labor market', focus='United States',
        metric='UNRATE', unit='unemployment rate, percent', frequency='MONTHLY',
        measurement='US unemployment rate. It is one defined labor-market measure, not all labor conditions.'),
    'us-volatility': dict(provider='FRED', category='Markets', factor='Equity volatility', focus='United States',
        metric='VIXCLS', unit='CBOE VIX index points', frequency='DAILY',
        measurement='Observed implied-volatility index; not realized future volatility or a geopolitical probability.'),
    'us-mortgages': dict(provider='FRED', category='Real Estate', factor='Mortgage rates', focus='United States',
        metric='MORTGAGE30US', unit='30-year fixed mortgage survey rate, percent', frequency='WEEKLY',
        measurement='US mortgage survey series; survey coverage and release timing require review.'),
    'vietnam-conflict': dict(provider='UCDP', category='Geopolitics', factor='Conflict risk', focus='Vietnam',
        metric='GED_25.1', unit='reported conflict fatalities, best/low/high estimates', frequency='EVENT_INTERVAL', country='Vietnam', country_id='816',
        measurement='UCDP GED 25.1 realized violent-event estimates. This fixed historical edition does not measure every kind of conflict risk; no row does not establish zero conflict.'),
}
HOSTS = {'api.worldbank.org', 'fred.stlouisfed.org', 'ucdpapi.pcr.uu.se'}


class DataUnavailable(ValueError):
    pass


def database_path():
    return Path(os.environ.get('PASION_EVENT_HISTORY_PATH', ROOT/'private-event-models'/'outcomes.sqlite3'))


def _download(url):
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname not in HOSTS:
        raise DataUnavailable('UNSUPPORTED_OUTCOME_HOST')
    request = Request(url, headers={'User-Agent':'Pasion-OutcomeResearch/1.0','Accept':'application/json,text/csv'})
    try:
        with urlopen(request, timeout=25) as response:
            if response.status != 200 or urlsplit(response.geturl()).hostname not in HOSTS:
                raise DataUnavailable('UNEXPECTED_OUTCOME_RESPONSE')
            raw = response.read(10_000_001)
    except OSError as exc:
        raise DataUnavailable('OUTCOME_PROVIDER_UNREACHABLE') from exc
    if len(raw) > 10_000_000:
        raise DataUnavailable('OUTCOME_RESPONSE_TOO_LARGE')
    return raw


def _value(value):
    if isinstance(value, bool):
        raise DataUnavailable('INVALID_OUTCOME_VALUE')
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise DataUnavailable('INVALID_OUTCOME_VALUE') from exc
    if not math.isfinite(result):
        raise DataUnavailable('INVALID_OUTCOME_VALUE')
    return result


def parse_worldbank(raw, profile):
    data = json.loads(raw)
    if not isinstance(data, list) or len(data) != 2 or not isinstance(data[0], dict) or not isinstance(data[1], list):
        raise DataUnavailable('INVALID_WORLD_BANK_RESPONSE')
    if data[0].get('pages') != 1:
        raise DataUnavailable('INCOMPLETE_WORLD_BANK_PAGES')
    rows = []
    for row in data[1]:
        if not isinstance(row, dict):
            raise DataUnavailable('INVALID_WORLD_BANK_OBSERVATION')
        if row.get('indicator',{}).get('id') != profile['metric'] or row.get('countryiso3code') != profile['country']:
            raise DataUnavailable('WORLD_BANK_CONTEXT_MISMATCH')
        if not re.fullmatch(r'\d{4}', str(row.get('date',''))):
            raise DataUnavailable('INVALID_OBSERVATION_PERIOD')
        if row.get('value') is None:
            continue
        rows.append({'key':str(row['date']), 'period':str(row['date']), 'value':_value(row['value']),
                     'publication_at':None, 'vintage':str(data[0].get('lastupdated') or 'UNKNOWN')})
    return rows


def parse_fred(raw, profile):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    names = reader.fieldnames or []
    date_key = 'observation_date' if 'observation_date' in names else 'DATE'
    if set(names) != {date_key,profile['metric']}:
        raise DataUnavailable('FRED_SERIES_MISMATCH')
    rows = []
    for row in reader:
        try:
            datetime.strptime(row[date_key], '%Y-%m-%d')
        except (KeyError, ValueError, TypeError) as exc:
            raise DataUnavailable('INVALID_OBSERVATION_PERIOD') from exc
        if row[profile['metric']] in ('', '.'):
            continue
        rows.append({'key':row[date_key], 'period':row[date_key], 'value':_value(row[profile['metric']]),
                     'publication_at':None, 'vintage':'LATEST_AT_RETRIEVAL'})
    return rows


def parse_ucdp(raw, profile):
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('Result'), list):
        raise DataUnavailable('INVALID_UCDP_RESPONSE')
    rows = []
    for row in data['Result']:
        if not isinstance(row, dict):
            raise DataUnavailable('INVALID_UCDP_EVENT')
        if row.get('country') != profile['country'] or str(row.get('country_id')) != profile['country_id']:
            raise DataUnavailable('UCDP_COUNTRY_MISMATCH')
        start, end = str(row.get('date_start',''))[:10], str(row.get('date_end',''))[:10]
        try:
            if datetime.fromisoformat(end) < datetime.fromisoformat(start):
                raise ValueError()
        except ValueError as exc:
            raise DataUnavailable('INVALID_EVENT_INTERVAL') from exc
        low, best, high = [_value(row.get(key)) for key in ('low','best','high')]
        if not 0 <= low <= best <= high or not row.get('id'):
            raise DataUnavailable('INVALID_EVENT_ESTIMATE')
        rows.append({'key':str(row['id']), 'period':start, 'period_end':end, 'value':best,
                     'low':low, 'high':high, 'date_precision':row.get('date_prec'),
                     'publication_at':None, 'vintage':profile['metric']})
    return rows, data.get('TotalPages')


def collect(profile_id, now=None):
    """Fetch a complete snapshot before making any database changes."""
    if profile_id not in PROFILES:
        raise DataUnavailable('UNSUPPORTED_OUTCOME_PROFILE')
    profile = PROFILES[profile_id]
    now = now or datetime.now(timezone.utc)
    urls, payloads = [], []
    if profile['provider'] == 'WORLD_BANK':
        url = f"https://api.worldbank.org/v2/country/{profile['country']}/indicator/{profile['metric']}?"+urlencode({'format':'json','per_page':10000})
        raw = _download(url)
        rows = parse_worldbank(raw, profile)
        urls, payloads = [url], [raw]
    elif profile['provider'] == 'FRED':
        url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?'+urlencode({'id':profile['metric']})
        raw = _download(url)
        rows = parse_fred(raw, profile)
        urls, payloads = [url], [raw]
    else:
        rows = []
        pages = None
        for page in range(20):
            url = 'https://ucdpapi.pcr.uu.se/api/gedevents/25.1?'+urlencode({'Country':profile['country_id'],'pagesize':1000,'page':page})
            raw = _download(url)
            chunk, total_pages = parse_ucdp(raw, profile)
            if type(total_pages) is not int or not 1 <= total_pages <= 20 or (pages is not None and total_pages != pages):
                raise DataUnavailable('INCOMPLETE_OR_CHANGING_UCDP_PAGES')
            pages = total_pages
            rows.extend(chunk)
            urls.append(url)
            payloads.append(raw)
            if page+1 == pages:
                break
    keys = [row['key'] for row in rows]
    if len(set(keys)) != len(keys):
        raise DataUnavailable('DUPLICATE_OUTCOME_OBSERVATIONS')
    if not rows:
        raise DataUnavailable('NO_MEASURED_OUTCOMES_NOT_ZERO')
    digest = hashlib.sha256()
    for raw in payloads:
        digest.update(len(raw).to_bytes(8,'big'))
        digest.update(raw)
    return {'schema_version':1, 'profile_id':profile_id, 'profile':profile,
            'retrieved_at':now.isoformat(), 'source_urls':urls, 'response_sha256':digest.hexdigest(),
            '_raw_responses':[{'url':url,'body':raw} for url,raw in zip(urls,payloads)],
            'status':'COLLECTED_NEEDS_OUTCOME_REVIEW', 'observations':rows,
            'history_policy':'LATEST_VINTAGE_RETROSPECTIVE_LABELS_ONLY',
            'point_in_time_ready':False, 'probability_model_ready':False}


def persist(snapshot, path=None):
    path = Path(path) if path else database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {k:v for k,v in snapshot.items() if k not in ('observations','_raw_responses')}
    # A complete successful retrieval is immutable; failed retrievals do not
    # erase earlier vintages or turn missing periods into zero observations.
    identifier = hashlib.sha256((snapshot['profile_id']+snapshot['retrieved_at']+snapshot['response_sha256']).encode()).hexdigest()
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS outcome_snapshots(id TEXT PRIMARY KEY,profile_id TEXT NOT NULL,retrieved_at TEXT NOT NULL,metadata TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS outcome_observations(snapshot_id TEXT NOT NULL,observation_key TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(snapshot_id,observation_key))')
        db.execute('CREATE TABLE IF NOT EXISTS outcome_raw_responses(snapshot_id TEXT NOT NULL,page INTEGER NOT NULL,source_url TEXT NOT NULL,sha256 TEXT NOT NULL,body BLOB NOT NULL,PRIMARY KEY(snapshot_id,page))')
        db.execute('INSERT OR IGNORE INTO outcome_snapshots VALUES(?,?,?,?)',(identifier,snapshot['profile_id'],snapshot['retrieved_at'],json.dumps(metadata)))
        for row in snapshot['observations']:
            # known_at is collection time, never the observation's historical
            # period. Proper release-vintage archives are still required.
            payload = {**row,'known_at':snapshot['retrieved_at'],'adjudication_status':'UNREVIEWED'}
            db.execute('INSERT OR IGNORE INTO outcome_observations VALUES(?,?,?)',(identifier,row['key'],json.dumps(payload)))
        for page, response in enumerate(snapshot.get('_raw_responses',[])):
            raw = response['body']
            db.execute('INSERT OR IGNORE INTO outcome_raw_responses VALUES(?,?,?,?,?)',
                       (identifier,page,response['url'],hashlib.sha256(raw).hexdigest(),raw))
    return identifier


def coverage(category, factor, focus, path=None):
    matches = [(key,p) for key,p in PROFILES.items() if p['category'] == category and p['factor'] == factor and p['focus'].casefold() == (focus or 'World').strip().casefold()]
    result = {'status':'NO_MAPPED_OUTCOME_SOURCE' if not matches else 'NOT_COLLECTED', 'point_in_time_ready':False,
              'probability_model_ready':False, 'profiles':[]}
    path = Path(path) if path else database_path()
    for key, profile in matches:
        entry = {**profile,'id':key,'status':'NOT_COLLECTED','observation_count':0}
        if path.is_file():
            try:
                with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    row = db.execute('SELECT id,metadata FROM outcome_snapshots WHERE profile_id=? ORDER BY retrieved_at DESC LIMIT 1',(key,)).fetchone()
                    if row:
                        metadata = json.loads(row[1])
                        count = db.execute('SELECT COUNT(*) FROM outcome_observations WHERE snapshot_id=?',(row[0],)).fetchone()[0]
                        entry.update(status='COLLECTED_NEEDS_OUTCOME_REVIEW',observation_count=count,
                                     retrieved_at=metadata['retrieved_at'],source_urls=metadata['source_urls'],response_sha256=metadata['response_sha256'])
            except (sqlite3.Error, ValueError, KeyError, OSError):
                entry['status'] = 'OUTCOME_STORE_UNAVAILABLE'
        result['profiles'].append(entry)
    if any(p['status'] == 'COLLECTED_NEEDS_OUTCOME_REVIEW' for p in result['profiles']):
        result['status'] = 'COLLECTED_NEEDS_OUTCOME_REVIEW'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=sorted(PROFILES), required=True)
    parser.add_argument('--database', type=Path, default=database_path())
    args = parser.parse_args()
    try:
        snapshot = collect(args.profile)
        identifier = persist(snapshot,args.database)
    except (DataUnavailable, ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1,f'Outcome collection failed: {exc}. Existing snapshots were preserved.\n')
    print(json.dumps({'snapshot_id':identifier,'observations':len(snapshot['observations']),
                      'status':snapshot['status'],'point_in_time_ready':False,'probability_model_ready':False}))


if __name__ == '__main__':
    main()
