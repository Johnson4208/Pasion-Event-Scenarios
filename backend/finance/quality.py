"""A05 financial relationship diagnostics, never fraud or investment probabilities."""
from decimal import Decimal

CONTEXT=('currency','scope','ownership','accounting_basis','restatement_basis')
def compatible(a,b):return all(a.get(k) is not None and a.get(k) != '' and a.get(k)==b.get(k) for k in CONTEXT)

def diagnostic(name,inputs,calculate,unit='x',same_period=True):
    base={'definition_id':name,'value':None,'unit':unit,'status':'UNAVAILABLE','reason_codes':[],
        'input_ids':[i.get('id') for i in inputs if i], 'source_ids':list(dict.fromkeys(s for i in inputs if i for s in i.get('source_ids',[]))),
        'calculation_version':'a05-v1','interpretation':'RELATIONSHIP_SCREEN_NOT_FRAUD_PROBABILITY',
        'inputs':[{k:i.get(k) for k in ('definition_id','value','unit','currency','period_start','period_end','period_type','scope','accounting_basis','known_at','status')} for i in inputs if i]}
    if not inputs or any(not i or i.get('status')!='READY' or i.get('value') is None for i in inputs):base['reason_codes']=['MISSING_ELIGIBLE_INPUTS'];return base
    if any(not compatible(inputs[0],i) for i in inputs):base['reason_codes']=['MISSING_OR_INCOMPATIBLE_ACCOUNTING_CONTEXT'];return base
    if same_period and any((i.get('period_start'),i.get('period_end'),i.get('period_type'))!=(inputs[0].get('period_start'),inputs[0].get('period_end'),inputs[0].get('period_type')) for i in inputs[1:]):base['reason_codes']=['INCOMPATIBLE_DURATION'];return base
    try:
        value=calculate([Decimal(i['value']) for i in inputs])
        if not value.is_finite():raise ValueError()
    except (ArithmeticError,ValueError):base['reason_codes']=['ZERO_NEGATIVE_OR_INVALID_DENOMINATOR'];return base
    from common.time import derived_known_at
    base.update(value=str(value),status='READY',known_at=derived_known_at(i['known_at'] for i in inputs),reason_codes=[])
    return base

def positive_ratio(a,b):
    if b<=0:raise ValueError()
    return a/b

def peer_reference(target,peers):
    required=('sector','market','accounting_basis','period_type','period_start','period_end','definition_id','calculation_version','unit','currency')
    if any(target.get(k) is None for k in required):return {'status':'UNAVAILABLE','reason_codes':['INCOMPLETE_PEER_CONTEXT'],'eligible_count':0}
    eligible=[p for p in peers if p.get('status')=='READY' and p.get('value') is not None and p.get('source_ids') and all(p.get(k)==target[k] for k in required)]
    if not eligible:return {'status':'UNAVAILABLE','reason_codes':['NO_MATCHED_REVIEWED_REFERENCE_GROUP'],'eligible_count':0}
    values=sorted(Decimal(p['value']) for p in eligible)
    if any(not v.is_finite() for v in values):raise ValueError('Invalid peer value')
    mid=len(values)//2;median=values[mid] if len(values)%2 else (values[mid-1]+values[mid])/2
    return {'status':'READY','reference_median':str(median),'eligible_count':len(values),'source_ids':list(dict.fromkeys(s for p in eligible for s in p['source_ids'])),'policy':'COMPARISON_CONTEXT_NOT_ANOMALY_VERDICT'}

def screen(metrics,prior):
    get=lambda k:metrics.get(k)
    results=[]
    results.append(diagnostic('revenue_growth',[get('revenue'),prior.get('revenue')],lambda v:positive_ratio(v[0],v[1])-1,same_period=False))
    if results[-1]['status']=='READY' and get('revenue')['period_type']!=prior['revenue']['period_type']:
        results[-1].update(status='UNAVAILABLE',value=None,reason_codes=['INCOMPATIBLE_PRIOR_PERIOD_BASIS'])
    results.append(diagnostic('cfo_conversion',[get('cfo'),get('net_income')],lambda v:positive_ratio(v[0],v[1])))
    ni,cfo,assets=get('net_income'),get('cfo'),get('assets')
    flow_ok=ni and cfo and (ni.get('period_start'),ni.get('period_end'),ni.get('period_type'))==(cfo.get('period_start'),cfo.get('period_end'),cfo.get('period_type'))
    accrual=diagnostic('accrual_proxy',[ni,cfo,assets],lambda v:positive_ratio(v[0]-v[1],v[2]),same_period=False)
    if accrual['status']=='READY' and (not flow_ok or assets.get('period_end')!=ni.get('period_end')):accrual.update(status='UNAVAILABLE',value=None,reason_codes=['ASSET_ASOF_OR_FLOW_DURATION_MISMATCH'])
    results.append(accrual)
    results.append(diagnostic('margin_change_pp',[get('net_margin'),prior.get('net_margin')],lambda v:v[0]-v[1],unit='percentage_points',same_period=False))
    results.append(diagnostic('working_capital_growth',[get('working_capital'),prior.get('working_capital')],lambda v:positive_ratio(v[0],v[1])-1,same_period=False))
    def dividend_buffer(v):
        if v[1]<0 or v[2]<0:raise ValueError()
        return v[0]-v[1]-v[2]
    results.append(diagnostic('cash_after_capex_and_dividends',[get('cfo'),get('capex'),get('dividends')],dividend_buffer,unit='currency'))
    flags=[]
    conversion=next(r for r in results if r['definition_id']=='cfo_conversion')
    if conversion['status']=='READY' and Decimal(conversion['value'])<0:flags.append({'code':'POSITIVE_INCOME_NEGATIVE_OPERATING_CASH','source_ids':conversion['source_ids'],'diagnostic':'cfo_conversion','interpretation':'Review earnings/cash timing and evidence; not a fraud conclusion'})
    affordability=results[-1]
    if affordability['status']=='READY' and Decimal(affordability['value'])<0:flags.append({'code':'DIVIDENDS_EXCEED_SELECTED_PERIOD_CASH_AFTER_CAPEX','source_ids':affordability['source_ids'],'diagnostic':affordability['definition_id'],'interpretation':'Review funding, timing and balance-sheet context'})
    return {'version':1,'diagnostics':results,'flags':flags,'coverage':{'eligible':sum(r['status']=='READY' for r in results),'total':len(results)},
        'beneish':{'status':'UNAVAILABLE','reason_codes':['INCOMPLETE_REGISTERED_BENEISH_COMPONENTS'],'missing_components':['DSRI','GMI','AQI','SGI','DEPI','SGAI','LVGI','TATA'],'value':None,'probability':None},
        'peers':{'status':'UNAVAILABLE','reason_codes':['REVIEWED_SECTOR_MARKET_AND_DEFINITION_REFERENCE_GROUP_REQUIRED']},
        'health_heuristic':{'status':'UNAVAILABLE','value':None,'reason_codes':['REVIEWED_COMPONENT_NORMALIZATION_POLICY_REQUIRED'],'label':'Research heuristic only'},
        'fraud_probability':None,'policy':'MISSING_IS_NOT_ZERO_PENALTY_NO_UNIVERSAL_MARGIN_THRESHOLD'}
