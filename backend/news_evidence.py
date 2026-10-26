"""F11 permitted-source news, reviewed claim relations and proposed driver changes."""
import hashlib
import json
import re
import secrets
from datetime import datetime,timezone
from urllib.parse import urlparse,urlunparse,parse_qsl,urlencode
import finance_core
import evidence_service
from macro_evidence import label,source


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS news_sources(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS news_articles(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS news_reviews(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS news_bookmarks(owner TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,article_id TEXT NOT NULL REFERENCES news_articles(id),PRIMARY KEY(owner,article_id))')
    db.execute('CREATE TABLE IF NOT EXISTS news_proposals(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS news_decisions(id TEXT PRIMARY KEY,proposal_id TEXT NOT NULL REFERENCES news_proposals(id),payload TEXT NOT NULL)')


def register(db,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    if data.get('permitted') is not True:raise ValueError()
    row={k:label(data[k]) for k in ('id','name','source_url','permission_basis','coverage')};source(row['source_url'])
    if db.execute('SELECT 1 FROM news_sources WHERE id=?',(row['id'],)).fetchone():raise ValueError()
    age=data['max_gap_seconds']
    if isinstance(age,bool) or not isinstance(age,int) or not 60<=age<=2592000:raise ValueError()
    row.update(max_gap_seconds=age,known_at=now.isoformat())
    db.execute('INSERT INTO news_sources VALUES (?,?)',(row['id'],json.dumps(row)))
    return {'version':1,'source':row}


def ingest(db,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    row=db.execute('SELECT payload FROM news_sources WHERE id=?',(data['source_id'],)).fetchone()
    if not row:raise ValueError()
    provider=json.loads(row[0]);url=source(data['url'])
    if urlparse(url).hostname!=urlparse(provider['source_url']).hostname:raise ValueError()
    published,ingested=finance_core.instant(data['published_at']),finance_core.instant(data['ingested_at'])
    if published>now or ingested>now or ingested<published:raise ValueError()
    tickers=data['tickers']
    if not isinstance(tickers,list) or len(tickers)>20 or any(not re.fullmatch('[A-Z0-9.-]{1,16}',k) for k in tickers):raise ValueError()
    claims=[]
    for c in data['claims']:
        if len(claims)>=30:raise ValueError()
        quantities=[]
        for q in c.get('quantities',[]):
            value=str(q['value']);unit=label(q['unit'])
            from decimal import Decimal
            if not Decimal(value).is_finite() or len(quantities)>=30:raise ValueError()
            quantities.append({'value':value,'unit':unit})
        assertion=finance_core.instant(c.get('asserted_at',data['published_at']))
        if assertion>now:raise ValueError()
        claims.append({'id':secrets.token_hex(16),'text':label(c['text']),'excerpt':label(c['excerpt']),'locator':label(c['locator']),
            'entity':label(c['entity']) if c.get('entity') else None,'entity_status':'EXPLICIT' if c.get('entity') else 'UNSPECIFIED','asserted_at':assertion.isoformat(),'quantities':quantities})
    # Remove query tracking and fragment from canonical identity, preserving the path.
    parsed=urlparse(url);query=urlencode(sorted((k,v) for k,v in parse_qsl(parsed.query) if not k.casefold().startswith('utm_') and k.casefold() not in ('gclid','fbclid')))
    canonical=urlunparse((parsed.scheme,parsed.netloc.casefold(),parsed.path,'',query,'')).rstrip('/')
    title=label(data['title']);normalized=' '.join(title.casefold().split())
    cluster=hashlib.sha256((normalized+'|'+published.date().isoformat()).encode()).hexdigest()[:24]
    if data.get('cluster_key'):
        cluster=hashlib.sha256(('reviewed-cluster|'+label(data['cluster_key'])).encode()).hexdigest()[:24]
    identity=hashlib.sha256(canonical.encode()).hexdigest()
    old=[json.loads(r[0]) for r in db.execute('SELECT payload FROM news_articles')]
    if any(r['identity']==identity and r['revision']==data['revision'] for r in old):raise ValueError()
    record={'id':secrets.token_hex(16),'identity':identity,'cluster_id':cluster,'source_id':provider['id'],'provider':provider['name'],
        'url':url,'title':title,'summary':label(data['summary']),'category':label(data['category']),'tickers':tickers,
        'claims':claims,'revision':label(data['revision']),'published_at':published.isoformat(),'ingested_at':ingested.isoformat(),
        'known_at':max(now,published,ingested).isoformat(),'accepted_at':now.isoformat(),
        'latency_seconds':(ingested-published).total_seconds(),'extraction_policy':'ADMIN_SUBMITTED_CLAIM_EXCERPTS_NO_AUTOMATED_TRUTH_INFERENCE'}
    db.execute('INSERT INTO news_articles VALUES (?,?)',(record['id'],json.dumps(record)))
    return {'version':1,'article':record}


def review(db,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    articles=[json.loads(r[0]) for r in db.execute('SELECT payload FROM news_articles')]
    target=next((a for a in articles if a['id']==data['article_id']),None)
    if not target or data['claim_id'] not in {c['id'] for c in target['claims']}:raise ValueError()
    if finance_core.instant(target['known_at'])>now:raise ValueError()
    relations=[]
    for link in data['relations']:
        related=next((a for a in articles if a['id']==link['article_id']),None)
        if not related or related['id']==target['id'] or related['cluster_id']==target['cluster_id'] or related['identity']==target['identity']:raise ValueError()
        if finance_core.instant(related['known_at'])>now or any(r['article_id']==related['id'] and r['claim_id']==link['claim_id'] for r in relations):raise ValueError()
        if link['claim_id'] not in {c['id'] for c in related['claims']} or link['stance'] not in ('SUPPORTING','REFUTING'):raise ValueError()
        if len(relations)>=30:raise ValueError()
        relations.append({'article_id':related['id'],'claim_id':link['claim_id'],'stance':link['stance'],'explanation':label(link['explanation']),
            'excerpt':next(c['excerpt'] for c in related['claims'] if c['id']==link['claim_id']),'url':related['url'],'provider':related['provider'],
            'published_at':related['published_at'],'ingested_at':related['ingested_at'],'known_at':related['known_at'],'revision':related['revision']})
    stances={r['stance'] for r in relations}
    status=evidence_service.verdict(stances)
    record={'id':secrets.token_hex(16),'article_id':target['id'],'claim_id':data['claim_id'],'known_at':now.isoformat(),
        'status':status,'relations':relations,'review_note':label(data['review_note']),'policy':'HUMAN_REVIEWED_CLAIM_RELATIONS_NOT_TRUTH_PROBABILITY',
        'verdict_at':now.isoformat(),'latency':evidence_service.latency(target['published_at'],target['ingested_at'],now.isoformat()),
        'usable_event_time':evidence_service.usable_event_time([target]+relations+[{'known_at':now.isoformat()}])}
    db.execute('INSERT INTO news_reviews VALUES (?,?)',(record['id'],json.dumps(record)))
    return {'version':1,'review':record}


def feed(db,owner,origin=None,now=None):
    initialize(db);now=now or datetime.now(timezone.utc);cutoff=finance_core.instant(origin) if origin else now
    if cutoff>now:raise ValueError()
    all_articles=[json.loads(r[0]) for r in db.execute('SELECT payload FROM news_articles')]
    articles=[a for a in all_articles if finance_core.instant(a['known_at'])<=cutoff]
    chosen={}
    for a in articles:
        if a['identity'] not in chosen or a['known_at']>chosen[a['identity']]['known_at']:chosen[a['identity']]=a
        elif a['known_at']==chosen[a['identity']]['known_at']:chosen[a['identity']]=dict(a,ambiguous=True)
    articles=list(chosen.values())
    saved=[r[0] for r in db.execute('SELECT article_id FROM news_bookmarks WHERE owner=?',(owner,))]
    # Retain exact bookmarked revisions, visibly superseded; never silently upgrade a bookmark.
    for a in all_articles:
        if a['id'] in saved and finance_core.instant(a['known_at'])<=cutoff and not any(r['id']==a['id'] for r in articles):
            articles.append(dict(a,superseded=True))
    reviews=[json.loads(r[0]) for r in db.execute('SELECT payload FROM news_reviews')]
    for a in articles:
        for c in a['claims']:
            matches=[r for r in reviews if r['article_id']==a['id'] and r['claim_id']==c['id'] and finance_core.instant(r['known_at'])<=cutoff]
            newest=max((r['known_at'] for r in matches),default=None);matches=[r for r in matches if r['known_at']==newest]
            selected=matches[0] if len(matches)==1 and not a.get('ambiguous') and not a.get('superseded') else None
            if selected:
                for link in selected['relations']:
                    original=next((r for r in all_articles if r['id']==link['article_id']),None)
                    latest=chosen.get(original['identity']) if original else None
                    if not latest or latest['id']!=link['article_id'] or latest.get('ambiguous'):
                        selected=None;break
            c['review']=selected or {'status':'INSUFFICIENT','relations':[],'review_note':'No current unambiguous claim review at origin; revised evidence requires renewed review'}
    coverage=[]
    for row in db.execute('SELECT payload FROM news_sources'):
        p=json.loads(row[0])
        if finance_core.instant(p['known_at'])>cutoff:continue
        arrivals=[a for a in all_articles if a['source_id']==p['id'] and finance_core.instant(a['known_at'])<=cutoff]
        last=max((a['known_at'] for a in arrivals),default=None)
        gap=(cutoff-finance_core.instant(last)).total_seconds() if last else None
        coverage.append({**p,'last_known_at':last,'gap_seconds':gap,'status':'READY' if gap is not None and gap<=p['max_gap_seconds'] else 'GAP',
            'mean_ingest_latency_seconds':sum(a['latency_seconds'] for a in arrivals)/len(arrivals) if arrivals else None})
    return {'version':1,'origin':cutoff.isoformat(),'articles':sorted(articles,key=lambda a:a['published_at'],reverse=True)[:200],
        'coverage':coverage,'bookmarks':saved,'status':'PARTIAL' if articles else 'UNAVAILABLE','score_policy':'NO_NEWS_TRUTH_OR_RETURN_SCORE'}


def bookmark(db,owner,data):
    initialize(db)
    if not db.execute('SELECT 1 FROM news_articles WHERE id=?',(data['article_id'],)).fetchone() or not isinstance(data['saved'],bool):raise ValueError()
    if data['saved']:db.execute('INSERT OR IGNORE INTO news_bookmarks VALUES (?,?)',(owner,data['article_id']))
    else:db.execute('DELETE FROM news_bookmarks WHERE owner=? AND article_id=?',(owner,data['article_id']))
    return {'version':1,'saved':data['saved']}


def propose(db,owner,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    a=next((a for a in feed(db,owner,now=now)['articles'] if a['id']==data['article_id']),None)
    claim=next((c for c in a['claims'] if c['id']==data['claim_id']),None) if a else None
    if not claim or claim['review']['status']!='SUPPORTED' or data['ticker'] not in a['tickers']:raise ValueError()
    record={k:label(data[k]) for k in ('ticker','driver','proposed_change','rationale')}
    record.update(id=secrets.token_hex(16),created_at=now.isoformat(),article_id=a['id'],claim_id=claim['id'],
        claim=claim,source_url=a['url'],status='PENDING_RESEARCH_REVIEW',valuation_policy='NO_AUTOMATIC_BASELINE_CHANGE')
    db.execute('INSERT INTO news_proposals VALUES (?,?,?)',(record['id'],owner,json.dumps(record)))
    return {'version':1,'proposal':record}


def decide(db,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    if data['decision'] not in ('APPROVED_FOR_DRIVER_REVIEW','REJECTED'):raise ValueError()
    if not db.execute('SELECT 1 FROM news_proposals WHERE id=?',(data['proposal_id'],)).fetchone():raise ValueError()
    if data['decision']=='APPROVED_FOR_DRIVER_REVIEW':
        row=db.execute('SELECT owner,payload FROM news_proposals WHERE id=?',(data['proposal_id'],)).fetchone();p=json.loads(row[1])
        a=next((a for a in feed(db,row[0],now=now)['articles'] if a['id']==p['article_id']),None)
        c=next((c for c in a['claims'] if c['id']==p['claim_id']),None) if a else None
        if not c or c['review']['status']!='SUPPORTED':raise ValueError()
    record={'id':secrets.token_hex(16),'proposal_id':data['proposal_id'],'decision':data['decision'],'note':label(data['note']),
        'known_at':now.isoformat(),'valuation_policy':'SEPARATE_F04_ASSUMPTION_REVIEW_REQUIRED'}
    db.execute('INSERT INTO news_decisions VALUES (?,?,?)',(record['id'],data['proposal_id'],json.dumps(record)))
    return {'version':1,'decision':record}


def proposals(db,owner):
    initialize(db)
    rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM news_proposals WHERE owner=? ORDER BY rowid DESC LIMIT 200',(owner,))]
    for p in rows:
        p['decisions']=[json.loads(r[0]) for r in db.execute('SELECT payload FROM news_decisions WHERE proposal_id=? ORDER BY rowid',(p['id'],))]
        if p['decisions']:p['status']=p['decisions'][-1]['decision']
    return {'version':1,'proposals':rows}


def review_queue(db):
    initialize(db)
    rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM news_proposals ORDER BY rowid DESC LIMIT 200')]
    for p in rows:
        last=db.execute('SELECT payload FROM news_decisions WHERE proposal_id=? ORDER BY rowid DESC LIMIT 1',(p['id'],)).fetchone()
        if last:p['status']=json.loads(last[0])['decision']
    return {'version':1,'proposals':rows}
