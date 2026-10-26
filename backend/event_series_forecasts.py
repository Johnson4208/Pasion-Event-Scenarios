"""Automatic, retrospective reference estimates from declared public series.

These are research probabilities for measured end states, not calibrated news
forecasts. Historical publication timestamps are not fabricated: the source is
the latest vintage, and the evaluation is explicitly retrospective.
"""
from __future__ import annotations

import bisect
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading

import event_forecasts
import event_horizons
import event_outcome_data


METHOD = 'RETROSPECTIVE_SERIES_REFERENCE_V1'
MIN_TRAINING = 20
MIN_HOLDOUT = 10
PREPARE_INTERVAL_SECONDS = 60
MAX_OBSERVATIONS = 100000
MODEL_LIFETIME = timedelta(hours=24)
_LOCK = threading.RLock()
_PREPARING = set()
_PROFILES = {
    'us-volatility': {
        'category': 'Markets', 'factor': 'Equity volatility', 'focus': 'United States',
        'cuts': [-.25, -.10, .10, .25], 'change_unit': 'RELATIVE_CHANGE',
        'ids': ['large_decrease', 'decrease', 'little_change', 'increase', 'large_increase'],
        'titles': ['VIX decreases by more than 25%', 'VIX decrease greater than 10% and at most 25%',
                   'VIX change from -10% to less than +10%', 'VIX increase from 10% to less than 25%', 'VIX increase of at least 25%'],
        'label': 'CBOE VIX index', 'family_id': 'us-vix-relative-change',
        'definition_version': 'vix-end-state-v1', 'minimum_horizon': 1,
        'endpoint_gap_days': 7, 'source_max_age_days': 7,
    },
    'us-mortgages': {
        'category': 'Real Estate', 'factor': 'Mortgage rates', 'focus': 'United States',
        'cuts': [-.25, .25], 'change_unit': 'PERCENTAGE_POINTS',
        'ids': ['lower', 'little_change', 'higher'],
        'titles': ['Mortgage rate decreases by more than 0.25 percentage points',
                   'Mortgage rate change from -0.25 to less than +0.25 percentage points',
                   'Mortgage rate increases by at least 0.25 percentage points'],
        'label': 'US 30-year fixed mortgage survey rate', 'family_id': 'us-mortgage-rate-change',
        'definition_version': 'mortgage-end-state-v1', 'minimum_horizon': 7,
        'endpoint_gap_days': 14, 'source_max_age_days': 21,
    },
}


def _now(value=None):
    value = value or datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('A timezone-aware forecast time is required')
    return value.astimezone(timezone.utc)


def _instant(value):
    if not isinstance(value, str):
        raise ValueError('Invalid timestamp')
    return _now(datetime.fromisoformat(value.replace('Z', '+00:00')))


def _context(category, factor, focus, horizon, basis):
    values = dict(category=category, factor=factor, focus=focus or 'World', horizon=horizon, basis=basis)
    if any(not isinstance(value, str) or not value.strip() or len(value) > 120 for value in values.values()):
        raise ValueError('Invalid research configuration')
    return {key: value.strip() for key, value in values.items()}


def _unavailable(context, status, reason, requirements, **extra):
    return {'schema_version': 2, 'method': METHOD, 'status': status, 'reason_code': reason,
            'context': context, 'missing_requirements': list(requirements), 'scenarios': [],
            'probabilities': None, 'intervals': None, 'news_adjusted': False,
            'calibrated_probability': False, **extra}


def _profile(context):
    us_aliases = {'united states', 'us', 'usa', 'u.s.', 'u.s', 'america'}
    for ident, profile in _PROFILES.items():
        if (context['category'] == profile['category'] and context['factor'] == profile['factor']
                and context['focus'].casefold() in us_aliases):
            return ident, profile
    return None, None


