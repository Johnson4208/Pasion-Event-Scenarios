"""A15 single-host transactional research ledger. No broker or allocation API.

Callers must hold BEGIN IMMEDIATE through commit. Capacity is in shares;
parent and child budgets must use the same side, window and unit.
"""
import json
import hashlib
from datetime import datetime, timezone
import finance_core

VERSION = 'a15-v1'

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS shadow_capacity_budgets(id TEXT PRIMARY KEY,parent_id TEXT,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS shadow_capacity_positions(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS shadow_capacity_events(key TEXT PRIMARY KEY,request TEXT NOT NULL,payload TEXT NOT NULL)')

def transaction(db):
    if not db.in_transaction:
        raise ValueError('BEGIN IMMEDIATE transaction required')

def quantity(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('Nonnegative integer shares required')
    return value

def load(db, table, key):
    row = db.execute('SELECT payload FROM '+table+' WHERE id=?', (key,)).fetchone()
    if not row:
        raise ValueError('Unknown ledger record')
    return json.loads(row[0])

def budget(db, data, now=None):
    transaction(db)
    now = now or datetime.now(timezone.utc)
    record = {key:data[key] for key in ('id','venue','symbol','side','window_start','window_end','source_id','policy_version')}
    record.update(capacity=quantity(data['capacity']), parent_id=data.get('parent_id'), unit='SHARES', version=VERSION)
    start,end = map(finance_core.instant,(record['window_start'],record['window_end']))
    if record['side'] not in ('BUY','SELL') or not start <= now < end or data.get('same_window_tape_verified') is not True:
        raise ValueError('Verified same-window tape required')
    if any(not isinstance(record[k],str) or not record[k].strip() for k in ('id','venue','symbol','source_id','policy_version')):
        raise ValueError('Capacity provenance required')
    record['known_at']=now.isoformat()
    if record['parent_id']:
        parent=load(db,'shadow_capacity_budgets',record['parent_id'])
        if any(parent[k]!=record[k] for k in ('side','window_start','window_end')):
            raise ValueError('Parent side and window must match')
        if parent['venue'] not in ('*',record['venue']) or parent['symbol'] not in ('*',record['symbol']):
            raise ValueError('Child outside parent scope')
    db.execute('INSERT INTO shadow_capacity_budgets VALUES (?,?,?)',(record['id'],record['parent_id'],json.dumps(record)))
    return record

def chain(db, key):
    result=[]
    while key:
        if key in result:raise ValueError('Cyclic capacity hierarchy')
        result.append(key)
        key=load(db,'shadow_capacity_budgets',key)['parent_id']
    return result

def committed(position):
    # Cancellation confirmation frees only unfilled quantity; fills count for
    # the entire window. Reconciliation holds never silently release load.
    return position['active_offer']+position['filled']+position['unfilled']+position['reconciliation_hold']

def usage(db, budget_id):
    return sum(committed(p) for (raw,) in db.execute('SELECT payload FROM shadow_capacity_positions')
               for p in [json.loads(raw)] if budget_id in p['budget_chain'])

def event(db, data, now=None):
    transaction(db)
    now=now or datetime.now(timezone.utc)
    request=json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False)
    key=data['idempotency_key']
    if not isinstance(key,str) or not key.strip():raise ValueError('Replay key required')
    old=db.execute('SELECT request,payload FROM shadow_capacity_events WHERE key=?',(key,)).fetchone()
    if old:
        if old[0]!=request:raise ValueError('Replay payload conflict')
        return dict(json.loads(old[1]),replayed=True)
    action=data['action'];pid=data['position_id'];revision=data['expected_revision']
    if not isinstance(data.get('source_id'),str) or not data['source_id'].strip():raise ValueError('Event source record required')
    if not isinstance(pid,str) or not pid.strip():raise ValueError('Position identity required')
    if isinstance(revision,bool) or not isinstance(revision,int):raise ValueError('Integer revision required')
    if action=='Offer':
        if revision!=0 or db.execute('SELECT 1 FROM shadow_capacity_positions WHERE id=?',(pid,)).fetchone():raise ValueError('Position already exists')
        b=load(db,'shadow_capacity_budgets',data['budget_id'])
        if '*' in (b['venue'],b['symbol']):raise ValueError('Leaf instrument budget required')
        expires=finance_core.instant(data['expires_at'])
        if not now<expires<=finance_core.instant(b['window_end']):raise ValueError('Bounded offer TTL required')
        q=quantity(data['quantity'])
        if not q:raise ValueError('Positive offer required')
        p=dict(id=pid,budget_id=b['id'],budget_chain=chain(db,b['id']),revision=0,
               active_offer=q,filled=0,unfilled=0,reconciliation_hold=0,status='OFFER',expires_at=expires.isoformat())
        for bid in p['budget_chain']:
            bound=load(db,'shadow_capacity_budgets',bid)
            for (raw,) in db.execute('SELECT payload FROM shadow_capacity_positions'):
                other=json.loads(raw)
                if bid in other['budget_chain'] and other['status']=='RECONCILIATION_REQUIRED':raise ValueError('Capacity reconciliation required')
            if not finance_core.instant(bound['window_start'])<=now<finance_core.instant(bound['window_end']):raise ValueError('Capacity window closed')
            if usage(db,bid)+q>bound['capacity']:raise ValueError('Shared capacity exceeded')
    else:
        p=load(db,'shadow_capacity_positions',pid)
        if revision!=p['revision']:raise ValueError('Revision conflict')
        if action=='Plan':
            if p['status']!='OFFER':raise ValueError('Offer required')
            if now>=finance_core.instant(p['expires_at']):raise ValueError('Offer expired')
            p['status']='PLAN'
        elif action=='Ordered':
            if p['status'] not in ('OFFER','PLAN') or now>=finance_core.instant(p['expires_at']):raise ValueError('Live offer required')
            p['unfilled']=p['active_offer'];p['active_offer']=0;p['status']='ORDERED'
        elif action in ('PartialFill','Fill'):
            q=quantity(data['quantity'])
            if p['status'] not in ('ORDERED','PARTIAL_FILL','CANCEL_REQUESTED') or not 0<q<=p['unfilled']:raise ValueError('Invalid fill')
            if action=='Fill' and q!=p['unfilled']:raise ValueError('Final fill must consume unfilled quantity')
            cancelling=p['status']=='CANCEL_REQUESTED'
            p['unfilled']-=q;p['filled']+=q
            p['status']='FILLED' if not p['unfilled'] else 'CANCEL_REQUESTED' if cancelling else 'PARTIAL_FILL'
        elif action=='CancelRequested':
            if p['status'] not in ('ORDERED','PARTIAL_FILL'):raise ValueError('Open order required')
            p['status']='CANCEL_REQUESTED'
        elif action=='CancelConfirmed':
            if p['status']!='CANCEL_REQUESTED':raise ValueError('Cancel request required')
            p['unfilled']=0;p['status']='CANCELLED'
        elif action=='Expired':
            if p['status'] not in ('OFFER','PLAN') or now<finance_core.instant(p['expires_at']):raise ValueError('Expired offer required')
            p['active_offer']=0;p['status']='EXPIRED'
        elif action in ('LateFill','Bust','ReconciliationRequired'):
            # Unknown broker/tape corrections freeze capacity; never create
            # spare capacity by subtracting a reported fill or bust.
            if action=='LateFill':
                q=quantity(data['quantity'])
                if not q:raise ValueError('Positive late fill required')
                p['reconciliation_hold']+=q
            p['status']='RECONCILIATION_REQUIRED'
        else:raise ValueError('Unsupported ledger event')
    p['revision']+=1
    result=dict(event_id=hashlib.sha256(key.encode()).hexdigest(),action=action,source_id=data['source_id'],known_at=now.isoformat(),
                position=p,version=VERSION,replayed=False,allocation_weight=None,calibrated=False,status='AUDIT_ONLY_SHADOW')
    payload=json.dumps(p)
    if revision==0 and action=='Offer':
        db.execute('INSERT INTO shadow_capacity_positions VALUES (?,?,?)',(pid,p['revision'],payload))
    else:
        changed=db.execute('UPDATE shadow_capacity_positions SET revision=?,payload=? WHERE id=? AND revision=?',(p['revision'],payload,pid,revision))
        if changed.rowcount!=1:raise ValueError('Concurrent revision conflict')
    db.execute('INSERT INTO shadow_capacity_events VALUES (?,?,?)',(key,request,json.dumps(result)))
    return result

def audit(db):
    initialize(db)
    budgets=[]
    for (raw,) in db.execute('SELECT payload FROM shadow_capacity_budgets'):
        b=json.loads(raw);used=usage(db,b['id'])
        budgets.append(dict(b,committed=used,remaining_capacity=max(0,b['capacity']-used),breached=used>b['capacity']))
    return dict(version=VERSION,status='AUDIT_ONLY_SHADOW',budgets=budgets,
                events=[json.loads(r[0]) for r in db.execute('SELECT payload FROM shadow_capacity_events ORDER BY rowid DESC LIMIT 100')])
