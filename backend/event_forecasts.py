"""Reviewed historical reference classes, independent of headline sentiment.

No model or historical outcomes ship with the application. A local operator can
build a catalog from adjudicated, dated cases. These are historical baseline
estimates, not a claim that future events follow the same distribution.
"""
import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import event_horizons

METHOD = 'HISTORICAL_REFERENCE_CLASS_V1'
BASES = ('END_STATE', 'OCCURRENCE')
MIN_SAMPLES = 100
MAX_SCENARIOS = 100


class InvalidModel(ValueError):
    pass


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise InvalidModel('INVALID_DEFINITION')
    return value.strip()


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidModel('INVALID_TIMESTAMP') from exc


def _source(value):
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError()
        return value
    except (TypeError, ValueError) as exc:
        raise InvalidModel('INVALID_RESOLUTION_SOURCE') from exc


def _context(value):
    result = {k: _text(value.get(k)) for k in ('category', 'factor', 'focus', 'horizon', 'basis')}
    event_horizons.info(result['horizon'])
    if result['basis'] not in BASES:
        raise InvalidModel('INVALID_PROBABILITY_BASIS')
    return result


def _key(value):
    return tuple(value[k].strip().casefold() if k == 'focus' else value[k]
                 for k in ('category', 'factor', 'focus', 'horizon', 'basis'))


def _beta_fraction(a, b, x):
    # Continued fraction for the regularized incomplete beta function.
    tiny = 1e-300
    c, d = 1., 1. - (a+b)*x/(a+1.)
    if abs(d) < tiny:
        d = tiny
    d = 1./d
    h = d
    for m in range(1, 1001):
        for aa in (m*(b-m)*x/((a+2*m-1)*(a+2*m)),
                   -(a+m)*(a+b+m)*x/((a+2*m)*(a+2*m+1))):
            d = 1.+aa*d
            c = 1.+aa/c
            if abs(d) < tiny:
                d = tiny
            if abs(c) < tiny:
                c = tiny
            d = 1./d
            delta = d*c
            h *= delta
        if abs(delta-1.) < 1e-12:
            return h
    raise InvalidModel('INTERVAL_DID_NOT_CONVERGE')


def _beta_cdf(x, a, b):
    if x <= 0:
        return 0.
    if x >= 1:
        return 1.
    bt = math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    if x < (a+1)/(a+b+2):
        return bt*_beta_fraction(a, b, x)/a
    return 1-bt*_beta_fraction(b, a, 1-x)/b


def _quantile(q, a, b):
    lo, hi = 0., 1.
    for _ in range(70):
        mid = (lo+hi)/2
        if _beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


def _estimate(counts, n, basis):
    denominator = n+len(counts)/2 if basis == 'END_STATE' else n+1
    probabilities = {key: (count+.5)/denominator for key, count in counts.items()}
    intervals = {}
    for key, count in counts.items():
        a = count+.5
        b = denominator-a
        intervals[key] = [_quantile(.025, a, b), _quantile(.975, a, b)]
    return probabilities, intervals


