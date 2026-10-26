"""A01 canonical typed results. Status is explicit; Decimal values retain exact text."""
import hashlib
import json
from datetime import datetime,timezone
from decimal import Decimal, getcontext
from typing import TypedDict, Literal, NotRequired

Status=Literal['READY','UNAVAILABLE','STALE','WITHHELD','ERROR','UNCERTAIN']
Semantic=Literal['ACTUAL','DERIVED','PROXY','ASSUMPTION','FORECAST']
class EconomicResult(TypedDict):
    id:str
    object_type:Literal['CanonicalFact','DerivedMetric','ModelOutput','DecisionEligibility']
    value:str|None
    unit:str|None
    status:Status
    definition_id:str
    period_start:str|None
    period_end:str|None
    as_of:str|None
    known_at:str|None
    source_ids:list[str]
    calculation_version:str
    reason_codes:list[str]
    origin:Semantic
    input_ids:list[str]
    exact_scale:str
    rounding_policy:str
    assumption_ids:NotRequired[list[str]]
    model_version:NotRequired[str|None]
    eligibility:NotRequired[dict]

def instant(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Offset clock required')
    return result.astimezone(timezone.utc)

def decimal_text(value):
    if value is None:return None
    if isinstance(value,bool):raise ValueError('Boolean is not a numeric fact')
    amount=Decimal(str(value))
    if not amount.is_finite():raise ValueError('Invalid nonfinite numeric result')
    return str(amount)

def compatible(a,b,*,same_definition=True):
    keys=('currency','accounting_basis','scope','restatement_basis','period_type','period_start','period_end','unit')
    if same_definition:keys+=('definition_id',)
    return all(a.get(k) is not None and a.get(k)==b.get(k) for k in keys)

def envelope(record,inputs=(),object_type=None):
    result=dict(record)
    if result.get('status') not in ('READY','UNAVAILABLE','STALE','WITHHELD','ERROR','UNCERTAIN'):raise ValueError('Explicit status required')
    if result.get('origin') not in ('ACTUAL','DERIVED','PROXY','ASSUMPTION','FORECAST'):raise ValueError('Explicit economic semantics required')
    result['value']=decimal_text(result.get('value'))
    if result['status']=='READY' and result['value'] is None:raise ValueError('Ready cannot lack a value')
    if not result.get('definition_id') or not result.get('calculation_version'):raise ValueError('Definition and calculation version required')
    result.setdefault('period_start',None);result.setdefault('period_end',None)
    result.setdefault('as_of',result['period_end']);result.setdefault('known_at',None)
    result.setdefault('source_ids',[]);result.setdefault('reason_codes',[]);result.setdefault('unit',None)
    result['exact_scale']=decimal_text(result.get('scale','1'))
    if result['exact_scale'] is None or Decimal(result['exact_scale'])<=0:raise ValueError('Positive exact scale required')
    result['rounding_policy']=f'DECIMAL_PRECISION_{getcontext().prec}_{getcontext().rounding}_NO_ADDITIONAL_QUANTIZATION'
    result['object_type']=object_type or ('CanonicalFact' if result['origin']=='ACTUAL' else 'DerivedMetric')
    if result['object_type'] not in ('CanonicalFact','DerivedMetric','ModelOutput','DecisionEligibility'):raise ValueError()
    if inputs:
        known=[i['known_at'] for i in inputs if i.get('known_at')]
        if len(known)!=len(inputs):raise ValueError('Every input requires known_at')
        result['known_at']=max(known,key=instant)
        result['input_ids']=[i['id'] for i in inputs]
        result['source_ids']=list(dict.fromkeys(s for i in inputs for s in i.get('source_ids',[])))
    else:result.setdefault('input_ids',list(result['source_ids']) if result['origin']=='DERIVED' else [])
    if result['known_at'] is not None:instant(result['known_at'])
    if result['status']=='READY' and not result['source_ids']:raise ValueError('Ready economic result requires source lineage')
    result.setdefault('id','result-'+hashlib.sha256(json.dumps({k:v for k,v in result.items() if k!='id'},sort_keys=True,separators=(',',':')).encode()).hexdigest()[:32])
    result['contract_version']='a01-v1'
    return result
