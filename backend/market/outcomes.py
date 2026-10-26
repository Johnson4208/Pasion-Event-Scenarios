"""A10 retrospective first-touch scenarios; no calibrated target-hit model."""
from decimal import Decimal
import secrets

def first_touch(bars,origin_index,horizon,stop,target,direction='Long',fee_rate='0',fixed_fee='0',slippage_bps='0',quantity='1'):
    if direction not in ('Long','Short') or isinstance(origin_index,bool) or not isinstance(origin_index,int) or isinstance(horizon,bool) or not isinstance(horizon,int) or origin_index<0 or horizon<1:raise ValueError()
    if origin_index+horizon>=len(bars):return {'status':'UNAVAILABLE','reason_codes':['UNMATURED_HORIZON'],'net_pnl':None}
    path=bars[origin_index+1:origin_index+horizon+1]
    if bars[origin_index].get('complete') is not True:return {'status':'UNAVAILABLE','reason_codes':['ORIGIN_BAR_INCOMPLETE'],'net_pnl':None}
    if not all(b.get('complete') is True for b in path):return {'status':'UNAVAILABLE','reason_codes':['INCOMPLETE_FUTURE_SESSIONS'],'net_pnl':None}
    stop,target,rate,flat,slip,q=[Decimal(str(v)) for v in (stop,target,fee_rate,fixed_fee,slippage_bps,quantity)]
    if any(not v.is_finite() for v in (stop,target,rate,flat,slip,q)) or min(stop,target,q)<=0 or rate<0 or flat<0 or not 0<=slip<10000:raise ValueError()
    slip/=10000;entry=Decimal(str(path[0]['open']));long=direction=='Long'
    if not (stop<entry<target if long else target<entry<stop):return {'status':'WITHHELD','reason_codes':['NEXT_OPEN_OUTSIDE_PLANNED_STOP_TARGET'],'net_pnl':None}
    outcome='UNRESOLVED';exit_price=Decimal(str(path[-1]['close']));exit_index=origin_index+horizon
    for offset,b in enumerate(path,origin_index+1):
        opened,high,low=[Decimal(str(b[k])) for k in ('open','high','low')]
        if (opened<=stop if long else opened>=stop):outcome='STOP_GAP';exit_price=opened
        elif (opened>=target if long else opened<=target):outcome='TARGET';exit_price=target  # conservative improvement policy
        elif (low<=stop if long else high>=stop):outcome='STOP';exit_price=stop  # stop first if both touched
        elif (high>=target if long else low<=target):outcome='TARGET';exit_price=target
        else:continue
        exit_index=offset;break
    execution_entry=entry*(1+slip if long else 1-slip);execution_exit=exit_price*(1-slip if long else 1+slip)
    gross=q*(execution_exit-execution_entry)*(1 if long else -1)
    costs=flat*2+q*(execution_entry+execution_exit)*rate
    return {'version':1,'run_id':secrets.token_hex(16),'status':'RETROSPECTIVE_SCENARIO','outcome':outcome,'entry':str(entry),'exit':str(exit_price),'entry_bar':origin_index+1,'exit_bar':exit_index,
        'net_pnl':str(gross-costs),'fees':str(costs),'quantity':str(q),'origin_index':origin_index,'horizon_sessions':horizon,
        'entry_at':path[0].get('as_of'),'exit_at':bars[exit_index].get('as_of'),'stop_policy':'FIXED_PREDECLARED_SCENARIO_LEVELS',
        'policy':'NEXT_OPEN_GAP_AT_OPEN_COLLISION_STOP_FIRST_UNRESOLVED_HORIZON_CLOSE','cost_basis':'EXPLICIT_SCENARIO_ASSUMPTIONS_NOT_HISTORICAL_BROKER_FILLS','kelly_status':'WITHHELD'}

def summarize(paths):
    matured=[p for p in paths if p.get('status')=='RETROSPECTIVE_SCENARIO']
    wins=sum(p['outcome']=='TARGET' for p in matured);losses=sum(p['outcome'] in ('STOP','STOP_GAP') for p in matured);unresolved=len(matured)-wins-losses
    return {'wins':wins,'losses':losses,'unresolved':unresolved,'conditional_target_hit':wins/(wins+losses) if wins+losses else None,'unconditional_target_hit':wins/len(matured) if matured else None,
        'all_path_net_pnl':str(sum((Decimal(p['net_pnl']) for p in matured),Decimal(0))),'excluded_unmatured_or_invalid':len(paths)-len(matured),'probability_status':'DESCRIPTIVE_PATH_COUNTS_NOT_VALIDATED_EDGE'}