def _validation(train, holdout, n_train, n_holdout, basis):
    p, _ = _estimate(train, n_train, basis)
    observed = {k: holdout[k]/n_holdout for k in train}
    errors = {k: abs(p[k]-observed[k]) for k in p}
    # A documented drift check, not a guarantee of prospective calibration.
    limits = {k: min(.10, 1.96*math.sqrt(p[k]*(1-p[k])*(1/n_train+1/n_holdout))) for k in p}
    coverage = all(min(train[k], holdout[k]) >= 5 for k in p)
    if basis == 'OCCURRENCE':
        coverage = coverage and all(min(n_train-train[k], n_holdout-holdout[k]) >= 5 for k in p)
        brier = sum(observed[k]*(1-p[k])**2+(1-observed[k])*p[k]**2 for k in p)/len(p)
        loss = -sum(observed[k]*math.log(p[k])+(1-observed[k])*math.log1p(-p[k]) for k in p)/len(p)
    else:
        brier = 1+sum(v*v for v in p.values())-2*sum(observed[k]*p[k] for k in p)
        loss = -sum(observed[k]*math.log(p[k]) for k in p)
    passed = coverage and all(errors[k] <= limits[k] for k in p)
    return {'status': 'PASSED_HOLDOUT_CHECK' if passed else 'WITHHELD_HOLDOUT_CHECK_FAILED',
            'holdout_sample_count': n_holdout, 'brier_score': brier, 'log_loss': loss,
            'maximum_rate_error': max(errors.values()), 'per_outcome_rate_error': errors,
            'per_outcome_error_limit': limits, 'outcome_coverage': coverage,
            'policy': 'At least 100 training and 100 later holdout groups; at least 5 outcomes per class; rate drift within 1.96 pooled standard errors and 10 percentage points.'}


def build(spec, reviewer, now=None):
    """Fit one predeclared reference class; never fit on its later holdout."""
    now = now or datetime.now(timezone.utc)
    context = _context(spec['context'])
    definitions = spec.get('scenarios')
    if not isinstance(definitions, list) or not 2 <= len(definitions) <= MAX_SCENARIOS:
        raise InvalidModel('INVALID_SCENARIO_SET')
    scenarios = [{k: _text(row.get(k)) for k in ('id', 'title', 'resolution_rule')} for row in definitions]
    ids = [row['id'] for row in scenarios]
    if len(set(ids)) != len(ids):
        raise InvalidModel('DUPLICATE_SCENARIO')
    start = _time(spec['validation_start'])
    if start >= now:
        raise InvalidModel('INVALID_HOLDOUT_WINDOW')
    cases = spec.get('cases')
    if not isinstance(cases, list) or len(cases) > 100000:
        raise InvalidModel('INVALID_CASES')
    counts = [{k: 0 for k in ids} for _ in range(2)]
    sizes = [0, 0]
    groups, identifiers = set(), set()
    training_end, holdout_end = None, None
    embargoed = 0
    for case in cases:
        if case.get('reviewed') is not True:
            raise InvalidModel('UNREVIEWED_OUTCOME')
        ident, group = _text(case.get('id')), _text(case.get('group_id'))
        if ident in identifiers or group in groups:
            raise InvalidModel('DUPLICATE_OR_DEPENDENT_CASE_GROUP')
        identifiers.add(ident)
        groups.add(group)
        origin, maturity, resolved = [_time(case.get(k)) for k in ('origin_at', 'maturity_at', 'resolved_at')]
        expected = origin+timedelta(days=event_horizons.info(context['horizon'])['forecast_days'])
        if maturity != expected or not origin < maturity <= resolved <= now:
            raise InvalidModel('UNMATURED_OR_WRONG_HORIZON_CASE')
        _source(case.get('source_url'))
        if context['basis'] == 'END_STATE':
            if case.get('outcome_id') not in ids:
                raise InvalidModel('OUTCOME_NOT_IN_DEFINITION')
            labels = {k: int(k == case['outcome_id']) for k in ids}
        else:
            labels = case.get('outcomes')
            if not isinstance(labels, dict) or set(labels) != set(ids) or any(type(v) is not bool for v in labels.values()):
                raise InvalidModel('INCOMPLETE_OCCURRENCE_LABELS')
        if origin < start and resolved >= start:
            embargoed += 1
            continue
        partition = int(origin >= start)
        sizes[partition] += 1
        for key in ids:
            counts[partition][key] += int(labels[key])
        if partition:
            holdout_end = max(holdout_end or resolved, resolved)
        else:
            training_end = max(training_end or resolved, resolved)
    if min(sizes) < MIN_SAMPLES:
        raise InvalidModel('INSUFFICIENT_INDEPENDENT_HISTORY')
    validation = _validation(*counts, *sizes, context['basis'])
    expiry = _time(spec['expires_at'])
    if not now < expiry <= now+timedelta(days=90):
        raise InvalidModel('INVALID_MODEL_EXPIRY')
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema_version': 1, 'method': METHOD, 'model_version': _text(spec['model_version']),
            'family_id': _text(spec['family_id']), 'definition_version': _text(spec['definition_version']),
            'question': _text(spec['question']), 'sampling_policy': _text(spec['sampling_policy']),
            'context': context, 'scenarios': scenarios, 'training_counts': counts[0], 'holdout_counts': counts[1],
            'training_sample_count': sizes[0], 'holdout_sample_count': sizes[1], 'validation': validation,
            'training_resolved_through': training_end.isoformat(), 'holdout_origin_from': start.isoformat(),
            'holdout_resolved_through': holdout_end.isoformat(), 'embargoed_cases': embargoed,
            'reviewer': _text(reviewer), 'reviewed_at': now.isoformat(), 'expires_at': expiry.isoformat(),
            'dataset_sha256': digest, 'smoothing': 'Jeffreys symmetric half-count per outcome; never a 50% per-scenario starting probability.'}