def _configuration(category, factor, focus, horizon, basis):
    context = _context(category, factor, focus, horizon, basis)
    ident, profile = _profile(context)
    if profile is None:
        return context, None, None, _unavailable(context, 'UNSUPPORTED_CONTEXT', 'NO_OPERATIONAL_SERIES_PROFILE',
            ['MEASURABLE_OUTCOME_DEFINITION', 'SOURCE_DATA', 'HISTORICAL_MODEL'])
    if basis != 'END_STATE':
        return context, ident, profile, _unavailable(context, 'UNSUPPORTED_HORIZON', 'END_STATE_BASIS_REQUIRED', ['END_STATE_BASIS'])
    try:
        days = event_horizons.info(horizon)['forecast_days']
    except ValueError:
        return context, ident, profile, _unavailable(context, 'UNSUPPORTED_HORIZON', 'UNKNOWN_FORECAST_HORIZON', ['SUPPORTED_HORIZON'])
    if days < profile['minimum_horizon']:
        return context, ident, profile, _unavailable(context, 'UNSUPPORTED_HORIZON', 'SOURCE_FREQUENCY_INCOMPATIBLE', ['COMPATIBLE_MEASUREMENT_FREQUENCY'])
    return context, ident, profile, None


def _definitions(profile):
    cuts = profile['cuts']
    change = '(end observation / baseline observation) - 1' if profile['change_unit'] == 'RELATIVE_CHANGE' else 'end survey rate minus baseline survey rate, in percentage points'
    result = []
    for index, (ident, title) in enumerate(zip(profile['ids'], profile['titles'])):
        lower = None if index == 0 else cuts[index-1]
        upper = None if index == len(cuts) else cuts[index]
        bounds = ('no lower bound' if lower is None else f'change >= {lower:g}') + '; ' + ('no upper bound' if upper is None else f'change < {upper:g}')
        result.append({'id': ident, 'title': title, 'lower_bound': lower, 'upper_bound': upper,
                       'resolution_rule': f'{profile["label"]}: change = {change}; {bounds}. '
                       f'Use the last source observation on or before the target UTC date, at most {profile["endpoint_gap_days"]} days earlier; never use a future observation.'})
    return result


def options():
    """Return declared coverage without network requests or database writes."""
    return [{'id': ident, 'profile_id': ident, 'label': profile['label'],
             'context': {key: profile[key] for key in ('category', 'factor', 'focus')} | {'horizon': '30 days', 'basis': 'END_STATE'},
             'category': profile['category'], 'factor': profile['factor'], 'focus': profile['focus'],
             'supported_horizons': [key for key, value in event_horizons.HORIZONS.items() if value[0] >= profile['minimum_horizon']],
             'default_horizon': '30 days', 'default_basis': 'END_STATE',
             'scenarios': _definitions(profile), 'threshold_cuts': list(profile['cuts']),
             'change_unit': profile['change_unit'], 'source': dict(event_outcome_data.PROFILES[ident]),
             'minimum_training_count': MIN_TRAINING, 'minimum_holdout_count': MIN_HOLDOUT,
             'method': METHOD, 'calibrated_probability': False}
            for ident, profile in _PROFILES.items()]


def _directory():
    return Path(os.environ.get('PASION_EVENT_SERIES_DIR', Path(__file__).resolve().parent/'private-event-models'/'series')).expanduser().resolve()


def _path(ident, horizon):
    # Both components are selected from fixed tables, never browser paths.
    return _directory()/(ident+'-'+horizon.replace(' ', '-')+'.json')


@contextmanager
def _preparation_lock(ident):
    """One preparation per public source, across threads and local processes."""
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = (str(directory), ident)
    with _LOCK:
        if key in _PREPARING:
            raise BlockingIOError('Preparation in progress')
        _PREPARING.add(key)
    stream = None
    locked = False
    try:
        stream = (directory/('.prepare-'+ident+'.lock')).open('a+b')
        if os.name == 'nt':
            import msvcrt
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b'\0')
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield stream
    finally:
        if stream is not None:
            if locked:
                if os.name == 'nt':
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()
        with _LOCK:
            _PREPARING.discard(key)


def _history_path():
    path = event_outcome_data.database_path().expanduser().resolve()
    if path.name.casefold() in {'accounts.sqlite3', 'documents.sqlite3', 'finance.sqlite3', 'macro.sqlite3', 'technical.sqlite3', 'stock_models.sqlite3'}:
        raise ValueError('Outcome history must be separate from application databases')
    return path


