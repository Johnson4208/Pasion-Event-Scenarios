"""F10 immutable evidence and private scenario judgments; no probability model."""
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal
import finance_core
import evidence_service
from macro_evidence import label, source, number


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS event_claims(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS event_versions(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS event_resolutions(id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES event_versions(id),owner TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,payload TEXT NOT NULL)')


def ingest(db,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    if data.get('reviewed') is not True or data['input_type'] not in ('ACTUAL','PROXY'):raise ValueError()
    record={k:label(data[k]) for k in ('claim_key','claim','provider','source_url','revision','input_type','input_policy')}
    source(record['source_url'])
    published,ingested,revised=[finance_core.instant(data[k]) for k in ('published_at','ingested_at','revised_at')]
    if published>now or ingested>now or revised>now or revised<published:raise ValueError()
    record.update(id=secrets.token_hex(16),published_at=published.isoformat(),ingested_at=ingested.isoformat(),
        revised_at=revised.isoformat(),known_at=max(now,published,ingested,revised).isoformat(),accepted_at=now.isoformat())
    record['latency']=evidence_service.latency(record['published_at'],record['ingested_at'])
    record['duplicate_group']=label(data['duplicate_group']) if data.get('duplicate_group') else record['source_url']
    db.execute('INSERT INTO event_claims VALUES (?,?)',(record['id'],json.dumps(record)))
    return {'version':1,'evidence':record}


def eligible(db,cutoff):
    initialize(db);groups={}
    for row in db.execute('SELECT payload FROM event_claims'):
        claim=json.loads(row[0])
        if finance_core.instant(claim['known_at'])<=cutoff:
            groups.setdefault(claim['claim_key'],[]).append(claim)
    result=[]
    for claims in groups.values():
        latest=max((r['revised_at'],r['known_at']) for r in claims)
        matches=[r for r in claims if (r['revised_at'],r['known_at'])==latest]
        if len(matches)==1:result.append(matches[0])
    # Shared retrieval surface, separate adjudication semantics: a news claim is proxy context, not a resolved fact.
    import news_evidence
    news=news_evidence.feed(db,'',cutoff.isoformat(),cutoff)
    clusters=set()
    for article in news['articles']:
        if article['cluster_id'] in clusters:continue
        clusters.add(article['cluster_id'])
        for claim in article['claims']:
            review=claim['review'];known=evidence_service.usable_event_time([article,{'known_at':review.get('known_at',article['known_at'])}])
            if finance_core.instant(known)>cutoff:continue
            result.append({'id':'news:'+claim['id']+':'+review.get('id','unreviewed'),'claim_key':'news:'+claim['id'],'claim':claim['text'],
                'provider':article['provider'],'source_url':article['url'],'revision':article['revision'],'input_type':'PROXY',
                'input_policy':'NEWS_ASSERTION_CONTEXT_VERDICT_'+review['status']+'_NOT_CALIBRATED_EVENT_PROBABILITY',
                'published_at':article['published_at'],'ingested_at':article['ingested_at'],'revised_at':review.get('known_at',article['known_at']),
                'known_at':known,'duplicate_group':article['cluster_id'],'evidence_status':review['status']})
    return result


def evidence(db,origin=None,now=None):
    now=now or datetime.now(timezone.utc);cutoff=finance_core.instant(origin) if origin else now
    if cutoff>now:raise ValueError()
    return {'version':1,'cutoff':cutoff.isoformat(),'claims':eligible(db,cutoff)}


def save(db,owner,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    cutoff,maturity=finance_core.instant(data['cutoff']),finance_core.instant(data['maturity'])
    if cutoff>now or maturity<=cutoff:raise ValueError()
    record={k:label(data[k]) for k in ('question','event_definition','category','factor','focus','cluster_id')}
    parent=data.get('parent_id')
    if parent and not db.execute('SELECT 1 FROM event_versions WHERE id=? AND owner=?',(parent,owner)).fetchone():raise ValueError()
    outcomes=data['outcomes']
    if not isinstance(outcomes,list) or not 2<=len(outcomes)<=6:raise ValueError()
    claims={r['id']:r for r in eligible(db,cutoff)};clean=[];identifiers=set()
    for outcome in outcomes:
        key=label(outcome['id'])
        if key in identifiers:raise ValueError()
        identifiers.add(key)
        weight=None if outcome.get('weight') is None else number(outcome['weight'])
        if weight is not None and not 0<=weight<=100:raise ValueError()
        links=[]
        for link in outcome.get('evidence',[]):
            if len(links)>=50 or link['id'] not in claims or link['stance'] not in ('SUPPORTING','OPPOSING','MIXED'):raise ValueError()
            if any(l['id']==link['id'] for l in links):raise ValueError()
            links.append({'id':link['id'],'stance':link['stance'],'relevance':label(link['relevance']),'claim':claims[link['id']]})
        clean.append({'id':key,'name':label(outcome['name']),'resolution_rule':label(outcome['resolution_rule']),
            'condition':label(outcome['condition']),'assumption':label(outcome['assumption']),
            'weight':str(weight) if weight is not None else None,'evidence':links,
            'evidence_status':'SOURCED_CONTEXT' if links else 'MISSING_EVIDENCE','evidence_group_count':len({l['claim'].get('duplicate_group',l['claim']['source_url']) for l in links}),
            'group_policy':'DEDUPLICATED_SOURCE_GROUPS_NOT_PROOF_OF_STATISTICAL_INDEPENDENCE'})
    weights=[r['weight'] for r in clean]
    if any(w is not None for w in weights) and (any(w is None for w in weights) or sum(Decimal(w) for w in weights)!=100):raise ValueError()
    record.update(id=secrets.token_hex(16),parent_id=parent,created_at=now.isoformat(),cutoff=cutoff.isoformat(),maturity=maturity.isoformat(),outcomes=clean,
        weight_policy='ANALYTICAL_JUDGMENT_NOT_PROBABILITY',probability_status='UNAVAILABLE_NO_CALIBRATED_EVENT_MODEL',
        downstream_policy='NO_STOCK_P_UP_OR_KELLY_INPUT',calculation_version='f10-v1',
        temporal_status='CONTEMPORANEOUS' if (now-cutoff).total_seconds()<=60 else 'RETROSPECTIVE_RESEARCH_NOT_ORIGIN_FORECAST')
    record['usable_event_time']=evidence_service.usable_event_time([link['claim'] for outcome in clean for link in outcome['evidence']])
    record['probability_boundaries']=evidence_service.BOUNDARIES
    db.execute('INSERT INTO event_versions VALUES (?,?,?)',(record['id'],owner,json.dumps(record)))
    return {'version':1,'study':record}


def resolve(db,owner,data,now=None):
    initialize(db);now=now or datetime.now(timezone.utc)
    row=db.execute('SELECT payload FROM event_versions WHERE id=? AND owner=?',(data['version_id'],owner)).fetchone()
    if not row:raise ValueError()
    study=json.loads(row[0]);observed=finance_core.instant(data['observed_at'])
    if not finance_core.instant(study['maturity'])<=observed<=now or data['outcome_id'] not in {r['id'] for r in study['outcomes']}:raise ValueError()
    claim=next((r for r in eligible(db,now) if r['id']==data['evidence_id']),None)
    if not claim or claim['input_type']!='ACTUAL' or finance_core.instant(claim['published_at'])>observed:raise ValueError()
    if db.execute('SELECT 1 FROM event_resolutions WHERE version_id=? AND owner=?',(study['id'],owner)).fetchone():raise ValueError()
    record={'id':secrets.token_hex(16),'version_id':study['id'],'outcome_id':data['outcome_id'],
        'observed_at':observed.isoformat(),'known_at':now.isoformat(),'evidence':claim,'explanation':label(data['explanation']),
        'status':'MANUALLY_RECORDED_OUTCOME_NOT_CALIBRATION_CERTIFICATION',
        'outcome_quality':label(data['quality_note']) if data.get('quality_note') else 'MANUAL_REVIEW_NOT_INDEPENDENTLY_AUDITED',
        'probability_boundaries':evidence_service.BOUNDARIES}
    db.execute('INSERT INTO event_resolutions VALUES (?,?,?,?)',(record['id'],study['id'],owner,json.dumps(record)))
    return {'version':1,'resolution':record}


def history(db,owner):
    initialize(db)
    studies=[json.loads(r[0]) for r in db.execute('SELECT payload FROM event_versions WHERE owner=? ORDER BY rowid DESC LIMIT 200',(owner,))]
    resolutions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM event_resolutions WHERE owner=?',(owner,))]
    return {'version':1,'studies':studies,'resolutions':resolutions,'probability_status':'UNAVAILABLE_NO_CALIBRATED_EVENT_MODEL'}
