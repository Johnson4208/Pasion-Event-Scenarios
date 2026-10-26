"""A13 shared evidence semantics, used by news and conditional event research."""
from common.time import instant,derived_known_at

def latency(published_at,ingested_at,verdict_at=None):
    feed=(instant(ingested_at)-instant(published_at)).total_seconds()
    if feed<0:raise ValueError('Ingestion cannot precede publication')
    verification=(instant(verdict_at)-instant(ingested_at)).total_seconds() if verdict_at else None
    if verification is not None and verification<0:raise ValueError()
    return {'feed_latency_seconds':feed,'verification_latency_seconds':verification}

def verdict(stances):
    values=set(stances)
    if not values<= {'SUPPORTING','REFUTING'}:raise ValueError()
    return 'CONFLICTING' if len(values)==2 else 'SUPPORTED' if 'SUPPORTING' in values else 'REFUTED' if 'REFUTING' in values else 'INSUFFICIENT'

def usable_event_time(required_evidence):
    if not required_evidence: return None
    return derived_known_at(item['known_at'] for item in required_evidence)

BOUNDARIES={'scenario_weights':'ANALYTICAL_JUDGMENTS','event_probability':'UNAVAILABLE_WITHOUT_FUTURE_MATURED_INDEPENDENT_CALIBRATION',
    'stock_return_probability':'SEPARATE_A09_MODEL','feed_silence':'MISSING_COVERAGE_NOT_POSITIVE_EVIDENCE','financial_baseline':'NO_AUTOMATIC_HEADLINE_EDITS'}
