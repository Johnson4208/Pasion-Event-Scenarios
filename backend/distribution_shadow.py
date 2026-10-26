"""F15 isolated admin shadow gate and atomic capacity simulation; no routing."""
import json
import secrets
from datetime import datetime,timezone
import finance_core
import feasibility
from macro_evidence import label
from distribution import engine
from distribution import capacity

def initialize(db):
    capacity.initialize(db)
    schema='''CREATE TABLE IF NOT EXISTS distribution_pools(id TEXT PRIMARY KEY,capacity INTEGER NOT NULL,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS distribution_candidates(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS distribution_transitions(id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,candidate_id TEXT NOT NULL REFERENCES distribution_candidates(id),pool_id TEXT NOT NULL REFERENCES distribution_pools(id),action TEXT NOT NULL,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS distribution_reservations(candidate_id TEXT PRIMARY KEY REFERENCES distribution_candidates(id),pool_id TEXT NOT NULL REFERENCES distribution_pools(id),slots INTEGER NOT NULL,active INTEGER NOT NULL);'''
    for statement in schema.split(';'):
        if statement.strip():db.execute(statement)

def pool(db,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    capacity=data['capacity_slots']
    if isinstance(capacity,bool) or not isinstance(capacity,int) or not 1<=capacity<=10000 or data.get('reviewed') is not True:raise ValueError()
    record={'id':secrets.token_hex(16),'capacity_slots':capacity,'horizon':label(data['horizon']),
        'utility_definition':label(data['utility_definition']),'utility_version':label(data['utility_version']),
        'policy':label(data['policy']),'known_at':now.isoformat(),'expires_at':finance_core.instant(data['expires_at']).isoformat(),
        'status':'SHADOW_SIMULATION_ONLY','capacity_unit':'SIMULATED_REVIEW_SLOTS_NOT_SHARES_OR_CASH'}
    if finance_core.instant(record['expires_at'])<=now:raise ValueError()
    db.execute('INSERT INTO distribution_pools VALUES (?,?,?)',(record['id'],capacity,json.dumps(record)))
    return {'version':1,'pool':record}

def candidate(db,root,data,now=None):
    initialize(db);feasibility.initialize(db);now=now or datetime.now(timezone.utc)
    owner=data['owner'].casefold();ticker=data['draft']['ticker'];reasons=[]
    account=db.execute('SELECT disabled FROM accounts WHERE email=?',(owner,)).fetchone()
    if not account or account[0]:reasons.append('ACTIVE_IDENTITY_REQUIRED')
    row=db.execute('SELECT payload FROM distribution_pools WHERE id=?',(data['pool_id'],)).fetchone()
    p=json.loads(row[0]) if row else None
    if not p or finance_core.instant(p['expires_at'])<=now:reasons.append('VALID_SHADOW_CAPACITY_POLICY_REQUIRED')
    checks=feasibility.for_owner(db,owner,data['draft']) if account and not account[0] else None
    if not checks or checks['status']!='READY':reasons.extend(checks.get('reason_codes',[]) if checks else ['FEASIBILITY_UNAVAILABLE'])
    fact=finance_core.evidence(root,data['fact_id'])
    if not fact or fact['ticker']!=ticker or fact['status']!='READY':reasons.append('ACCEPTED_ISSUER_RESEARCH_REQUIRED')
    # Explicit human policies are admission assertions, not inferred model confidence.
    for key,reason in [('suitability_reviewed','SUITABILITY_REVIEW_REQUIRED'),('name_sector_reviewed','NAME_SECTOR_EXPOSURE_REVIEW_REQUIRED'),('tape_window_reviewed','VERIFIED_TAPE_WINDOW_REQUIRED')]:
        if data.get(key) is not True:reasons.append(reason)
    if p and (data.get('horizon')!=p['horizon'] or data.get('utility_definition')!=p['utility_definition'] or data.get('utility_version')!=p['utility_version']):reasons.append('SAME_HORIZON_COMPARABLE_UTILITY_REQUIRED')
    instrument=db.execute('SELECT payload FROM trading_instruments WHERE ticker=?',(ticker,)).fetchone()
    reasons.extend(engine.context_gates(data,checks,json.loads(instrument[0]) if instrument else None,now))
    reasons.append('OUT_OF_TIME_VALIDATION_AND_OPERATIONAL_RELEASE_REQUIRED')
    gate_reasons=reasons[:-1]
    record={'id':secrets.token_hex(16),'pool_id':data['pool_id'],'owner':owner,'ticker':ticker,'fact_id':data['fact_id'],
        'created_at':now.isoformat(),'status':'WITHHELD' if gate_reasons else 'REVIEW_ONLY','reason_codes':reasons,
        'shadow_gate_passed':not gate_reasons,'draft':data['draft'],'feasibility_status':checks['status'] if checks else 'UNAVAILABLE',
        'account_version':checks.get('account_version') if checks else None,'instrument_version':checks.get('instrument_version') if checks else None,
        'expires_at':checks.get('expires_at') if checks else None,'allocation_quantity':None,'utility_rank':None,
        'review_note':label(data['review_note']),'execution_policy':'NO_RECOMMENDATION_ROUTING_OR_BROKER_EXECUTION'}
    record.update(policy_version=engine.VERSION,allocation_weight=None,calibrated=False,
        evidence_ids=[data['fact_id']],candidate_context={key:data.get(key) for key in
        ('venue','side','data_quality','decision_origin','horizon','utility_definition','utility_version','utility_model','utility_status','utility','sector','portfolio_context_id')})
    db.execute('INSERT INTO distribution_candidates VALUES (?,?)',(record['id'],json.dumps(record)))
    return {'version':1,'candidate':record}

def transition(db,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    key=label(data['idempotency_key']);action=data['action']
    if action not in ('RESERVE_SHADOW_SLOT','RELEASE_SHADOW_SLOT'):raise ValueError()
    existing=db.execute('SELECT candidate_id,pool_id,action,payload FROM distribution_transitions WHERE idempotency_key=?',(key,)).fetchone()
    if existing:
        if tuple(existing[:3])!=(data['candidate_id'],data['pool_id'],action):raise ValueError()
        return {'version':1,'transition':json.loads(existing[3]),'replayed':True}
    row=db.execute('SELECT payload FROM distribution_candidates WHERE id=?',(data['candidate_id'],)).fetchone()
    p=db.execute('SELECT capacity,payload FROM distribution_pools WHERE id=?',(data['pool_id'],)).fetchone()
    if not row or not p:raise ValueError()
    c=json.loads(row[0]);policy=json.loads(p[1])
    if c['pool_id']!=policy['id']:raise ValueError()
    reservation=db.execute('SELECT active FROM distribution_reservations WHERE candidate_id=?',(c['id'],)).fetchone()
    if action=='RESERVE_SHADOW_SLOT':
        if c.get('policy_version')!=engine.VERSION:raise ValueError('Candidate policy revalidation required')
        if not c['shadow_gate_passed'] or not c['expires_at'] or finance_core.instant(c['expires_at'])<=now or finance_core.instant(policy['expires_at'])<=now:raise ValueError()
        checks=feasibility.for_owner(db,c['owner'],c['draft'])
        if checks['status']!='READY' or checks.get('account_version')!=c['account_version'] or checks.get('instrument_version')!=c['instrument_version']:raise ValueError()
        if reservation:raise ValueError()  # one-shot candidate lifecycle, even after release
        used=db.execute('SELECT COALESCE(SUM(slots),0) FROM distribution_reservations WHERE pool_id=? AND active=1',(policy['id'],)).fetchone()[0]
        if used>=p[0]:raise ValueError()
        db.execute('INSERT INTO distribution_reservations VALUES (?,?,1,1)',(c['id'],policy['id']))
    else:
        if not reservation or not reservation[0]:raise ValueError()
        db.execute('UPDATE distribution_reservations SET active=0 WHERE candidate_id=?',(c['id'],))
    result={'id':secrets.token_hex(16),'candidate_id':c['id'],'pool_id':policy['id'],'action':action,'known_at':now.isoformat(),
        'capacity_unit':'SIMULATED_REVIEW_SLOT','allocation_quantity':None,'execution_policy':'SHADOW_ONLY'}
    db.execute('INSERT INTO distribution_transitions VALUES (?,?,?,?,?,?)',(result['id'],key,c['id'],policy['id'],action,json.dumps(result)))
    return {'version':1,'transition':result,'replayed':False}

def state(db):
    initialize(db);pools=[]
    for row in db.execute('SELECT payload FROM distribution_pools'):
        p=json.loads(row[0]);p['reserved_slots']=db.execute('SELECT COALESCE(SUM(slots),0) FROM distribution_reservations WHERE pool_id=? AND active=1',(p['id'],)).fetchone()[0];p['available_slots']=p['capacity_slots']-p['reserved_slots'];pools.append(p)
    return {'version':1,'capacity_ledger':capacity.audit(db),'pools':pools,'candidates':[json.loads(r[0]) for r in db.execute('SELECT payload FROM distribution_candidates ORDER BY rowid DESC LIMIT 100')],
        'events':[json.loads(r[0]) for r in db.execute('SELECT payload FROM distribution_transitions ORDER BY rowid DESC LIMIT 100')],'status':'SHADOW_ONLY_NO_ALLOCATION'}
