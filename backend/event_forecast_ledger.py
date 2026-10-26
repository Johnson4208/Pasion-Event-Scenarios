"""Immutable public research forecasts recorded before their outcome periods.

Resolution uses a later, complete source snapshot. Latest-vintage observed
values are not point-in-time release archives, and this ledger never promotes
an experimental forecast to calibrated status.
"""
from bisect import bisect_right
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit

import event_forecasts
import event_horizons
import event_outcome_data

METHOD = 'RETROSPECTIVE_SERIES_REFERENCE_V1'
PROFILES = {
    'us-volatility': ('Markets', 'Equity volatility', 'VIXCLS', 'RELATIVE_CHANGE', 7),
    'us-mortgages': ('Real Estate', 'Mortgage rates', 'MORTGAGE30US', 'PERCENTAGE_POINTS', 14),
}
THRESHOLDS = {'us-volatility': [-.25, -.10, .10, .25], 'us-mortgages': [-.25, .25]}
SOURCE_MAX_AGE = {'us-volatility': 7, 'us-mortgages': 21}
NOTICE = ('Predictions were recorded before maturity. Resolutions use the first adequate later '
          'latest-vintage source snapshot; historical publication timestamps and prospective '
          'calibration are not established. Repeated or overlapping forecast periods may be dependent.')
MAX_PENDING = 500


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (TypeError, AttributeError, ValueError):
        raise ValueError('INVALID_LEDGER_TIMESTAMP') from None


def _now(value):
    return _time(value.isoformat()) if isinstance(value, datetime) else datetime.now(timezone.utc)


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('INVALID_LEDGER_NUMBER')
    return float(value)


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('INVALID_LEDGER_OBSERVATION_DATE')
    return date.fromisoformat(value)


