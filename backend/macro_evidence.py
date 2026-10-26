"""F09 immutable reviewed vintages and issuer-specific commodity stress."""
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import finance_core

SCOPES = {'world', 'europe', 'americas', 'asia', 'vietnam', 'unitedStates', 'japan'}
KINDS = {'cpi', 'policy_rate', 'labor', 'fx', 'growth'}


def number(value):
    if isinstance(value, bool) or value is None: raise ValueError()
    result = Decimal(str(value))
    if not result.is_finite() or abs(result) > Decimal('1e18'): raise ValueError()
    return result


def label(value):
    if not isinstance(value, str) or not 0 < len(value) <= 200 or any(ord(c) < 32 for c in value): raise ValueError()
    return value


def source(value):
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password: raise ValueError()
    return label(value)


@contextmanager
def database(root):
    db = sqlite3.connect(root / 'macro.sqlite3')
    try:
        with db:
            db.executescript('''CREATE TABLE IF NOT EXISTS series(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vintages(id TEXT PRIMARY KEY,series_id TEXT NOT NULL REFERENCES series(id),payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS exposures(id TEXT PRIMARY KEY,payload TEXT NOT NULL);''')
            yield db
    finally: db.close()


def ingest(root, data, now=None):
    now = now or datetime.now(timezone.utc)
    definition = {k: data[k] for k in ('id','name','scope','kind','unit','frequency','timezone','calendar','provider','source_url')}
    for key in definition: label(definition[key])
    if not re.fullmatch('[A-Za-z0-9_.-]{1,80}',definition['id']) or definition['scope'] not in SCOPES or definition['kind'] not in KINDS: raise ValueError()
    if definition['frequency'] not in ('daily','monthly','quarterly','annual','event'): raise ValueError()
    ZoneInfo(definition['timezone']); source(definition['source_url'])
    if data.get('reviewed') is not True: raise ValueError()
    # Optional thresholds are a reviewed rule in this series' own units, never global weights.
    rule = data.get('rule')
    if rule is not None:
        low, high = number(rule['low']), number(rule['high'])
        if low >= high: raise ValueError()
        definition['rule'] = {'low':str(low),'high':str(high),'meaning':label(rule['meaning'])}
    items = data['observations']
    if not isinstance(items,list) or not 1 <= len(items) <= 1000: raise ValueError()
    rows = []
    for item in items:
        start,end = date.fromisoformat(item['period_start']),date.fromisoformat(item['period_end'])
        release,known,expiry = [finance_core.instant(item[k]) for k in ('release_at','known_at','expires_at')]
        if start > end or end > release.date() or release > now or known > now or expiry <= release: raise ValueError()
        rows.append({'id':secrets.token_hex(16),'period_start':start.isoformat(),'period_end':end.isoformat(),
            'value':None if item['value'] is None else str(number(item['value'])),
            'release_at':release.isoformat(),'known_at':max(release,known,now).isoformat(),
            'accepted_at':now.isoformat(),'expires_at':expiry.isoformat(),'revision':label(item['revision'])})
    # Ambiguous simultaneous revisions are never admitted in one batch.
    if len({(r['period_end'],r['release_at']) for r in rows}) != len(rows): raise ValueError()
    with database(root) as db:
        old = db.execute('SELECT payload FROM series WHERE id=?',(definition['id'],)).fetchone()
        if old and json.loads(old[0]) != definition: raise ValueError()
        db.execute('INSERT OR IGNORE INTO series VALUES (?,?)',(definition['id'],json.dumps(definition)))
        for row in rows:
            prior=[json.loads(r[0]) for r in db.execute('SELECT payload FROM vintages WHERE series_id=?',(definition['id'],))]
            prior=[r for r in prior if r['period_end']==row['period_end']]
            row['previous_vintage_id']=max(prior,key=lambda r:(r['known_at'],r['release_at']))['id'] if prior else None
            db.execute('INSERT INTO vintages VALUES (?,?,?)',(row['id'],definition['id'],json.dumps(row)))
    return {'version':1,'status':'REVIEWED','count':len(rows)}


