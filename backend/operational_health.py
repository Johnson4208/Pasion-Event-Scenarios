"""F16 isolated read-only quality probes and sanitized request traces."""
import json
import sqlite3
from datetime import datetime,timezone
from contextlib import closing
import market_summary
import finance_core
import stock_models
import release_governance

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS request_traces(id TEXT PRIMARY KEY,occurred_at TEXT NOT NULL,route_group TEXT NOT NULL,http_status INTEGER NOT NULL,error_code TEXT,contract_version TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS health_runs(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')

def trace(db,identifier,path,status,error_code=None):
    initialize(db)
    # Never log body, query, owner, raw paths, tokens or credentials.
    group='admin' if path.startswith('/api/admin/') else 'research' if path.startswith('/api/research/') else 'market' if path.startswith('/api/market/') else 'account'
    error_code=error_code or ({400:'INVALID_REQUEST',401:'AUTHENTICATION_REQUIRED',403:'ACCESS_DENIED',409:'CONFLICT',429:'RATE_LIMITED'}.get(status,'SERVICE_FAILURE') if status>=400 else None)
    db.execute('INSERT INTO request_traces VALUES (?,?,?,?,?,?)',(identifier,datetime.now(timezone.utc).isoformat(),group,status,error_code,'f16-v1'))
    db.execute('DELETE FROM request_traces WHERE id IN (SELECT id FROM request_traces ORDER BY rowid DESC LIMIT -1 OFFSET 10000)')

def probe(name,fn):
    try:return {'subsystem':name,**fn()}
    except (sqlite3.Error,OSError,ValueError,TypeError,KeyError,ArithmeticError):return {'subsystem':name,'status':'UNAVAILABLE','reason_codes':['SUBSYSTEM_PROBE_FAILED']}

def archive(db,report):
    initialize(db)
    db.execute('INSERT INTO health_runs VALUES (?,?)',(report['run_id'],json.dumps(report)))
    return report

def stored(root,filename,table):
    path=root/filename
    if not path.exists():return []
    with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)) as db:
        if not db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone():return []
        return [json.loads(r[0]) for r in db.execute('SELECT payload FROM '+table+' LIMIT 1000')]

def report(root,now=None):
    now=now or datetime.now(timezone.utc)
    def provider():
        data=market_summary.summary('provider',now=now)
        return {'status':data['status'],'reason_codes':[data['reason']] if data.get('reason') else [],'calculation_version':'f02-v1','quotes':[{k:q.get(k) for k in ('ticker','status','reason','as_of')} for q in data.get('quotes',[])]}
    def finance():
        facts=stored(root,'finance.sqlite3','facts');tickers=sorted({f['ticker'] for f in facts})[:20]
        checks=[]
        for ticker in tickers:
            result=finance_core.company(root,ticker,'TTM')
            checks.append({'ticker':ticker,'period':'TTM','status':result['status'],'unavailable_metrics':sum(m['status']!='READY' for m in result['metrics'].values())})
        return {'status':'PARTIAL' if facts else 'UNAVAILABLE','reason_codes':['METRIC_PERIOD_COVERAGE_IS_INDIVIDUAL'] if facts else ['NO_ACCEPTED_FINANCIAL_FACTS'],'accepted_fact_count':len(facts),'period_checks':checks,'calculation_version':finance_core.VERSION}
    def models():
        items=stored(root,'stock_models.sqlite3','models');tickers=sorted({m['ticker'] for m in items})[:20]
        results=[stock_models.analysis(root,ticker,now) for ticker in tickers]
        return {'status':'PARTIAL' if items else 'UNAVAILABLE','reason_codes':['PER_HORIZON_RELIABILITY_GATES'] if items else ['NO_FROZEN_MODELS'],'model_policy':stock_models.POLICY,'models':[{k:m.get(k) for k in ('id','ticker','frozen_at','expires_at')} for m in items],
            'horizon_health':[{'ticker':r['ticker'],'horizons':[{k:h.get(k) for k in ('status','reason','model_id','horizon_sessions','model_expires_at','prediction_expires_at')} for h in r['horizons']]} for r in results]}
    def documents():
        path=root/'documents.sqlite3'
        if not path.exists():return {'status':'UNAVAILABLE','reason_codes':['NO_DOCUMENT_JOBS']}
        with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)) as db:items=[json.loads(r[0]) for r in db.execute('SELECT content FROM documents LIMIT 1000')]
        counts={k:sum(i.get('status')==k for i in items) for k in ('ready','processing','failed')}
        return {'status':'PARTIAL' if counts['failed'] or counts['processing'] else 'READY','reason_codes':['DOCUMENT_JOBS_REQUIRE_ATTENTION'] if counts['failed'] else [],'job_counts':counts}
    def evidence():
        vintages=stored(root,'macro.sqlite3','vintages');stale=sum(finance_core.instant(v['expires_at'])<=now for v in vintages)
        return {'status':'PARTIAL' if vintages else 'UNAVAILABLE','reason_codes':['STALE_RELEASE_VINTAGES'] if stale else ['NO_MACRO_VINTAGES'] if not vintages else [],'vintage_count':len(vintages),'expired_vintage_count':stale}
    def shadow():
        pools=stored(root,'accounts.sqlite3','distribution_pools');candidates=stored(root,'accounts.sqlite3','distribution_candidates')
        return {'status':'REVIEW_ONLY','reason_codes':['OPERATIONAL_ALLOCATION_RELEASE_WITHHELD'],'pool_count':len(pools),'candidate_gate_counts':{k:sum(c['status']==k for c in candidates) for k in ('WITHHELD','REVIEW_ONLY')},'calculation_version':'f15-shadow-v1'}
    systems=[probe(name,fn) for name,fn in [('provider',provider),('financial_periods',finance),('market_models',models),('document_jobs',documents),('evidence_vintages',evidence),('distribution_feasibility',shadow)]]
    traces=[]
    path=root/'accounts.sqlite3'
    if path.exists():
        try:
            with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='request_traces'").fetchone():
                    traces=[dict(zip(('trace_id','occurred_at','route_group','http_status','error_code','contract_version'),r)) for r in db.execute('SELECT * FROM request_traces ORDER BY rowid DESC LIMIT 50')]
        except (sqlite3.Error,OSError):pass
    return {'version':1,'release_manifest':release_governance.manifest(root,now),'run_id':__import__('secrets').token_hex(16),'checked_at':now.isoformat(),'status':'PARTIAL' if any(s['status']!='READY' for s in systems) else 'READY','subsystems':systems,
        'release_gate':'PRODUCTION_IDENTITY_STORAGE_AND_REAL_PROVIDER_VALIDATION_REQUIRED','recent_request_traces':traces,'policy':'ISOLATED_SUBSYSTEM_GATES_NO_GLOBAL_RESEARCH_DISABLE','calculation_versions':{'finance':finance_core.VERSION,'models':stock_models.POLICY,'health':'f16-v1'}}
