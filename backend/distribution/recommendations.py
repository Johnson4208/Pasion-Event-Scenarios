"""Transactional recommendation-exposure limiter, initially used only by the lab.

Exposure means a recommendation issued, not a trade or market liquidity.
Callers must supply server-validated suitable candidates with comparable utility.
"""
import hashlib
import json
import math
import sqlite3

VERSION = 'exposure-v1'

def decide(path, request_id, customer, candidates, policy, now):
    def finite(x):
        return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
    if not finite(now) or now<0 or not isinstance(customer,str) or not customer.strip() or not isinstance(request_id,str) or not request_id.strip():
        raise ValueError('Valid request, customer and clock required')
    for key in ('window_seconds','max_per_symbol','max_per_sector','customer_cooldown_seconds'):
        if type(policy.get(key)) is not int or policy[key]<=0:raise ValueError('Positive integer '+key+' required')
    if not isinstance(policy.get('version'),str) or not policy['version'] or not finite(policy.get('utility_tolerance')) or policy['utility_tolerance']<0:
        raise ValueError('Versioned policy and nonnegative utility tolerance required')
    if not isinstance(candidates,list) or len(candidates)>1000:raise ValueError('Candidate list required')
    seen=set()
    for c in candidates:
        if not isinstance(c,dict) or not all(isinstance(c.get(k),str) and c[k].strip() for k in ('symbol','sector','horizon','utility_definition','utility_version')) or not finite(c.get('utility')):
            raise ValueError('Typed finite candidate required')
        if c['symbol'] in seen:raise ValueError('Duplicate symbol')
        seen.add(c['symbol'])
    payload=json.dumps(dict(customer=customer,candidates=candidates,policy=policy),sort_keys=True,allow_nan=False)
    digest=hashlib.sha256(payload.encode()).hexdigest()
    with sqlite3.connect(path,timeout=30) as db:
        db.execute('CREATE TABLE IF NOT EXISTS recommendation_requests(id TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS recommendation_exposures(request_id TEXT PRIMARY KEY,customer TEXT,symbol TEXT,sector TEXT,issued_at REAL)')
        db.execute('CREATE INDEX IF NOT EXISTS exposures_time ON recommendation_exposures(issued_at)')
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT digest,result FROM recommendation_requests WHERE id=?',(request_id,)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError('Idempotency payload conflict')
            return dict(json.loads(old[1]),replayed=True)
        if db.execute('SELECT 1 FROM recommendation_exposures WHERE issued_at>? LIMIT 1',(now,)).fetchone():raise ValueError('Clock moved backwards')
        eligible=[c for c in candidates if c.get('suitable') is True and c.get('data_status')=='READY']
        context={(c['horizon'],c['utility_definition'],c['utility_version']) for c in eligible}
        if len(context)>1:raise ValueError('Incomparable candidate utilities')
        best=max((c['utility'] for c in eligible),default=None)
        comparable=[c for c in eligible if c['utility']>=best-policy['utility_tolerance']]
        active=list(db.execute('SELECT customer,symbol,sector FROM recommendation_exposures WHERE issued_at>?',(now-policy['window_seconds'],)))
        recent={r[0] for r in db.execute('SELECT symbol FROM recommendation_exposures WHERE customer=? AND issued_at>?',(customer,now-policy['customer_cooldown_seconds']))}
        reasons={};allowed=[]
        for c in comparable:
            symbol_count=sum(r[1]==c['symbol'] for r in active)
            sector_count=sum(r[2]==c['sector'] for r in active)
            blocked=[]
            if symbol_count>=policy['max_per_symbol']:blocked.append('SYMBOL_EXPOSURE_CAP')
            if sector_count>=policy['max_per_sector']:blocked.append('SECTOR_EXPOSURE_CAP')
            if c['symbol'] in recent:blocked.append('CUSTOMER_REPEAT_COOLDOWN')
            if blocked:reasons[c['symbol']]=blocked
            else:allowed.append(c)
        # Prefer highest utility until a cap/cooldown blocks it. Never widen tolerance.
        selected=sorted(allowed,key=lambda c:(-c['utility'],c['symbol']))[:1]
        result=dict(version=VERSION,policy_version=policy['version'],status='SELECTED' if selected else 'NO_SUITABLE_ALTERNATIVE',
                    symbol=selected[0]['symbol'] if selected else None,issued_at=now,
                    blocked=reasons,eligible_count=len(eligible),comparable_count=len(comparable),replayed=False)
        if selected:
            c=selected[0]
            db.execute('INSERT INTO recommendation_exposures VALUES (?,?,?,?,?)',(request_id,customer,c['symbol'],c['sector'],now))
        db.execute('INSERT INTO recommendation_requests VALUES (?,?,?)',(request_id,digest,json.dumps(result)))
        return result