def unavailable(context, reason='NO_REVIEWED_HISTORICAL_MODEL'):
    return {'schema_version': 1, 'status': 'UNAVAILABLE', 'reason_code': reason, 'context': context,
            'scenarios': [], 'probabilities': None, 'intervals': None,
            'notice': 'No probabilities are inferred from headline counts, evidence scores, or missing sources.'}


def estimate(artifact, context, now=None):
    """Validate the whole family atomically, then return every outcome together."""
    now = now or datetime.now(timezone.utc)
    if artifact.get('schema_version') != 1 or artifact.get('method') != METHOD or _key(_context(artifact['context'])) != _key(context):
        raise InvalidModel('MODEL_CONTEXT_MISMATCH')
    for k in ('family_id', 'definition_version', 'question', 'model_version', 'reviewer', 'sampling_policy', 'dataset_sha256'):
        _text(artifact.get(k))
    if not _time(artifact['holdout_resolved_through']) <= _time(artifact['reviewed_at']) <= now < _time(artifact['expires_at']):
        raise InvalidModel('MODEL_EXPIRED_OR_FUTURE_DATED')
    if _time(artifact['expires_at']) > _time(artifact['reviewed_at'])+timedelta(days=90):
        raise InvalidModel('MODEL_EXPIRY_TOO_LONG')
    if not _time(artifact['training_resolved_through']) < _time(artifact['holdout_origin_from']) < _time(artifact['holdout_resolved_through']):
        raise InvalidModel('HOLDOUT_LEAKAGE')
    scenarios = artifact.get('scenarios')
    if not isinstance(scenarios, list) or not 2 <= len(scenarios) <= MAX_SCENARIOS:
        raise InvalidModel('INVALID_SCENARIO_SET')
    ids = [_text(row.get('id')) for row in scenarios]
    if len(set(ids)) != len(ids):
        raise InvalidModel('DUPLICATE_SCENARIO')
    for row in scenarios:
        _text(row.get('title'))
        _text(row.get('resolution_rule'))
    train, holdout = artifact.get('training_counts'), artifact.get('holdout_counts')
    n_train, n_holdout = artifact.get('training_sample_count'), artifact.get('holdout_sample_count')
    if any(type(n) is not int or not MIN_SAMPLES <= n <= 100000 for n in (n_train, n_holdout)):
        raise InvalidModel('INSUFFICIENT_INDEPENDENT_HISTORY')
    for counts, n in ((train, n_train), (holdout, n_holdout)):
        if not isinstance(counts, dict) or set(counts) != set(ids) or any(type(v) is not int or not 0 <= v <= n for v in counts.values()):
            raise InvalidModel('INCOMPLETE_OR_INVALID_OUTCOME_COUNTS')
        if context['basis'] == 'END_STATE' and sum(counts.values()) != n:
            raise InvalidModel('OUTCOMES_NOT_EXHAUSTIVE')
    validation = _validation(train, holdout, n_train, n_holdout, context['basis'])
    if validation['status'] != 'PASSED_HOLDOUT_CHECK':
        raise InvalidModel('HOLDOUT_CHECK_FAILED')
    probabilities, intervals = _estimate(train, n_train, context['basis'])
    public = {k: artifact[k] for k in ('family_id', 'definition_version', 'question', 'model_version', 'sampling_policy',
              'dataset_sha256', 'training_sample_count', 'holdout_sample_count', 'training_resolved_through',
              'holdout_origin_from', 'holdout_resolved_through', 'reviewed_at', 'expires_at', 'smoothing')}
    return {**public, 'schema_version': 1, 'method': METHOD, 'status': 'REFERENCE_ESTIMATE_AVAILABLE',
            'as_of': now.isoformat(),
            'context': context, 'scenarios': scenarios, 'probabilities': probabilities, 'intervals': intervals,
            'interval_level': .95, 'validation': validation, 'training_counts': train, 'holdout_counts': holdout,
            'mutually_exclusive': context['basis'] == 'END_STATE', 'exhaustive': context['basis'] == 'END_STATE',
            'news_adjusted': False, 'notice': 'Historical reference-class baseline with 95% credible intervals for its rates. Validity depends on the sampling and stationarity assumptions; this is not a guarantee about future events.'}


