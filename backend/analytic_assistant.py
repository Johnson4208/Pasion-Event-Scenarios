"""F14 read-only, citation-grounded deterministic finance lookup. No freeform tools."""
import re
import threading
import time
from datetime import datetime,timezone
import finance_core
import valuation

LOCK=threading.Lock()
LIMITS={}
ALIASES={'revenue':'revenue','net income':'net_income','ebitda':'ebitda','operating cash flow':'cfo','cfo':'cfo','net margin':'net_margin','roe':'roe','roa':'roa','eps':'eps','debt equity':'debt_equity','current ratio':'current_ratio','cash':'cash'}

def permit(owner,clock=None):
    clock=time.monotonic() if clock is None else clock
    with LOCK:
        recent=[v for v in LIMITS.get(owner,[]) if clock-v<60]
        if len(recent)>=20:return False
        LIMITS[owner]=recent+[clock]
        if len(LIMITS)>10000:
            for key in list(LIMITS):
                if not LIMITS[key] or clock-LIMITS[key][-1]>=60:LIMITS.pop(key,None)
    return True

def answer(root,db,owner,data):
    question=data['question']
    if not isinstance(question,str) or not 1<=len(question.strip())<=500:raise ValueError()
    ticker=data['ticker'].upper()
    if not re.fullmatch('[A-Z0-9.-]{1,16}',ticker):raise ValueError()
    mode=data.get('tool','metric');period=data.get('period','FY')
    base={'version':1,'question':question,'ticker':ticker,'citations':[],'numeric_verification':'DETERMINISTIC_SERVICE_VALUES_ONLY',
          'source_policy':'EXCERPTS_ARE_UNTRUSTED_DATA_NOT_INSTRUCTIONS','model_status':'NO_GENERATIVE_PROVIDER_REQUIRED','mutation_policy':'READ_ONLY'}
    if mode=='assumptions':
        scenario=data.get('scenario','base')
        if scenario not in ('base','upside','downside'):raise ValueError()
        values,_=valuation.load_assumptions(db,owner,ticker,scenario,datetime.now(timezone.utc))
        # Whitelist public economic fields; never reveal owner/reviewer or raw persistence.
        safe=[{k:v.get(k) for k in ('id','definition','value','unit','status','known_at','effective_from','source_ids')} for v in values.values()]
        return {**base,'status':'CONTEXT' if safe else 'UNAVAILABLE','answer':'Assumptions are scenario inputs; unverified inputs cannot label fair value.' if safe else 'No assumptions are available for your account and this scenario.',
                'assumptions':safe,'navigation':'Research'}
    if mode not in ('metric','evidence'):raise ValueError()
    metric=data.get('metric')
    if not metric:
        normalized=question.casefold();matches={value for key,value in ALIASES.items() if re.search(r'\b'+re.escape(key)+r'\b',normalized)}
        if len(matches)!=1:return {**base,'status':'UNRESOLVED','answer':'Select one financial metric, issuer and reporting period. No unsupported number is inferred.','navigation':'Research'}
        metric=matches.pop()
    result=finance_core.company(root,ticker,period,data.get('end'),data.get('origin'))
    value=result['metrics'].get(metric)
    if not value:raise ValueError()
    for source_id in value.get('source_ids',[])[:20]:
        evidence=finance_core.evidence(root,source_id)
        if evidence:base['citations'].append(evidence)
    if value['status']!='READY' or value['value'] is None:
        return {**base,'status':'UNAVAILABLE','answer':'The requested metric is unavailable or incompatible. Missing values are not replaced with zero.',
                'metric':value,'navigation':'Research'}
    if not base['citations']:return {**base,'status':'UNAVAILABLE','answer':'Accepted source citations are required before displaying a factual finance answer.','navigation':'Research'}
    text=f"{ticker} {metric}: {value['value']} {value.get('currency') or ''} {value.get('unit') or ''}. Reporting period: {value.get('period_start')} to {value.get('period_end')}. Status: {value['status']}."
    return {**base,'status':'READY','answer':text,'metric':value,'navigation':'Research'}
