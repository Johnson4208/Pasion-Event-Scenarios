"""F12 staged document observations, explicit review and immutable source excerpts."""
import copy
import hashlib
import json
import secrets
from datetime import datetime,timezone
from decimal import Decimal
import document_service
import finance_core as finance
from macro_evidence import label

def financial_fact_key(issuer,fact):
    return hashlib.sha256(json.dumps([issuer]+[fact[k] for k in ('definition_id','period_type','period_start','period_end','unit','currency','accounting_basis','scope','ownership','restatement_basis','revision')],separators=(',',':')).encode()).hexdigest()

def structured_context(value,fact):
    if value is None:return None
    keys=('namespace','concept','context_ref','unit_ref','entity_identifier','decimals','filing_id','amendment','source_locator')
    result={k:label(value[k]) for k in keys}
    dimensions=value['dimensions']
    if not isinstance(dimensions,dict) or len(dimensions)>30:raise ValueError()
    result['dimensions']={label(k):label(v) for k,v in dimensions.items()}
    if value['period_start']!=fact['period_start'] or value['period_end']!=fact['period_end'] or value['currency']!=fact['currency']:raise ValueError('Structured context mismatch')
    result.update(period_start=fact['period_start'],period_end=fact['period_end'],currency=fact['currency'])
    return result


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS finance_stages(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS finance_stage_decisions(id TEXT PRIMARY KEY,stage_id TEXT UNIQUE NOT NULL REFERENCES finance_stages(id),payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS finance_source_excerpts(fact_id TEXT PRIMARY KEY REFERENCES facts(id),payload TEXT NOT NULL)')


def observations(root,document_id):
    document=document_service.get_document(root,document_id)
    if document['status']!='ready':raise ValueError()
    _,original=document_service.get_original(root,document_id)
    sections=[{k:s.get(k) for k in ('id','title','page','text','table','bbox')} for s in document.get('sections',[])]
    return {'version':1,'document_id':document_id,'source_hash':hashlib.sha256(original).hexdigest(),
        'parser_version':'pasion-document-service-v1','sections':sections,'definitions':finance.DEFINITIONS,
        'xbrl_adapter':{'version':1,'status':'CONTRACT_ONLY','required':['namespace','concept','context_id','entity_identifier','period','unit_ref','decimals','dimensions','source_locator'],
            'policy':'External XBRL/iXBRL adapters must emit staged sidecar facts with original-document evidence; tags never bypass review'},
        'policy':'EXTRACTION_OBSERVATIONS_NOT_ACCOUNTING_VALIDITY'}


def warnings(facts):
    groups={};output=[]
    for fact in facts:
        key=tuple(fact[k] for k in ('period_start','period_end','currency','scope','accounting_basis','restatement_basis','unit'))
        groups.setdefault(key,{}).setdefault(fact['definition_id'],[]).append(fact)
    for context,metrics in groups.items():
        if not any(k in metrics for k in ('assets','liabilities','equity')):continue
        keys=('assets','liabilities','equity')
        if any(len(metrics.get(k,[]))!=1 or metrics[k][0]['value'] is None for k in keys):
            output.append({'code':'BALANCE_IDENTITY_INCOMPLETE','context':list(context)});continue
        values=[Decimal(str(metrics[k][0]['value']))*Decimal(str(metrics[k][0]['scale'])) for k in keys]
        discrepancy=values[0]-values[1]-values[2]
        if discrepancy!=0:output.append({'code':'BALANCE_IDENTITY_DISCREPANCY','difference':str(discrepancy),'context':list(context)})
    return output


def stage(root,data,reviewer,now=None):
    now=now or datetime.now(timezone.utc);document_id=data['document_id']
    extracted=observations(root,document_id);payload=copy.deepcopy(data['payload'])
    identifier=secrets.token_hex(16)
    if len(payload['reports'])!=1:raise ValueError()
    report=payload['reports'][0]
    report.update(id='report-'+identifier,document_id=document_id,source_hash=extracted['source_hash'],parser_version=extracted['parser_version'])
    if finance.instant(report['published_at'])>now or finance.instant(report['indexed_at'])>now:raise ValueError()
    citations={};raw_observations={};seen_keys=set()
    for index,fact in enumerate(payload['facts']):
        fact.update(id='fact-'+identifier+'-'+str(index),report_id=report['id'],reviewed=True)
        evidence=fact['evidence'];section=next((s for s in extracted['sections'] if str(s['id'])==str(evidence['section_id'])),None)
        if not section or section['page']!=evidence['page']:raise ValueError()
        evidence['page_kind']='PHYSICAL_PAGE' if section['page'] is not None else 'UNPAGINATED_SECTION'
        row,column=evidence.get('row'),evidence.get('column')
        if row is not None or column is not None:
            table=section.get('table')
            if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (row,column)) or not table or row>=len(table) or column>=len(table[row]):raise ValueError()
            excerpt=str(table[row][column]);row_context=' | '.join(str(v) for v in table[row])[:1000]
            column_context=str(table[0][column]) if column<len(table[0]) else ''
        else:
            excerpt=label(evidence['excerpt'])
            if excerpt not in (section.get('text') or ''):raise ValueError()
            row_context=label(evidence['row_context']);column_context=label(evidence['column_context'])
        if not excerpt.strip():raise ValueError()
        fact['ownership']=label(evidence['ownership'])
        key=financial_fact_key(payload['issuer']['ticker'].upper(),fact)
        if key in seen_keys:raise ValueError('Duplicate financial context in stage')
        seen_keys.add(key);fact['financial_fact_key']=key
        structured=structured_context(fact.get('structured_context'),fact)
        if structured is not None:fact['structured_context']=structured
        raw_observations[fact['id']]={'id':'observation-'+identifier+'-'+str(index),'source_text':excerpt,
            'section_id':section['id'],'page':section['page'],'row':row,'column':column,'bbox':section.get('bbox'),
            'source_hash':extracted['source_hash'],'parser_version':extracted['parser_version'],
            'candidate_metric':fact['definition_id'],'proposed_value':fact['value'],'proposed_scale':fact['scale'],
            'correction_note':evidence['interpretation_note'],'structured_context':structured,'status':'UNREVIEWED_OBSERVATION'}
        # Retain the observation verbatim even when a reviewer proposes a corrected numeric interpretation.
        citations[fact['id']]={'section_id':section['id'],'page':section['page'],'table':label(evidence['table']),
            'tag':label(evidence['tag']),'row':row,'column':column,'excerpt':excerpt[:1000],
            'row_context':row_context,'column_context':column_context[:1000],'page_kind':evidence['page_kind'],'source_hash':extracted['source_hash'],
            'parser_version':extracted['parser_version'],'interpretation_note':label(evidence['interpretation_note']),
            'ownership':label(evidence['ownership']),'bbox':section.get('bbox'),'observation_id':raw_observations[fact['id']]['id'],'financial_fact_key':key}
    with finance.database(root) as db:
        initialize(db)
        # Validate canonical context and calendar using the same writer, then roll back all trial facts.
        db.execute('SAVEPOINT stage_validation')
        try:finance.ingest(root,payload,reviewer,now,connection=db)
        finally:
            db.execute('ROLLBACK TO stage_validation');db.execute('RELEASE stage_validation')
        record={'id':identifier,'document_id':document_id,'created_at':now.isoformat(),'created_by':reviewer,
            'parent_id':data.get('parent_id'),'status':'STAGED_NOT_ECONOMIC_FACTS','payload':payload,'citations':citations,'raw_observations':raw_observations,'adapter':'REVIEWED_SIDECAR_V1','warnings':warnings(payload['facts'])}
        if record['parent_id'] and not db.execute('SELECT 1 FROM finance_stages WHERE id=? AND document_id=?',(record['parent_id'],document_id)).fetchone():raise ValueError()
        db.execute('INSERT INTO finance_stages VALUES (?,?,?)',(identifier,document_id,json.dumps(record)))
    return {'version':1,'stage':record}


def history(root,document_id):
    with finance.database(root) as db:
        initialize(db)
        rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM finance_stages WHERE document_id=? ORDER BY rowid DESC',(document_id,))]
        for record in rows:
            decision=db.execute('SELECT payload FROM finance_stage_decisions WHERE stage_id=?',(record['id'],)).fetchone()
            record['decision']=json.loads(decision[0]) if decision else None
    return {'version':1,'stages':rows}


def decide(root,data,reviewer,now=None):
    now=now or datetime.now(timezone.utc)
    if data['decision'] not in ('ACCEPT','REJECT','AMBIGUOUS'):raise ValueError()
    note=label(data['note'])
    with finance.database(root) as db:
        initialize(db)
        row=db.execute('SELECT payload FROM finance_stages WHERE id=?',(data['stage_id'],)).fetchone()
        if not row:raise ValueError()
        record=json.loads(row[0])
        if db.execute('SELECT 1 FROM finance_stage_decisions WHERE stage_id=?',(record['id'],)).fetchone():raise ValueError()
        if data['decision']=='ACCEPT':
            keys={fact.get('financial_fact_key') for fact in record['payload']['facts'] if fact.get('financial_fact_key')}
            if any(json.loads(row[0]).get('financial_fact_key') in keys for row in db.execute('SELECT payload FROM facts')):raise ValueError('Context revision already accepted; create a new revision')
            current=observations(root,record['document_id'])
            if current['source_hash']!=next(iter(record['citations'].values()))['source_hash']:raise ValueError()
            if record['warnings'] and data.get('acknowledge_discrepancies') is not True:raise ValueError()
            finance.ingest(root,record['payload'],reviewer,now,connection=db)
            for fact_id,citation in record['citations'].items():db.execute('INSERT INTO finance_source_excerpts VALUES (?,?)',(fact_id,json.dumps(citation)))
        result={'id':secrets.token_hex(16),'stage_id':record['id'],'decision':data['decision'],'note':note,'reviewer':reviewer,
            'known_at':now.isoformat(),'fact_ids':list(record['citations']) if data['decision']=='ACCEPT' else []}
        db.execute('INSERT INTO finance_stage_decisions VALUES (?,?,?)',(result['id'],record['id'],json.dumps(result)))
    return {'version':1,'decision':result}