def _label(value, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('INVALID_LEDGER_DEFINITION')
    return value.strip()


def _focus(value):
    if _label(value).casefold() not in ('united states', 'us', 'usa', 'u.s.', 'u.s', 'america'):
        raise ValueError('UNSUPPORTED_LEDGER_CONTEXT')
    return 'United States'


def _context(value):
    if not isinstance(value, dict):
        raise ValueError('UNSUPPORTED_LEDGER_CONTEXT')
    context = {key: _label(value.get(key)) for key in ('category', 'factor', 'focus', 'horizon', 'basis')}
    _focus(context['focus'])
    if context['basis'] != 'END_STATE':
        raise ValueError('UNSUPPORTED_LEDGER_CONTEXT')
    event_horizons.info(context['horizon'])
    return context


def _context_key(context):
    return json.dumps([context['category'], context['factor'], _focus(context['focus']),
                       context['horizon'], context['basis']], separators=(',', ':'))


def _validated(model, now):
    if not isinstance(model, dict) or model.get('schema_version') != 2 or model.get('method') != METHOD or model.get('status') != 'RESEARCH_ESTIMATE_AVAILABLE':
        raise ValueError('UNSUPPORTED_LEDGER_MODEL')
    source = model.get('source')
    profile_id = source.get('profile_id') if isinstance(source, dict) else None
    if profile_id not in PROFILES:
        raise ValueError('UNSUPPORTED_LEDGER_PROFILE')
    category, factor, metric, change_unit, _ = PROFILES[profile_id]
    context = _context(model.get('context'))
    if (context['category'], context['factor']) != (category, factor) or source.get('metric') != metric or model.get('change_unit') != change_unit:
        raise ValueError('UNSUPPORTED_LEDGER_CONTEXT')
    if model.get('news_adjusted') is not False or model.get('calibrated_probability') is not False:
        raise ValueError('UNSUPPORTED_LEDGER_CALIBRATION_CLAIM')
    as_of, origin, maturity = (_time(model.get(key)) for key in ('as_of', 'forecast_origin_at', 'maturity_at'))
    duration = event_horizons.info(context['horizon'])['forecast_days']
    if profile_id == 'us-mortgages' and duration < 7:
        raise ValueError('INCOMPATIBLE_LEDGER_SOURCE_FREQUENCY')
    if not as_of <= origin <= now < maturity or maturity != origin + timedelta(days=duration):
        raise ValueError('FORECAST_MUST_BE_RECORDED_BEFORE_MATURITY')
    baseline = model.get('baseline')
    if not isinstance(baseline, dict):
        raise ValueError('INVALID_LEDGER_BASELINE')
    baseline_value = _number(baseline.get('value'))
    baseline_day = _day(baseline.get('observation_at'))
    if (baseline_day > origin.date() or (now.date() - baseline_day).days > SOURCE_MAX_AGE[profile_id]
            or change_unit == 'RELATIVE_CHANGE' and baseline_value <= 0):
        raise ValueError('INVALID_LEDGER_BASELINE')
    cuts = model.get('threshold_cuts')
    scenarios = model.get('scenarios')
    if not isinstance(cuts, list) or not 1 <= len(cuts) <= 99 or not isinstance(scenarios, list) or len(scenarios) != len(cuts) + 1:
        raise ValueError('INCOMPLETE_LEDGER_OUTCOME_FAMILY')
    cuts = [_number(value) for value in cuts]
    if cuts != THRESHOLDS[profile_id]:
        raise ValueError('INVALID_LEDGER_THRESHOLDS')
    definitions = []
    for index, row in enumerate(scenarios):
        if not isinstance(row, dict):
            raise ValueError('INCOMPLETE_LEDGER_OUTCOME_FAMILY')
        definition = {key: _label(row.get(key)) for key in ('id', 'title', 'resolution_rule')}
        for key, expected in (('lower_bound', cuts[index - 1] if index else None),
                              ('upper_bound', cuts[index] if index < len(cuts) else None)):
            if key in row and row[key] != expected:
                raise ValueError('INCONSISTENT_LEDGER_OUTCOME_BOUNDS')
            definition[key] = expected
        definitions.append(definition)
    ids = [row['id'] for row in definitions]
    probabilities = model.get('probabilities')
    if len(set(ids)) != len(ids) or not isinstance(probabilities, dict) or set(probabilities) != set(ids):
        raise ValueError('INCOMPLETE_LEDGER_OUTCOME_FAMILY')
    probabilities = {ident: _number(probabilities[ident]) for ident in ids}
    if any(not 0 <= value <= 1 for value in probabilities.values()) or abs(sum(probabilities.values()) - 1) > 1e-8:
        raise ValueError('INVALID_LEDGER_SIMPLEX')
    if model.get('mutually_exclusive') is not True or model.get('exhaustive') is not True:
        raise ValueError('INCOMPLETE_LEDGER_OUTCOME_FAMILY')
    counts = {}
    for field, minimum in (('training', 20), ('holdout', 10)):
        values, size = model.get(field + '_counts'), model.get(field + '_sample_count')
        if (not isinstance(values, dict) or set(values) != set(ids) or type(size) is not int
                or not minimum <= size <= 100000 or any(type(value) is not int or value < 0 for value in values.values())
                or sum(values.values()) != size):
            raise ValueError('INVALID_LEDGER_RESEARCH_COUNTS')
        counts[field] = {ident: values[ident] for ident in ids}
    expected_probabilities, expected_intervals = event_forecasts._estimate(counts['training'], model['training_sample_count'], 'END_STATE')
    intervals = model.get('intervals')
    if not isinstance(intervals, dict) or set(intervals) != set(ids) or model.get('interval_level') != .95:
        raise ValueError('INVALID_LEDGER_UNCERTAINTY')
    safe_intervals = {}
    for ident in ids:
        interval = intervals[ident]
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            raise ValueError('INVALID_LEDGER_UNCERTAINTY')
        interval = [_number(value) for value in interval]
        if (not math.isclose(probabilities[ident], expected_probabilities[ident], rel_tol=0, abs_tol=1e-10)
                or any(not math.isclose(value, expected, rel_tol=0, abs_tol=1e-10)
                       for value, expected in zip(interval, expected_intervals[ident]))):
            raise ValueError('INCONSISTENT_LEDGER_RESEARCH_ESTIMATE')
        safe_intervals[ident] = interval
    training_end = _day(model.get('training_period_end'))
    holdout_start, holdout_end = (_day(model.get(key)) for key in ('holdout_period_start', 'holdout_period_end'))
    if not training_end < holdout_start < holdout_end <= baseline_day:
        raise ValueError('INVALID_LEDGER_VALIDATION_PERIODS')
    validation = model.get('validation')
    if (not isinstance(validation, dict) or validation.get('status') != 'RETROSPECTIVE_HOLDOUT_ONLY'
            or validation.get('quality') not in ('LIMITED', 'RETROSPECTIVE_ONLY')
            or validation.get('point_in_time_validated') is not False
            or validation.get('prospectively_calibrated') is not False):
        raise ValueError('INVALID_LEDGER_VALIDATION_CLAIM')
    observed = {ident: counts['holdout'][ident]/model['holdout_sample_count'] for ident in ids}
    errors = {ident: abs(probabilities[ident]-observed[ident]) for ident in ids}
    expected_scores = {
        'brier_score': 1 + sum(value*value for value in probabilities.values()) - 2*sum(observed[ident]*probabilities[ident] for ident in ids),
        'log_loss': -sum(observed[ident]*math.log(probabilities[ident]) for ident in ids),
        'maximum_rate_error': max(errors.values()),
    }
    if any(not math.isclose(_number(validation.get(key)), value, rel_tol=0, abs_tol=1e-10) for key, value in expected_scores.items()):
        raise ValueError('INCONSISTENT_LEDGER_VALIDATION_SCORES')
    urls = source.get('source_urls', [])
    if not isinstance(urls, list) or not urls or len(urls) > 8:
        raise ValueError('INVALID_LEDGER_SOURCE')
    for url in urls:
        if not isinstance(url, str):
            raise ValueError('INVALID_LEDGER_SOURCE')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'fred.stlouisfed.org' or parsed.username or parsed.password
                or parsed.path != '/graph/fredgraph.csv' or parse_qs(parsed.query) != {'id': [metric]}):
            raise ValueError('INVALID_LEDGER_SOURCE')
    # Explicit public fields only: arbitrary model/operator/account metadata is
    # never copied into this shared research ledger.
    safe = {key: _label(model.get(key)) for key in ('family_id', 'definition_version', 'model_version', 'question')}
    safe.update(schema_version=2, method=METHOD, status='RESEARCH_ESTIMATE_AVAILABLE',
                context=context, as_of=as_of.isoformat(), forecast_origin_at=origin.isoformat(),
                maturity_at=maturity.isoformat(), baseline={'value': baseline_value,
                'observation_at': baseline_day.isoformat(), 'unit': _label(baseline.get('unit'))},
                threshold_cuts=cuts, change_unit=change_unit, scenarios=definitions,
                probabilities=probabilities, calibrated_probability=False, news_adjusted=False,
                mutually_exclusive=True, exhaustive=True,
                intervals=safe_intervals, interval_level=.95,
                training_counts=counts['training'], holdout_counts=counts['holdout'],
                training_sample_count=model['training_sample_count'], holdout_sample_count=model['holdout_sample_count'],
                training_period_end=training_end.isoformat(), holdout_period_start=holdout_start.isoformat(),
                holdout_period_end=holdout_end.isoformat(),
                validation={'status': 'RETROSPECTIVE_HOLDOUT_ONLY', 'quality': validation['quality'],
                            **expected_scores, 'point_in_time_validated': False, 'prospectively_calibrated': False},
                source={'profile_id': profile_id, 'provider': 'FRED', 'metric': metric,
                        'source_urls': list(urls), 'snapshot_id': _label(source.get('snapshot_id')),
                        'retrieved_at': _time(source.get('retrieved_at')).isoformat()})
    if _time(safe['source']['retrieved_at']) > origin:
        raise ValueError('FUTURE_LEDGER_SOURCE')
    return safe