def _stored_snapshot(ident, now):
    path = _history_path()
    if not path.is_file():
        return None
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=5)
        connection.execute('PRAGMA trusted_schema=OFF')
        row = connection.execute('SELECT id,metadata FROM outcome_snapshots WHERE profile_id=? ORDER BY retrieved_at DESC LIMIT 1', (ident,)).fetchone()
        if not row:
            return None
        metadata = json.loads(row[1])
        retrieved = _instant(metadata['retrieved_at'])
        if not retrieved <= now or retrieved.date() != now.date() or metadata.get('profile_id') != ident:
            return None
        observations = connection.execute('SELECT payload FROM outcome_observations WHERE snapshot_id=? ORDER BY observation_key LIMIT ?', (row[0], MAX_OBSERVATIONS+1)).fetchall()
        if len(observations) > MAX_OBSERVATIONS:
            return None
        return ({**metadata, 'observations': [json.loads(record[0]) for record in observations]}, row[0])
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        return None
    finally:
        if connection is not None:
            connection.close()


def _source_snapshot(ident, now, lock_stream):
    existing = _stored_snapshot(ident, now)
    if existing is not None:
        return existing
    lock_stream.seek(0)
    try:
        last = json.loads(lock_stream.read(4096).lstrip(b'\0') or b'{}').get('last_attempt_at')
        if last and 0 <= (now-_instant(last)).total_seconds() < PREPARE_INTERVAL_SECONDS:
            raise BlockingIOError('Preparation rate limit')
    except (ValueError, TypeError, AttributeError):
        pass
    lock_stream.seek(0)
    lock_stream.truncate()
    lock_stream.write(json.dumps({'last_attempt_at': now.isoformat()}).encode())
    lock_stream.flush()
    os.fsync(lock_stream.fileno())
    snapshot = event_outcome_data.collect(ident, now=now)
    # Do not make a malformed or future-dated provider response the snapshot
    # reused by every subsequent request for the rest of the UTC day.
    _observations(snapshot, ident, now)
    # Collection uses the real retrieval time. It never backdates historical
    # observation availability or marks mechanically derived cases as reviewed.
    snapshot_id = event_outcome_data.persist(snapshot, path=_history_path())
    return snapshot, snapshot_id


def _observations(snapshot, ident, now):
    expected = event_outcome_data.PROFILES[ident]
    profile = snapshot.get('profile')
    if (snapshot.get('profile_id') != ident or not isinstance(profile, dict)
            or any(profile.get(key) != expected.get(key) for key in ('provider', 'metric', 'category', 'factor', 'focus'))):
        raise ValueError('SOURCE_CONTEXT_MISMATCH')
    retrieved = _instant(snapshot['retrieved_at'])
    if retrieved > now:
        raise ValueError('FUTURE_SOURCE_RETRIEVAL')
    rows = snapshot.get('observations')
    if not isinstance(rows, list) or not rows or len(rows) > MAX_OBSERVATIONS:
        raise ValueError('INVALID_SOURCE_OBSERVATIONS')
    output = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('period'), str):
            raise ValueError('INVALID_SOURCE_OBSERVATION')
        period = date.fromisoformat(row['period'])
        value = row.get('value')
        if period in seen or period > min(now.date(), retrieved.date()):
            raise ValueError('DUPLICATE_OR_FUTURE_PERIOD')
        if type(value) not in (int, float) or not math.isfinite(value) or (ident == 'us-volatility' and value <= 0):
            raise ValueError('INVALID_SOURCE_VALUE')
        seen.add(period)
        output.append((period, float(value)))
    return sorted(output)


def _pairs(series, duration_days, profile):
    """Use disjoint periods and the last observed endpoint, never future data."""
    dates = [row[0] for row in series]
    last_target = None
    pairs = []
    skipped = 0
    for origin_index, (origin, baseline) in enumerate(series):
        if last_target is not None and origin <= last_target:
            continue
        target = origin+timedelta(days=duration_days)
        if target > dates[-1]:
            break
        end_index = bisect.bisect_right(dates, target)-1
        endpoint, final = series[end_index]
        if end_index <= origin_index or (target-endpoint).days > profile['endpoint_gap_days']:
            skipped += 1
            continue
        change = final/baseline-1 if profile['change_unit'] == 'RELATIVE_CHANGE' else final-baseline
        label = profile['ids'][bisect.bisect_right(profile['cuts'], change)]
        pairs.append({'origin': origin, 'target': target, 'endpoint': endpoint, 'outcome_id': label})
        last_target = target
    return pairs, skipped


def _counts(pairs, ids):
    result = {ident: 0 for ident in ids}
    for pair in pairs:
        result[pair['outcome_id']] += 1
    return result