def forecast(category, factor, focus, horizon, basis='END_STATE', now=None):
    context = _context(dict(category=category, factor=factor, focus=focus or 'World', horizon=horizon, basis=basis))
    path = os.environ.get('PASION_EVENT_MODELS_PATH')
    if not path:
        return unavailable(context)
    try:
        # This is an operator-configured local file, never a browser URL/path.
        with Path(path).open('rb') as file:
            raw = file.read(5_000_001)
        if len(raw) > 5_000_000:
            raise InvalidModel('MODEL_CATALOG_TOO_LARGE')
        catalog = json.loads(raw)
        if catalog.get('schema_version') != 1 or not isinstance(catalog.get('models'), list) or len(catalog['models']) > 1000:
            raise InvalidModel('INVALID_MODEL_CATALOG')
        matches = [a for a in catalog['models'] if _key(_context(a['context'])) == _key(context)]
        if not matches:
            return unavailable(context, 'NO_MODEL_FOR_THIS_CONTEXT')
        if len(matches) != 1:
            raise InvalidModel('AMBIGUOUS_MODEL_FAMILY')
        return estimate(matches[0], context, now)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return unavailable(context, str(exc) if isinstance(exc, InvalidModel) else 'INVALID_MODEL_CATALOG')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='JSON with schema_version:1 and a models array of definitions and reviewed cases')
    parser.add_argument('--output', required=True, help='Private local catalog path; do not commit historical data or this file')
    parser.add_argument('--reviewer', required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('models'), list) or not 1 <= len(data['models']) <= 1000:
        parser.error('Input needs schema_version:1 and at least one model specification.')
    if Path(args.input).resolve() == Path(args.output).resolve():
        parser.error('Keep the input dataset: use a different path for the output catalog.')
    try:
        models = [build(spec, args.reviewer) for spec in data['models']]
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    if len({_key(a['context']) for a in models}) != len(models):
        parser.error('Duplicate contexts: define one complete outcome family per context and basis.')
    if any(m['validation']['status'] != 'PASSED_HOLDOUT_CHECK' for m in models):
        parser.error('Holdout check failed; no catalog was written. Inspect outcomes, sampling policy and drift.')
    Path(args.output).write_text(json.dumps({'schema_version': 1, 'models': models}, indent=2), encoding='utf-8')
    print(f'Built {len(models)} historical reference-class models. No live headline probability adjustment is enabled.')


if __name__ == '__main__':
    main()