def summary(root, scope, origin=None, now=None):
    now = now or datetime.now(timezone.utc)
    origin = finance_core.instant(origin) if origin else now
    if scope not in SCOPES or origin > now: raise ValueError()
    output = []
    with database(root) as db:
        definitions = [json.loads(r[0]) for r in db.execute('SELECT payload FROM series ORDER BY id')]
        for definition in definitions:
            if definition['scope'] != scope: continue
            eligible = [json.loads(r[0]) for r in db.execute('SELECT payload FROM vintages WHERE series_id=?',(definition['id'],))]
            eligible = [r for r in eligible if finance_core.instant(r['known_at']) <= origin and finance_core.instant(r['release_at']) <= origin]
            history = []
            for end in sorted({r['period_end'] for r in eligible}):
                period = [r for r in eligible if r['period_end']==end]
                newest = max((r['release_at'],r['known_at']) for r in period)
                choices = [r for r in period if (r['release_at'],r['known_at'])==newest]
                if len(choices)>1:
                    history.append({'period_end':end,'value':None,'status':'UNAVAILABLE','reason':'AMBIGUOUS_REVISION'})
                else: history.append({**choices[0],'status':'READY' if choices[0]['value'] is not None else 'UNAVAILABLE','reason':None if choices[0]['value'] is not None else 'MISSING_OBSERVATION'})
            latest = history[-1] if history else None
            status = latest['status'] if latest else 'UNAVAILABLE'
            reason = latest['reason'] if latest else 'NO_OBSERVATION_KNOWN_AT_ORIGIN'
            if latest and latest.get('expires_at') and finance_core.instant(latest['expires_at']) <= origin:
                status,reason = 'STALE','RELEASE_COVERAGE_EXPIRED'
            fit = None
            if status=='READY' and definition.get('rule'):
                rule = definition['rule'];value=number(latest['value'])
                fit = 'BELOW_RANGE' if value<number(rule['low']) else 'ABOVE_RANGE' if value>number(rule['high']) else 'WITHIN_RANGE'
            output.append({**definition,'status':status,'reason':reason,'latest':latest,'history':history[-240:],
                'heuristic_fit':fit,'fit_label':'Reviewed threshold heuristic; not a probability' if fit else 'No eligible rule'})
    covered = sorted({r['kind'] for r in output if r['status']=='READY'})
    # All five factors and one unambiguous configured rule per factor are required.
    rule_inputs=[r for r in output if r['status']=='READY' and r['heuristic_fit']]
    complete_rules=all(sum(r['kind']==kind for r in rule_inputs)==1 for kind in KINDS)
    regime={'status':'HEURISTIC' if complete_rules else 'UNAVAILABLE',
        'fit':('WITHIN_ALL_REVIEWED_RANGES' if all(r['heuristic_fit']=='WITHIN_RANGE' for r in rule_inputs) else 'OUTSIDE_REVIEWED_RANGES') if complete_rules else None,
        'reason':None if complete_rules else 'FIVE_UNAMBIGUOUS_REVIEWED_FACTOR_RULES_REQUIRED',
        'source_ids':[r['id'] for r in rule_inputs] if complete_rules else [],'label':'Threshold context heuristic; not a market forecast or probability'}
    return {'version':1,'scope':scope,'origin':origin.isoformat(),'series':output,'coverage':{'covered':covered,'missing':sorted(KINDS-set(covered))},
        'status':'READY' if len(covered)==len(KINDS) else 'PARTIAL' if covered else 'UNAVAILABLE',
        'regime':regime}


def exposure(root, data, now=None):
    now = now or datetime.now(timezone.utc)
    if data.get('reviewed') is not True or not re.fullmatch('[A-Z0-9.-]{1,16}',data['ticker']): raise ValueError()
    # A mapping must cite an accepted issuer fact. Admin review asserts the segment economics.
    fact_ids = data['fact_ids']
    if not isinstance(fact_ids,list) or not 1<=len(fact_ids)<=30: raise ValueError()
    with finance_core.database(root) as db:
        for fact_id in fact_ids:
            row = db.execute('SELECT ticker,payload FROM facts WHERE id=?',(fact_id,)).fetchone()
            if not row or row['ticker'] != data['ticker']: raise ValueError()
            fact=json.loads(row['payload'])
            if fact.get('status')!='READY' or fact.get('value') is None or finance_core.instant(fact['known_at'])>now: raise ValueError()
    result = {k:label(data[k]) for k in ('ticker','segment','commodity','grade','location','volume_unit','currency','contract_reset','inventory_lag','hedge_scope')}
    if not re.fullmatch('[A-Z]{3}',result['currency']): raise ValueError()
    start,end = date.fromisoformat(data['period_start']),date.fromisoformat(data['period_end'])
    if start>end: raise ValueError()
    result.update(period_start=start.isoformat(),period_end=end.isoformat())
    # Effective repricing volumes exclude fixed contracts, hedges and volumes outside this scenario period.
    for key in ('output_volume','input_volume','output_repricing_fraction','input_repricing_fraction'):
        value = number(data[key])
        if value<0 or ('fraction' in key and value>1): raise ValueError()
        result[key]=str(value)
    result.update(id=secrets.token_hex(16),known_at=now.isoformat(),expires_at=finance_core.instant(data['expires_at']).isoformat(),fact_ids=fact_ids)
    if finance_core.instant(result['expires_at'])<=now: raise ValueError()
    with database(root) as db: db.execute('INSERT INTO exposures VALUES (?,?)',(result['id'],json.dumps(result)))
    return {'version':1,'exposure':result}