def _validation(train_counts, hold_counts):
    """Describe a held-out historical check without certifying calibration."""
    n_train, n_holdout = sum(train_counts.values()), sum(hold_counts.values())
    probabilities, _ = event_forecasts._estimate(train_counts, n_train, 'END_STATE')
    observed = {key: hold_counts[key]/n_holdout for key in train_counts}
    errors = {key: abs(probabilities[key]-observed[key]) for key in train_counts}
    brier = 1+sum(value*value for value in probabilities.values())-2*sum(observed[key]*probabilities[key] for key in train_counts)
    loss = -sum(observed[key]*math.log(probabilities[key]) for key in train_counts)
    flags = []
    if n_train < 100: flags.append('SMALL_TRAINING_SAMPLE')
    if n_holdout < 100: flags.append('SMALL_HOLDOUT_SAMPLE')
    if min(train_counts.values()) < 5 or min(hold_counts.values()) < 3: flags.append('RARE_OR_UNOBSERVED_OUTCOMES')
    limits = {key: min(.15, 1.96*math.sqrt(probabilities[key]*(1-probabilities[key])*(1/n_train+1/n_holdout))) for key in train_counts}
    if any(errors[key] > limits[key] for key in train_counts): flags.append('HOLDOUT_RATE_DRIFT')
    return {'status': 'RETROSPECTIVE_HOLDOUT_ONLY', 'quality': 'LIMITED' if flags else 'RETROSPECTIVE_ONLY',
            'brier_score': brier, 'log_loss': loss, 'maximum_rate_error': max(errors.values()),
            'per_outcome_rate_error': errors, 'quality_flags': flags,
            'zero_change_benchmark_brier': 2*(1-observed['little_change']),
            'point_in_time_validated': False, 'prospectively_calibrated': False}


def _build(snapshot, snapshot_id, context, ident, profile, now):
    series = _observations(snapshot, ident, now)
    baseline_date, baseline_value = series[-1]
    age = (now.date()-baseline_date).days
    if age > profile['source_max_age_days']:
        return _unavailable(context, 'STALE_SOURCE', 'LATEST_OBSERVATION_TOO_OLD', ['FRESH_SOURCE_OBSERVATION'],
                            baseline={'value': baseline_value, 'observation_at': baseline_date.isoformat(), 'unit': snapshot['profile']['unit']})
    horizon_days = event_horizons.info(context['horizon'])['forecast_days']
    maturity = now+timedelta(days=horizon_days)
    duration = (maturity.date()-baseline_date).days
    pairs, skipped = _pairs(series, duration, profile)
    if len(pairs) < MIN_TRAINING+MIN_HOLDOUT:
        return _unavailable(context, 'INSUFFICIENT_HISTORY', 'TOO_FEW_NONOVERLAPPING_PERIODS',
                            ['AT_LEAST_20_TRAINING_AND_10_HOLDOUT_PERIODS'], available_period_count=len(pairs))
    split = min(len(pairs)-MIN_HOLDOUT, max(MIN_TRAINING, int(len(pairs)*.7)))
    training, holdout = pairs[:split], pairs[split:]
    if training[-1]['target'] >= holdout[0]['origin']:
        raise ValueError('OVERLAPPING_VALIDATION_PERIODS')
    train_counts = _counts(training, profile['ids'])
    hold_counts = _counts(holdout, profile['ids'])
    probabilities, intervals = event_forecasts._estimate(train_counts, len(training), 'END_STATE')
    digest_payload = {'profile_id': ident, 'series': [(period.isoformat(), value) for period, value in series],
                      'source_response_sha256': snapshot.get('response_sha256'), 'duration_days': duration,
                      'threshold_cuts': profile['cuts'], 'method': METHOD}
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    source_profile = snapshot['profile']
    return {'schema_version': 2, 'method': METHOD, 'status': 'RESEARCH_ESTIMATE_AVAILABLE', 'context': context,
            'family_id': profile['family_id'], 'definition_version': profile['definition_version'],
            'model_version': METHOD+':'+digest[:16],
            'question': f'At {maturity.date().isoformat()}, how will the last available {profile["label"]} observation compare with its {baseline_date.isoformat()} baseline?',
            'scenarios': _definitions(profile), 'probabilities': probabilities, 'intervals': intervals, 'interval_level': .95,
            'training_counts': train_counts, 'holdout_counts': hold_counts,
            'training_sample_count': len(training), 'holdout_sample_count': len(holdout),
            'validation': _validation(train_counts, hold_counts),
            'training_period_start': training[0]['origin'].isoformat(), 'training_period_end': training[-1]['target'].isoformat(),
            'holdout_period_start': holdout[0]['origin'].isoformat(), 'holdout_period_end': holdout[-1]['target'].isoformat(),
            'sampling_policy': f'Disjoint source-observation origins; each next origin is strictly after the preceding target. '
                f'Historical targets are {duration} calendar days after each baseline; endpoint is the last source observation on or before target, '
                f'no more than {profile["endpoint_gap_days"]} days earlier. Chronological approximately 70/30 split; holdout never fits the probabilities. '
                'Minimum 20 training and 10 holdout periods is a research display policy, not proof of calibration. '
                'Latest-vintage retrospective data; publication availability and residual dependence are not verified.',
            'as_of': now.isoformat(), 'forecast_origin_at': now.isoformat(), 'maturity_at': maturity.isoformat(),
            'expires_at': (now+MODEL_LIFETIME).isoformat(), 'effective_duration_days': duration, 'baseline_age_days': age,
            'endpoint_max_gap_days': profile['endpoint_gap_days'], 'skipped_missing_periods': skipped,
            'baseline': {'value': baseline_value, 'observation_at': baseline_date.isoformat(), 'unit': source_profile['unit']},
            'source': {'profile_id': ident, 'provider': source_profile['provider'], 'metric': source_profile['metric'],
                       'source_urls': snapshot['source_urls'], 'retrieved_at': snapshot['retrieved_at'],
                       'snapshot_id': snapshot_id, 'observation_count': len(series)},
            'dataset_sha256': digest, 'threshold_cuts': list(profile['cuts']), 'change_unit': profile['change_unit'],
            'news_adjusted': False, 'calibrated_probability': False, 'mutually_exclusive': True, 'exhaustive': True,
            'smoothing': 'Symmetric Jeffreys half-count per outcome. Unobserved outcomes retain prior uncertainty.',
            'uncertainty_notice': '95% credible intervals concern historical outcome rates under stationarity assumptions; they are not 95% future-prediction accuracy. Current news does not numerically adjust these estimates.'}