def _path(path):
    return Path(path) if path is not None else event_outcome_data.database_path()


def _connect(path, readonly=False):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=8) if readonly else sqlite3.connect(path, timeout=8)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA foreign_keys=ON')
    return db


def _initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS event_series_predictions (
            id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, maturity_at TEXT NOT NULL,
            profile_id TEXT NOT NULL, context_key TEXT NOT NULL,
            forecast_sha256 TEXT NOT NULL UNIQUE, forecast_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS event_series_resolutions (
            forecast_id TEXT PRIMARY KEY REFERENCES event_series_predictions(id),
            resolved_at TEXT NOT NULL, source_snapshot_id TEXT NOT NULL,
            observation_at TEXT NOT NULL, outcome_id TEXT NOT NULL,
            resolution_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS event_series_predictions_context
            ON event_series_predictions(context_key, recorded_at DESC);
    ''')


def record(model, now=None, path=None):
    """Record a whole public forecast once, without replacing its prior values."""
    now = _now(now)
    safe = _validated(model, now)
    payload = json.dumps(safe, sort_keys=True, separators=(',', ':'), allow_nan=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    ident = 'series-' + digest[:32]
    location = _path(path)
    if not location.is_file():
        raise ValueError('LEDGER_SOURCE_SNAPSHOT_REQUIRED')
    with closing(_connect(location)) as db, db:
        if not {'outcome_snapshots', 'outcome_observations'}.issubset(_tables(db)):
            raise ValueError('LEDGER_SOURCE_SNAPSHOT_REQUIRED')
        snapshot = db.execute('SELECT id,profile_id,retrieved_at,metadata FROM outcome_snapshots WHERE id=?',
                              (safe['source']['snapshot_id'],)).fetchone()
        observations = _snapshot_observations(db, snapshot, now) if snapshot else None
        baseline_day = _day(safe['baseline']['observation_at'])
        if not snapshot or snapshot['profile_id'] != safe['source']['profile_id'] or not observations or baseline_day != max(observations) or not math.isclose(
                observations[baseline_day], safe['baseline']['value'], rel_tol=1e-12, abs_tol=1e-12) or _time(snapshot['retrieved_at']) != _time(safe['source']['retrieved_at']):
            raise ValueError('LEDGER_BASELINE_SOURCE_MISMATCH')
        _initialize(db)
        db.execute('INSERT OR IGNORE INTO event_series_predictions VALUES (?,?,?,?,?,?,?)',
                   (ident, now.isoformat(), safe['maturity_at'], safe['source']['profile_id'],
                    _context_key(safe['context']), digest, payload))
        row = db.execute('SELECT recorded_at,maturity_at FROM event_series_predictions WHERE id=?', (ident,)).fetchone()
        resolved = db.execute('SELECT 1 FROM event_series_resolutions WHERE forecast_id=?', (ident,)).fetchone()
    return {'id': ident, 'recorded_at': row['recorded_at'], 'maturity_at': row['maturity_at'],
            'status': 'RESOLVED' if resolved else 'PENDING', 'calibration_status': 'NOT_ESTABLISHED'}


def _tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _snapshot_observations(db, snapshot, now):
    try:
        retrieved = _time(snapshot['retrieved_at'])
        metadata = json.loads(snapshot['metadata'])
        if retrieved > now or metadata.get('status') != 'COLLECTED_NEEDS_OUTCOME_REVIEW':
            return None
        if (metadata.get('profile_id') != snapshot['profile_id']
                or _time(metadata.get('retrieved_at')) != retrieved):
            return None
        profile = metadata.get('profile')
        expected = event_outcome_data.PROFILES[snapshot['profile_id']]
        if not isinstance(profile, dict) or any(profile.get(key) != expected[key] for key in ('provider', 'metric', 'category', 'factor', 'focus')):
            return None
        observations = {}
        for index, row in enumerate(db.execute('SELECT payload FROM outcome_observations WHERE snapshot_id=?', (snapshot['id'],))):
            if index >= 50000:
                return None
            payload = json.loads(row[0])
            period, value = _day(payload['period']), _number(payload['value'])
            if period > retrieved.date() or period in observations or _time(payload['known_at']) != retrieved:
                return None
            observations[period] = value
        return observations
    except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        return None


def resolve_due(now=None, path=None):
    """Resolve matured predictions from adequate later snapshots, never news."""
    now, location = _now(now), _path(path)
    if not location.is_file():
        return {'status': 'UNINITIALIZED', 'resolved': 0, 'pending': 0, 'calibration_status': 'NOT_ESTABLISHED'}
    with closing(_connect(location)) as db, db:
        tables = _tables(db)
        if 'event_series_predictions' not in tables:
            return {'status': 'UNINITIALIZED', 'resolved': 0, 'pending': 0, 'calibration_status': 'NOT_ESTABLISHED'}
        _initialize(db)
        pending = db.execute('SELECT p.* FROM event_series_predictions p LEFT JOIN event_series_resolutions r '
                             'ON r.forecast_id=p.id WHERE r.forecast_id IS NULL AND p.maturity_at<=? '
                             'ORDER BY p.recorded_at LIMIT ?', (now.isoformat(), MAX_PENDING)).fetchall()
        completed, cached = 0, {}
        for row in pending:
            maturity = _time(row['maturity_at'])
            if maturity > now or not {'outcome_snapshots', 'outcome_observations'}.issubset(tables):
                continue
            model = json.loads(row['forecast_json'])
            snapshots = []
            for snapshot in db.execute('SELECT id,profile_id,retrieved_at,metadata FROM outcome_snapshots '
                                       'WHERE profile_id=?', (row['profile_id'],)):
                try:
                    retrieved = _time(snapshot['retrieved_at'])
                    if maturity <= retrieved <= now:
                        snapshots.append((retrieved, snapshot['id'], snapshot))
                except ValueError:
                    continue
            # Order actual instants, not ISO text, so recovered snapshots with
            # different UTC offsets retain the first adequate vintage policy.
            for retrieved, _, snapshot in sorted(snapshots, key=lambda entry: entry[:2]):
                if snapshot['id'] not in cached:
                    cached[snapshot['id']] = _snapshot_observations(db, snapshot, now)
                observations = cached[snapshot['id']]
                if not observations or max(observations) < maturity.date():
                    # A later retrieval of an old/incomplete series does not
                    # prove what was observed by the target period.
                    continue
                eligible = [period for period in observations if period <= maturity.date()]
                if not eligible:
                    continue
                period = max(eligible)
                gap = (maturity.date() - period).days
                if gap > PROFILES[row['profile_id']][-1] or period <= _day(model['baseline']['observation_at']):
                    continue
                observed = observations[period]
                baseline = model['baseline']['value']
                if model['change_unit'] == 'RELATIVE_CHANGE':
                    if observed <= 0:
                        continue
                    change = observed / baseline - 1
                else:
                    change = observed - baseline
                outcome = model['scenarios'][bisect_right(model['threshold_cuts'], change)]['id']
                resolution = {'outcome_id': outcome, 'observed_value': observed, 'change': change,
                              'observation_at': period.isoformat(), 'maturity_at': maturity.isoformat(),
                              'source_snapshot_id': snapshot['id'], 'source_retrieved_at': retrieved.isoformat(),
                              'resolved_at': now.isoformat(), 'resolution_policy': 'FIRST_ADEQUATE_LATER_LATEST_VINTAGE_SNAPSHOT',
                              'point_in_time_release_archive': False, 'adjudication_status': 'UNREVIEWED', 'notice': NOTICE}
                db.execute('INSERT OR IGNORE INTO event_series_resolutions VALUES (?,?,?,?,?,?)',
                           (row['id'], now.isoformat(), snapshot['id'], period.isoformat(), outcome,
                            json.dumps(resolution, sort_keys=True, allow_nan=False)))
                completed += 1
                break
        remaining = db.execute('SELECT count(*) FROM event_series_predictions p LEFT JOIN event_series_resolutions r '
                               'ON r.forecast_id=p.id WHERE r.forecast_id IS NULL').fetchone()[0]
    return {'status': 'READY', 'resolved': completed, 'pending': remaining, 'calibration_status': 'NOT_ESTABLISHED', 'notice': NOTICE}


def summary(context=None, limit=20, now=None, path=None):
    """Read public ledger status without creating a database or source table."""
    now, location = _now(now), _path(path)
    if type(limit) is not int:
        raise ValueError('INVALID_LEDGER_LIMIT')
    limit = min(100, max(1, limit))
    empty = {'status': 'UNINITIALIZED', 'forecast_count': 0, 'resolved_count': 0, 'pending_count': 0,
             'due_count': 0, 'recent': [], 'brier_score': None, 'log_loss': None,
             'calibration_status': 'NOT_ESTABLISHED', 'notice': NOTICE}
    if not location.is_file():
        return empty
    with closing(_connect(location, readonly=True)) as db:
        if not {'event_series_predictions', 'event_series_resolutions'}.issubset(_tables(db)):
            return empty
        condition, params = (' WHERE p.context_key=?', (_context_key(_context(context)),)) if context else ('', ())
        rows = db.execute('SELECT p.*,r.resolved_at,r.outcome_id,r.resolution_json FROM event_series_predictions p '
                          'LEFT JOIN event_series_resolutions r ON r.forecast_id=p.id' + condition + ' ORDER BY p.recorded_at DESC', params).fetchall()
        recent, briers, losses = [], [], []
        for row in rows:
            model = json.loads(row['forecast_json'])
            if row['outcome_id']:
                probabilities = model['probabilities']
                briers.append(sum((value - int(ident == row['outcome_id']))**2 for ident, value in probabilities.items()))
                losses.append(-math.log(max(probabilities[row['outcome_id']], 1e-15)))
            if len(recent) < limit:
                recent.append({'id': row['id'], 'recorded_at': row['recorded_at'], 'maturity_at': row['maturity_at'],
                               'profile_id': row['profile_id'], 'context': model['context'],
                               'status': 'RESOLVED' if row['outcome_id'] else 'PENDING',
                               'probabilities': model['probabilities'], 'outcome_id': row['outcome_id'],
                               'intervals': model.get('intervals'), 'interval_level': model.get('interval_level'),
                               'validation': model.get('validation'), 'baseline': model['baseline'],
                               'resolved_at': row['resolved_at']})
        return {**empty, 'status': 'READY', 'forecast_count': len(rows), 'resolved_count': len(briers),
                'pending_count': len(rows) - len(briers),
                'due_count': sum(not row['outcome_id'] and _time(row['maturity_at']) <= now for row in rows),
                'recent': recent, 'brier_score': sum(briers)/len(briers) if briers else None,
                'log_loss': sum(losses)/len(losses) if losses else None,
                'evaluation_scope': 'IMMUTABLE_PRE_MATURITY_FORECASTS_WITH_LATEST_VINTAGE_UNREVIEWED_RESOLUTIONS'}
