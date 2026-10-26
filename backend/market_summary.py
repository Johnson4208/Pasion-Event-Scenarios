"""F02: explicit demo fixtures and fail-closed trusted-provider cache adapter."""
import json
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DEMO = json.loads(Path(__file__).with_name('market_demo.json').read_text(encoding='utf-8'))


def clock(value):
    if not isinstance(value, str):
        raise ValueError('Invalid clock')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Offset required')
    return parsed.astimezone(timezone.utc)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def summary(mode='demo', now=None, snapshot=None):
    now = now or datetime.now(timezone.utc)
    base = {'version': 1, 'mode': mode, 'evaluated_at': now.isoformat(),
            'benchmark': {'status': 'UNAVAILABLE', 'reason': 'NO_VERIFIED_BENCHMARK'},
            'breadth': {'status': 'UNAVAILABLE', 'reason': 'NO_VERIFIED_UNIVERSE'}, 'quotes': []}
    if mode == 'demo':
        base.update(status='READY', provider_status='NOT_CONNECTED', reason='ILLUSTRATIVE_FIXTURE')
        base['quotes'] = [dict(item, status='READY', origin='SAMPLE', source='Pasion demo fixture',
                               as_of=None, reason='ILLUSTRATIVE_FIXTURE') for item in DEMO]
        return base
    if mode != 'provider':
        raise ValueError('Invalid mode')
    try:
        if snapshot is None:
            cache = os.environ.get('PASION_MARKET_SNAPSHOT')
            if not cache:
                raise ValueError('Provider not configured')
            snapshot = json.loads(Path(cache).read_text(encoding='utf-8'))
        if not isinstance(snapshot, dict) or snapshot.get('verified') is not True or not isinstance(snapshot.get('source'), str) or not snapshot['source'].strip():
            raise ValueError('Unverified source')
        source = snapshot['source'][:120]
        records = snapshot['quotes']
        if not isinstance(records, dict):
            raise ValueError('Invalid cache')
        base.update(status='READY', provider_status='CONNECTED', reason=None)
    except (OSError, ValueError, TypeError, KeyError):
        base.update(status='UNAVAILABLE', provider_status='UNAVAILABLE', reason='PROVIDER_NOT_READY')
        return base
    for item in DEMO:
        result = {k: v for k, v in item.items() if k not in ('price', 'change')}
        result.update(price=None, change=None, origin='ACTUAL', source=source, as_of=None,
                      status='UNAVAILABLE', reason='NO_PROVIDER_COVERAGE')
        record = records.get(item['ticker'])
        if record is not None:
            try:
                # The provider adapter supplies authoritative exchange-calendar sessions.
                as_of = clock(record['as_of'])
                opened, closed = clock(record['session_open']), clock(record['session_close'])
                ZoneInfo(record['timezone'])
                if not all(isinstance(record[k], str) and record[k].strip() for k in ('venue', 'calendar', 'currency', 'unit')):
                    raise ValueError('Missing instrument master')
                if record['unit'] != item['unit'] or not opened <= as_of <= closed or closed <= opened:
                    raise ValueError('Invalid session or unit')
                age = record['max_age_seconds']
                if not number(age) or not 0 < age <= 86400:
                    raise ValueError('Invalid freshness policy')
                if not number(record['price']) or record['price'] <= 0 or not number(record['change']):
                    raise ValueError('Invalid quote')
                result.update(as_of=as_of.isoformat(), venue=record['venue'], currency=record['currency'])
                if as_of > now or opened > now:
                    result.update(status='WITHHELD', reason='FUTURE_SESSION_OR_QUOTE')
                elif (now - as_of).total_seconds() > age:
                    result.update(status='STALE', reason='QUOTE_EXPIRED')
                else:
                    result.update(status='READY', reason=None, price=record['price'], change=record['change'],
                                  expires_at=(as_of + timedelta(seconds=age)).isoformat())
            except (ValueError, TypeError, KeyError, OverflowError):
                result.update(status='WITHHELD', reason='INVALID_QUOTE_OR_SESSION')
        base['quotes'].append(result)
    ready = [q for q in base['quotes'] if q['status'] == 'READY']
    base['coverage'] = {'available': len(ready), 'total': len(DEMO), 'scope': 'SUPPORTED_INSTRUMENTS_ONLY'}
    benchmark = next((q for q in ready if q['ticker'] == 'SPX'), None)
    if benchmark:
        base['benchmark'] = {k: benchmark[k] for k in ('ticker', 'price', 'change', 'status', 'source', 'as_of')}
    # Index/commodity moves cannot be counted as total equity-market breadth.
    if not ready:
        base.update(status='UNAVAILABLE', reason='NO_READY_QUOTES')
    return base