def _atomic_model(path, model):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix='.series-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(model, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _valid_cached(model, context, ident, profile, now):
    if (not isinstance(model, dict) or model.get('schema_version') != 2 or model.get('method') != METHOD
            or model.get('status') != 'RESEARCH_ESTIMATE_AVAILABLE' or _profile(model.get('context', {}))[0] != ident
            or model['context'].get('horizon') != context['horizon'] or model['context'].get('basis') != 'END_STATE'):
        return False
    start, end = _instant(model['as_of']), _instant(model['expires_at'])
    if not start <= now < end or end > start+MODEL_LIFETIME:
        return False
    baseline = date.fromisoformat(model['baseline']['observation_at'])
    maturity = _instant(model['maturity_at'])
    origin = _instant(model['forecast_origin_at'])
    if (origin != start or maturity != origin+timedelta(days=event_horizons.info(context['horizon'])['forecast_days'])
            or baseline > start.date() or (now.date()-baseline).days > profile['source_max_age_days']
            or model.get('effective_duration_days') != (maturity.date()-baseline).days):
        return False
    baseline_value = model['baseline']['value']
    if type(baseline_value) not in (int, float) or not math.isfinite(baseline_value) or (ident == 'us-volatility' and baseline_value <= 0):
        return False
    source = model['source']
    expected_source = event_outcome_data.PROFILES[ident]
    if any(source.get(key) != expected_source[key] for key in ('provider', 'metric')) or _instant(source['retrieved_at']) > start:
        return False
    if (source.get('source_urls') != ['https://fred.stlouisfed.org/graph/fredgraph.csv?id='+expected_source['metric']]
            or not re.fullmatch(r'[0-9a-f]{64}', source.get('snapshot_id', ''))
            or not re.fullmatch(r'[0-9a-f]{64}', model.get('dataset_sha256', ''))
            or model.get('family_id') != profile['family_id'] or model.get('definition_version') != profile['definition_version']):
        return False
    training_end = date.fromisoformat(model['training_period_end'])
    holdout_start, holdout_end = [date.fromisoformat(model[key]) for key in ('holdout_period_start', 'holdout_period_end')]
    if not training_end < holdout_start < holdout_end <= baseline:
        return False
    ids = profile['ids']
    if model.get('threshold_cuts') != profile['cuts'] or model.get('change_unit') != profile['change_unit']:
        return False
    if model.get('scenarios') != _definitions(profile) or model.get('source', {}).get('profile_id') != ident:
        return False
    if any(model.get(key) is not expected for key, expected in (('calibrated_probability', False), ('news_adjusted', False), ('mutually_exclusive', True), ('exhaustive', True))):
        return False
    for key, size_name in (('training_counts', 'training_sample_count'), ('holdout_counts', 'holdout_sample_count')):
        counts, size = model[key], model[size_name]
        if type(size) is not int or not (MIN_TRAINING if key == 'training_counts' else MIN_HOLDOUT) <= size <= MAX_OBSERVATIONS:
            return False
        if set(counts) != set(ids) or any(type(value) is not int or value < 0 for value in counts.values()) or sum(counts.values()) != size:
            return False
    if set(model['probabilities']) != set(ids) or set(model['intervals']) != set(ids) or model.get('interval_level') != .95:
        return False
    expected, expected_intervals = event_forecasts._estimate(model['training_counts'], model['training_sample_count'], 'END_STATE')
    for ident in ids:
        probability, interval = model['probabilities'][ident], model['intervals'][ident]
        if (type(probability) not in (int, float) or not math.isfinite(probability) or abs(probability-expected[ident]) > 1e-10
                or not isinstance(interval, list) or len(interval) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in interval)
                or not 0 <= interval[0] <= probability <= interval[1] <= 1
                or any(abs(value-expected_value) > 1e-10 for value, expected_value in zip(interval, expected_intervals[ident]))):
            return False
    if abs(sum(model['probabilities'].values())-1) > 1e-9:
        return False
    validation = model.get('validation', {})
    expected_validation = _validation(model['training_counts'], model['holdout_counts'])
    return validation == expected_validation


