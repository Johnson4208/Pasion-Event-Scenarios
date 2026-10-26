"""A14 fail-closed research admission. No allocations or routing."""
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import finance_core

VERSION = 'a14-v1'

def finite(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a quantity')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Finite number required') from exc
    if not result.is_finite():
        raise ValueError('Finite number required')
    return result

def context_gates(data, checks, rules, now):
    reasons = []
    for key in ('horizon', 'utility_definition', 'utility_version', 'utility_model', 'sector', 'portfolio_context_id'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            reasons.append(key.upper() + '_REQUIRED')
    if data.get('data_quality') != 'READY' or data.get('utility_status') != 'READY':
        reasons.append('READY_RESEARCH_AND_DEFINED_UTILITY_REQUIRED')
    try:
        finite(data.get('utility'))
        origin = finance_core.instant(data.get('decision_origin'))
        if origin > now:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        reasons.append('FINITE_UTILITY_AND_VALID_DECISION_ORIGIN_REQUIRED')
    quote = (rules or {}).get('quote', {})
    try:
        ZoneInfo(quote.get('timezone', ''))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        reasons.append('QUOTE_IANA_TIMEZONE_REQUIRED')
    if not rules or data.get('venue') != rules.get('venue'):
        reasons.append('VERIFIED_VENUE_REQUIRED')
    if data.get('side') not in ('BUY', 'SELL') or data.get('side') != data.get('draft', {}).get('side', 'BUY'):
        reasons.append('EXPLICIT_SUPPORTED_SIDE_REQUIRED')
    if not checks or checks.get('liquidity_status') != 'REVIEWED_CAP':
        reasons.append('VERIFIED_LIQUIDITY_CAPACITY_REQUIRED')
    # A human checkbox is insufficient: no versioned exposure-policy evaluator
    # exists yet. Do not admit a candidate on self-reported concentration flags.
    reasons.append('VERIFIED_NAME_SECTOR_CURRENCY_EXPOSURE_POLICY_UNAVAILABLE')
    return reasons

def near_equivalent(candidates, tolerance):
    """Comparable research set only; no forced substitute or allocation."""
    tolerance = finite(tolerance)
    if tolerance < 0:
        raise ValueError('Nonnegative tolerance required')
    ready = [c for c in candidates if c.get('shadow_gate_passed') and c.get('utility_status') == 'READY']
    if not ready:
        return []
    keys = ('horizon', 'utility_definition', 'utility_version', 'utility_model', 'utility_status')
    if any(not ready[0].get(k) for k in keys) or any(any(c.get(k) != ready[0][k] for k in keys) for c in ready):
        raise ValueError('Incompatible utilities cannot be ranked')
    best = max(finite(c['utility']) for c in ready)
    return [c['id'] for c in ready if finite(c['utility']) >= best - tolerance]
