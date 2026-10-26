"""F13 owner-scoped watch intents and immutable, deduplicated alert evaluations."""
import hashlib
import json
import re
import secrets
from datetime import datetime,timezone
import finance_core
import feasibility


def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS watch_intents(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES accounts(email),payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS watch_events(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES accounts(email),fingerprint TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(owner,fingerprint));
      CREATE TABLE IF NOT EXISTS watch_acks(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES accounts(email),event_id TEXT NOT NULL REFERENCES watch_events(id),payload TEXT NOT NULL,UNIQUE(owner,event_id));''')


def save(db,owner,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    kind=data['intent_type']
    if kind not in ('WATCH','PRICE_ALERT','RESEARCH_BOOKMARK'):raise ValueError()
    ticker=data.get('ticker','')
    if kind!='RESEARCH_BOOKMARK' and not re.fullmatch('[A-Z0-9.-]{1,16}',ticker):raise ValueError()
    record={'id':secrets.token_hex(16),'intent_type':kind,'ticker':ticker,'created_at':now.isoformat(),'source':'MANUAL_EXPLICIT_INTENT','execution_policy':'NOT_AN_ORDER_OR_HOLDING'}
    if data.get('imported'):
        if data.get('consent') is not True:raise ValueError()
        record['source']='CONSENTED_BROWSER_IMPORT_UNVERIFIED'
    if kind=='PRICE_ALERT':
        target=feasibility.decimal(data['target'])
        if target<=0 or data['currency'] not in ('USD','VND','EUR','GBP','JPY','CNY') or data['direction'] not in ('ABOVE','BELOW'):raise ValueError()
        throttle=data.get('throttle_seconds',3600)
        if isinstance(throttle,bool) or not isinstance(throttle,int) or not 60<=throttle<=86400:raise ValueError()
        record.update(target=str(target),currency=data['currency'],direction=data['direction'],throttle_seconds=throttle)
    if kind=='RESEARCH_BOOKMARK':
        reference=data['reference']
        if not isinstance(reference,str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,200}',reference):raise ValueError()
        record['reference']=reference
    for row in db.execute('SELECT payload FROM watch_intents WHERE owner=?',(owner,)):
        old=json.loads(row[0])
        if kind in ('WATCH','RESEARCH_BOOKMARK') and old['intent_type']==kind and (old.get('ticker')==ticker if kind=='WATCH' else old.get('reference')==record.get('reference')):
            return {'version':1,'intent':old}
    db.execute('INSERT INTO watch_intents VALUES (?,?,?)',(record['id'],owner,json.dumps(record)))
    return {'version':1,'intent':record}


def read(db,owner):
    initialize(db)
    return {'version':1,'intents':[json.loads(r[0]) for r in db.execute('SELECT payload FROM watch_intents WHERE owner=? ORDER BY rowid DESC',(owner,))],
        'events':[json.loads(r[0]) for r in db.execute('SELECT payload FROM watch_events WHERE owner=? ORDER BY rowid DESC LIMIT 200',(owner,))],
        'acknowledgments':[json.loads(r[0]) for r in db.execute('SELECT payload FROM watch_acks WHERE owner=?',(owner,))],
        'channel_status':'IN_APP_ONLY_NO_EXTERNAL_PUSH','feed_status':'VERIFIED_QUOTES_REQUIRED'}


def evaluate(db,owner,now=None):
    initialize(db);feasibility.initialize(db);now=now or datetime.now(timezone.utc);created=[]
    for row in db.execute('SELECT payload FROM watch_intents WHERE owner=?',(owner,)).fetchall():
        intent=json.loads(row[0])
        if intent['intent_type']!='PRICE_ALERT':continue
        row=db.execute('SELECT payload FROM trading_instruments WHERE ticker=?',(intent['ticker'],)).fetchone()
        rules=json.loads(row[0]) if row else None;reason='REVIEWED_QUOTE_REQUIRED';trigger=False;quote_id='missing';source=None
        if rules:
            q=rules['quote'];asof=finance_core.instant(q['as_of']);opened=finance_core.instant(q['session_open']);closed=finance_core.instant(q['session_close'])
            quote_id=rules['version']+'|'+q['as_of'];source=rules['source']
            if rules['currency']!=intent['currency']:reason='CURRENCY_MISMATCH'
            elif not opened<=asof<=closed or asof>now or not opened<=now<=closed:reason='QUOTE_SESSION_INVALID'
            elif (now-asof).total_seconds()>float(feasibility.decimal(q['max_age_seconds'])):reason='QUOTE_EXPIRED'
            else:
                price,target=feasibility.decimal(q['price']),feasibility.decimal(intent['target'])
                trigger=price>=target if intent['direction']=='ABOVE' else price<=target
                reason='PRICE_THRESHOLD_MET' if trigger else 'PRICE_THRESHOLD_NOT_MET'
        fingerprint=hashlib.sha256((intent['id']+'|'+quote_id+'|'+reason).encode()).hexdigest()
        if db.execute('SELECT 1 FROM watch_events WHERE owner=? AND fingerprint=?',(owner,fingerprint)).fetchone():continue
        # Throttle only new notifications from this alert/source, never overwrite prior trigger evidence.
        notification=trigger
        if trigger:
            previous=[json.loads(r[0]) for r in db.execute('SELECT payload FROM watch_events WHERE owner=?',(owner,))]
            if any(e['intent_id']==intent['id'] and e.get('source')==source and e['notification'] and (now-finance_core.instant(e['evaluated_at'])).total_seconds()<intent['throttle_seconds'] for e in previous):notification=False
        event={'id':secrets.token_hex(16),'intent_id':intent['id'],'intent_type':'ALERT_EVALUATION','ticker':intent['ticker'],
            'evaluated_at':now.isoformat(),'source':source,'source_version':quote_id,'reason':reason,'triggered':trigger,
            'notification':notification,'delivery':'IN_APP' if notification else 'THROTTLED' if trigger else 'NO_NOTIFICATION',
            'quote':rules['quote'] if rules else None,'execution_policy':'INFORMATION_ONLY_NOT_EXECUTION'}
        db.execute('INSERT INTO watch_events VALUES (?,?,?,?)',(event['id'],owner,fingerprint,json.dumps(event)));created.append(event)
    return {'version':1,'created':created}


def acknowledge(db,owner,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    if not db.execute('SELECT 1 FROM watch_events WHERE id=? AND owner=?',(data['event_id'],owner)).fetchone():raise ValueError()
    existing=db.execute('SELECT payload FROM watch_acks WHERE owner=? AND event_id=?',(owner,data['event_id'])).fetchone()
    if existing:return {'version':1,'acknowledgment':json.loads(existing[0])}
    record={'id':secrets.token_hex(16),'event_id':data['event_id'],'acknowledged_at':now.isoformat()}
    db.execute('INSERT INTO watch_acks VALUES (?,?,?,?)',(record['id'],owner,data['event_id'],json.dumps(record)))
    return {'version':1,'acknowledgment':record}