def forecast(category, factor, focus, horizon, basis='END_STATE', now=None):
    """Read a fixed prepared forecast only; GET never fetches or writes data."""
    now = _now(now)
    context, ident, profile, unavailable = _configuration(category, factor, focus, horizon, basis)
    if unavailable:
        return unavailable
    try:
        with _path(ident, horizon).open('rb') as stream:
            raw = stream.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError()
        model = json.loads(raw)
        if _valid_cached(model, context, ident, profile, now):
            # US aliases describe the same declared source population. Keep the
            # caller's context so the UI never sees a different filter silently.
            return {**model, 'context': context}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return _unavailable(context, 'RESEARCH_NOT_PREPARED', 'PREPARE_CURRENT_RESEARCH_ESTIMATE', ['PREPARE_RESEARCH_ESTIMATE'])


def prepare(category, factor, focus, horizon, basis='END_STATE', now=None):
    """Explicitly collect/reuse real history, fit and atomically cache a model."""
    now = _now(now)
    context, ident, profile, unavailable = _configuration(category, factor, focus, horizon, basis)
    if unavailable:
        return unavailable
    try:
        with _preparation_lock(ident) as lock_stream:
            snapshot, snapshot_id = _source_snapshot(ident, now, lock_stream)
            model = _build(snapshot, snapshot_id, context, ident, profile, now)
            if model['status'] == 'RESEARCH_ESTIMATE_AVAILABLE':
                _atomic_model(_path(ident, horizon), model)
            return model
    except BlockingIOError:
        return _unavailable(context, 'SOURCE_UNAVAILABLE', 'PREPARATION_BUSY_OR_RATE_LIMITED', ['RETRY_PREPARATION_LATER'])
    except event_outcome_data.DataUnavailable as error:
        reason = str(error)
        return _unavailable(context, 'SOURCE_UNAVAILABLE', reason if re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', reason) else 'OUTCOME_SOURCE_UNAVAILABLE', ['SOURCE_DATA'])
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, OverflowError):
        return _unavailable(context, 'SOURCE_UNAVAILABLE', 'SOURCE_OR_MODEL_PREPARATION_FAILED', ['VALID_SOURCE_DATA_AND_WRITABLE_PRIVATE_STORE'])