def exposures(root,ticker):
    if not re.fullmatch('[A-Z0-9.-]{1,16}',ticker): raise ValueError()
    with database(root) as db: items=[json.loads(r[0]) for r in db.execute('SELECT payload FROM exposures')]
    return {'version':1,'exposures':[r for r in items if r['ticker']==ticker]}


def stress(root,data,now=None):
    now = now or datetime.now(timezone.utc)
    origin = finance_core.instant(data['origin']) if data.get('origin') else now
    if origin>now: raise ValueError()
    with database(root) as db: row=db.execute('SELECT payload FROM exposures WHERE id=?',(data['exposure_id'],)).fetchone()
    if not row: return {'version':1,'status':'UNAVAILABLE','delta_ebit':None,'reason':'REVIEWED_EXPOSURE_REQUIRED'}
    mapping=json.loads(row[0])
    if not finance_core.instant(mapping['known_at'])<=origin<finance_core.instant(mapping['expires_at']):
        return {'version':1,'status':'UNAVAILABLE','delta_ebit':None,'reason':'EXPOSURE_NOT_AVAILABLE_AT_ORIGIN'}
    values={k:number(data[k]) for k in ('output_price_delta','input_price_delta','pass_through','hedge_pnl','incremental_costs')}
    if values['incremental_costs']<0: raise ValueError()
    if data['volume_unit']!=mapping['volume_unit']: raise ValueError()
    conversion=number('1');fx_evidence=None
    if data['currency']!=mapping['currency']:
        with database(root) as db:row=db.execute('SELECT payload FROM series WHERE id=?',(data.get('fx_series_id'),)).fetchone()
        if not row:raise ValueError('Reviewed point-in-time FX series required')
        definition=json.loads(row[0])
        fx=next((s for s in summary(root,definition['scope'],origin.isoformat(),now)['series'] if s['id']==definition['id']),None)
        if not fx or fx['kind']!='fx' or fx['unit']!=mapping['currency']+'/'+data['currency'] or fx['status']!='READY':raise ValueError('FX direction/unit/freshness mismatch')
        conversion=number(fx['latest']['value'])
        if conversion<=0:raise ValueError()
        fx_evidence={'series_id':fx['id'],'vintage_id':fx['latest']['id'],'rate':str(conversion),'unit':fx['unit'],'known_at':fx['latest']['known_at'],'source_url':fx['source_url']}
    output=number(mapping['output_volume'])*number(mapping['output_repricing_fraction'])*values['output_price_delta']*conversion
    inputs=number(mapping['input_volume'])*number(mapping['input_repricing_fraction'])*values['input_price_delta']*conversion
    delta=output-inputs+values['pass_through']+values['hedge_pnl']-values['incremental_costs']
    return {'version':1,'status':'SCENARIO','delta_ebit':str(delta),'currency':mapping['currency'],'origin':origin.isoformat(),
        'exposure':mapping,'assumptions':{k:str(v) for k,v in values.items()},'shock_currency':data['currency'],'fx_evidence':fx_evidence,
        'source_ids':mapping['fact_ids']+([fx_evidence['vintage_id']] if fx_evidence else []),
        'commodity_role':'MIXED_OUTPUT_INPUT' if number(mapping['output_volume'])>0 and number(mapping['input_volume'])>0 else 'OUTPUT_PRODUCER' if number(mapping['output_volume'])>0 else 'INPUT_CONSUMER',
        'component_semantics':{'physical_exposure':'ADMIN_REVIEWED_SOURCE_MAPPING','price_shocks':'USER_SCENARIO_ASSUMPTIONS','pass_through_hedge_costs':'USER_ASSUMPTIONS_IN_EXPOSURE_CURRENCY','fx':'SOURCE_DERIVED' if fx_evidence else 'SAME_CURRENCY_IDENTITY'},
        'driver_proposal':{'definition':'ebit','delta':str(delta),'currency':mapping['currency'],'period_start':mapping['period_start'],'period_end':mapping['period_end'],'status':'UNVERIFIED_SCENARIO_NOT_BASELINE_UPDATE'},
        'predictive_model':{'status':'UNAVAILABLE','reason':'NO_OUT_OF_SAMPLE_VALIDATED_ISSUER_LAG_MODEL'},
        'hedging':{'status':'RESEARCH_ONLY','quantity':None,'reason':'CONTRACT_MARGIN_BASIS_COST_AND_VALIDATION_GATES_REQUIRED'},
        'bridge':{'output_effect':str(output),'input_effect':str(-inputs),'pass_through':str(values['pass_through']),
            'hedge_pnl':str(values['hedge_pnl']),'incremental_costs':str(-values['incremental_costs'])},
        'calculation_version':'f09-v1','forecast_status':'PROPOSED_SCENARIO_REQUIRES_F04_DRIVER_REVIEW'}
