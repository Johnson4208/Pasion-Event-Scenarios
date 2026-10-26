"""F06 completed-session diagnostics; causal heuristic events, never quantities."""
import hashlib
import json
import math
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import finance_core
import feasibility

VERSION='a08-v1'


def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def volume_state(value):
    return 'MISSING' if value is None else 'INVALID' if not finite(value) or value<0 else 'NO_TRADES' if value==0 else 'OBSERVED'


def result(value=None,reason=None,unit='number'):
    if value is not None and not math.isfinite(value):
        value=None;reason='INVALID_CALCULATION'
    return {'value':value,'status':'READY' if value is not None else 'UNAVAILABLE','reason_codes':[reason] if reason else [],'unit':unit,'calculation_version':VERSION}


def rvol(bars,index):
    if index<20:
        return result(reason='PRIOR_20_SESSIONS_REQUIRED',unit='x')
    values=[b['volume'] for b in bars[index-20:index+1]]
    states=[volume_state(v) for v in values]
    if 'INVALID' in states:
        return result(reason='INVALID_VOLUME',unit='x')
    if 'MISSING' in states:
        return result(reason='MISSING_VOLUME',unit='x')
    average=sum(values[:-1])/20
    if average==0:
        return result(reason='NO_PRIOR_TRADES',unit='x')
    return result(values[-1]/average,'NO_TRADES' if values[-1]==0 else None,'x')


def ema(values,period):
    if len(values)<period:
        return []
    output=[sum(values[:period])/period]
    for value in values[period:]:
        output.append(output[-1]+2/(period+1)*(value-output[-1]))
    return output


def smoothed(values,period):
    average=sum(values[:period])/period
    for value in values[period:]:
        average=(average*(period-1)+value)/period
    return average


def indicators(bars):
    closes=[b['close'] for b in bars]; n=len(bars)
    output={key:result(reason='INSUFFICIENT_COMPLETE_SESSIONS') for key in ('RSI14','MACD','MACD_signal','MACD_histogram','ATR14','RVOL20','OBV','CMF20','MFI14','SMA20','SMA60','SMA200','support20','resistance20')}
    if not n:return output
    latest=bars[-1];spread=latest['high']-latest['low']
    output['CLV']=result((latest['close']-latest['low'])/spread if spread else .5,unit='fraction')
    if n>=20:
        mean=sum(closes[-20:])/20;sd=(sum((v-mean)**2 for v in closes[-20:])/20)**.5
        output['Bollinger_upper20']=result(mean+2*sd,unit='quote_currency')
        output['Bollinger_lower20']=result(mean-2*sd,unit='quote_currency')
    else:
        output['Bollinger_upper20']=result(reason='PRIOR_20_CLOSES_REQUIRED');output['Bollinger_lower20']=result(reason='PRIOR_20_CLOSES_REQUIRED')
    for length in (60,):
        output['support'+str(length)]=result(min(b['low'] for b in bars[-length-1:-1]),unit='quote_currency') if n>length else result(reason='PRIOR_60_SESSIONS_REQUIRED')
        output['resistance'+str(length)]=result(max(b['high'] for b in bars[-length-1:-1]),unit='quote_currency') if n>length else result(reason='PRIOR_60_SESSIONS_REQUIRED')
    output['RVOL20']=rvol(bars,n-1)
    for period in (20,60,200):
        if n>=period:output['SMA'+str(period)]=result(sum(closes[-period:])/period,unit='quote_currency')
    if n>=21:
        output['support20']=result(min(b['low'] for b in bars[-21:-1]),unit='quote_currency')
        output['resistance20']=result(max(b['high'] for b in bars[-21:-1]),unit='quote_currency')
    if n>=15:
        changes=[b-a for a,b in zip(closes,closes[1:])]
        gain=smoothed([max(0,x) for x in changes],14); loss=smoothed([max(0,-x) for x in changes],14)
        output['RSI14']=result(50 if gain==loss==0 else 100 if loss==0 else 100-100/(1+gain/loss),unit='index')
        tr=[max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-closes[i-1]),abs(bars[i]['low']-closes[i-1])) for i in range(1,n)]
        output['ATR14']=result(smoothed(tr,14),unit='quote_currency')
    if n>=26:
        fast=ema(closes,12);slow=ema(closes,26)
        macd=[a-b for a,b in zip(fast[14:],slow)]
        output['MACD']=result(macd[-1],unit='quote_currency')
        signal=ema(macd,9)
        if signal:
            output['MACD_signal']=result(signal[-1],unit='quote_currency')
            output['MACD_histogram']=result(macd[-1]-signal[-1],unit='quote_currency')
    states=[volume_state(b['volume']) for b in bars]
    if all(s in ('OBSERVED','NO_TRADES') for s in states):
        obv=0
        for i in range(1,n):obv+=bars[i]['volume']*(1 if closes[i]>closes[i-1] else -1 if closes[i]<closes[i-1] else 0)
        output['OBV']=result(obv,unit='volume')
    else:output['OBV']=result(reason='MISSING_OR_INVALID_VOLUME')
    for length,name in ((20,'CMF20'),(15,'MFI14')):
        if n<length:continue
        sample=bars[-length:]
        if any(volume_state(b['volume']) not in ('OBSERVED','NO_TRADES') for b in sample):
            output[name]=result(reason='MISSING_OR_INVALID_VOLUME');continue
        if name=='CMF20':
            total=sum(b['volume'] for b in sample)
            flow=sum((0 if b['high']==b['low'] else (2*b['close']-b['low']-b['high'])/(b['high']-b['low']))*b['volume'] for b in sample)
            output[name]=result(flow/total if total else None,None if total else 'NO_MONEY_FLOW',unit='ratio')
        else:
            positive=negative=0
            typical=[(b['high']+b['low']+b['close'])/3 for b in sample]
            for i in range(1,len(sample)):
                amount=typical[i]*sample[i]['volume']
                if typical[i]>typical[i-1]:positive+=amount
                elif typical[i]<typical[i-1]:negative+=amount
            output[name]=result(50 if positive==negative==0 else 100 if negative==0 else 100-100/(1+positive/negative),'NO_MONEY_FLOW' if positive==negative==0 else None,'index')
    return output


def events(ticker,bars):
    found=[]
    for i in range(20,len(bars)):
        current=bars[i];prior=bars[i-20:i]; origin=finance_core.instant(current['known_at'])
        if any(finance_core.instant(b['known_at'])>origin for b in prior):continue
        rv=rvol(bars,i)
        if rv['status']!='READY' or volume_state(current['volume'])!='OBSERVED' or current.get('trading_status','TRADING')!='TRADING':continue
        support=min(b['low'] for b in prior);resistance=max(b['high'] for b in prior)
        spread=current['high']-current['low'];mean_spread=sum(b['high']-b['low'] for b in prior)/20
        close_location=(current['close']-current['low'])/spread if spread else .5
        spread_ratio=spread/mean_spread if mean_spread else None
        rules=[]
        if i>=21 and all(finance_core.instant(b['known_at'])<=origin for b in bars[i-21:i]):
            previous=bars[i-1];old_resistance=max(b['high'] for b in bars[i-21:i-1])
            if previous['close']>old_resistance and current['close']<old_resistance:
                rules.append(('FAILED_UP_BREAKOUT_OBSERVED','LATER_CLOSE_BELOW_PRE_BREAKOUT_RESISTANCE'))
        if current['low']<support and current['close']>support:rules.append(('SPRING_CANDIDATE','LOW_BREACH_CLOSE_ABOVE_PRIOR_SUPPORT'))
        if current['high']>resistance and current['close']<resistance:rules.append(('UPTHRUST_CANDIDATE','HIGH_BREACH_CLOSE_BELOW_PRIOR_RESISTANCE'))
        if rv['value']>=2 and spread_ratio is not None and spread_ratio>=1.5 and close_location<=.25 and current['close']<bars[i-1]['close']:
            rules.append(('SELLING_CLIMAX_CANDIDATE','HIGH_VOLUME_WIDE_DOWN_BAR'))
        if i>=199 and current['close']>resistance and rv['value']>=1.5 and current['close']>sum(b['close'] for b in bars[i-199:i+1])/200 and all(finance_core.instant(b['known_at'])<=origin for b in bars[i-199:i+1]):
            rules.append(('STRENGTH_CANDIDATE','BREAKOUT_WITH_VOLUME_AND_SMA200_CONTEXT'))
        for rule,reason in rules:
            inputs={'rvol':rv['value'],'spread_ratio':spread_ratio,'close_location':close_location,'prior_support':support,'prior_resistance':resistance}
            identity=hashlib.sha256(json.dumps([VERSION,ticker,current,prior,rule],sort_keys=True).encode()).hexdigest()[:24]
            found.append({'id':identity,'rule':rule,'bar_time':current['as_of'],'observed_at':current['known_at'],'bar_index':i,
                          'status':'TENTATIVE','reason_codes':[reason],'inputs':inputs,'context_start':prior[0]['as_of'],
                          'source_bar':dict(current),'caveat':'Causal heuristic candidate, not a calibrated probability or trade instruction.'})
        if i>20:
            parents=[e for e in found if e['bar_index']==i-1 and e['rule']=='SPRING_CANDIDATE']
            for parent in parents:
                if current['close']>bars[i-1]['high']:
                    found.append({'id':parent['id']+'-follow','parent_id':parent['id'],'rule':'SPRING_FOLLOW_THROUGH','bar_time':current['as_of'],
                                  'observed_at':current['known_at'],'bar_index':i,'status':'TENTATIVE','reason_codes':['LATER_SESSION_FOLLOW_THROUGH'],
                                  'inputs':{'close':current['close'],'prior_high':bars[i-1]['high']},'source_bar':dict(current),
                                  'caveat':'Later evidence is a separate event; the original candidate is not backdated or upgraded.'})
    return found


def database(root):
    db=sqlite3.connect(root/'technical.sqlite3');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,ticker TEXT,known_at TEXT,payload TEXT)')
    return db


def ingest(root,ticker,data,clock=None):
    clock=clock or datetime.now(timezone.utc)
    if data.get('provider_verified') is not True or data.get('adjustments_verified') is not True or data['adjustment_policy'] not in ('split_adjusted','total_return_adjusted','unadjusted_no_actions'):
        raise ValueError('Reviewed provider and corporate-action policy required.')
    for key in ('source','venue','calendar','currency','timezone'):
        if not isinstance(data[key],str) or not 0<len(data[key])<=160:raise ValueError('Instrument context required.')
    ZoneInfo(data['timezone'])
    bars=data['bars']
    if not isinstance(bars,list) or not 1<=len(bars)<=10000:raise ValueError('OHLCV history required.')
    previous=None
    for b in bars:
        stamp=finance_core.instant(b['as_of']);known=finance_core.instant(b['known_at'])
        if stamp>clock or known>clock or known<stamp or not isinstance(b['complete'],bool):raise ValueError('Invalid bar clocks.')
        if not isinstance(b['session_number'],int) or isinstance(b['session_number'],bool):raise ValueError('Invalid session.')
        if previous and (stamp<=previous[0] or b['session_number']!=previous[1]+1):raise ValueError('Missing exchange sessions.')
        if not all(finite(b[k]) and b[k]>0 for k in ('open','high','low','close')) or volume_state(b.get('volume'))=='INVALID':raise ValueError('Invalid OHLCV.')
        b['volume']=b.get('volume')
        state=b.get('trading_status','MISSING' if b['volume'] is None else 'NO_TRADE' if b['volume']==0 else 'TRADING')
        if state not in ('TRADING','NO_TRADE','HALTED','MISSING'):raise ValueError('Invalid trading state')
        if (state=='TRADING' and (b['volume'] is None or b['volume']<=0)) or (state in ('NO_TRADE','HALTED') and b['volume']!=0) or (state=='MISSING' and b['volume'] is not None):raise ValueError('Trading state and volume conflict')
        b['trading_status']=state
        if not b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:raise ValueError('Invalid bar ranges.')
        previous=(stamp,b['session_number'])
    payload={k:data[k] for k in ('source','venue','calendar','currency','timezone','adjustment_policy','bars')}
    payload.update(id=secrets.token_hex(16),ticker=ticker,known_at=clock.isoformat(),snapshot_hash=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest())
    db=database(root)
    try:
        with db:db.execute('INSERT INTO snapshots VALUES (?,?,?,?)',(payload['id'],ticker,payload['known_at'],json.dumps(payload)))
    finally:db.close()
    return {'id':payload['id'],'snapshot_hash':payload['snapshot_hash'],'known_at':payload['known_at'],'status':'ACCEPTED'}


def analyze(root,ticker,origin=None):
    clock=finance_core.instant(origin) if origin else datetime.now(timezone.utc)
    if clock>datetime.now(timezone.utc):raise ValueError('Future origin not permitted.')
    response={'version':1,'ticker':ticker,'status':'UNAVAILABLE','reason_codes':['NO_REVIEWED_OHLCV'],'bars':[],'events':[],
              'indicators':indicators([]),'phase':{'status':'UNAVAILABLE','value':None,'reason_codes':['NO_FORCED_PHASE_CLASSIFICATION']},
              'trap_radar':{'status':'UNAVAILABLE','probability':None,'reason_codes':['CAUSAL_OBSERVATIONS_ONLY']},
              'trade_idea':{**feasibility.withheld('VSA_DRAFT_AND_ACCOUNT_CHECK_REQUIRED'),'feasibility_endpoint':'/api/trades/feasibility'}}
    db=database(root)
    try:
        eligible=[r for r in db.execute('SELECT payload,known_at FROM snapshots WHERE ticker=? ORDER BY rowid DESC',(ticker,)) if finance_core.instant(r['known_at'])<=clock]
        if not eligible:return response
        snapshot=json.loads(eligible[0]['payload'])
    finally:db.close()
    bars=[b for b in snapshot['bars'] if b['complete'] and finance_core.instant(b['known_at'])<=clock and finance_core.instant(b['as_of'])<=clock]
    response.update(source=snapshot['source'],currency=snapshot['currency'],adjustment_policy=snapshot['adjustment_policy'],snapshot_hash=snapshot['snapshot_hash'],known_at=snapshot['known_at'])
    if not bars:return response
    if any(b['session_number']!=a['session_number']+1 for a,b in zip(bars,bars[1:])):
        response['reason_codes']=['INCOMPLETE_SESSION_HISTORY'];return response
    response.update(bars=bars,indicators=indicators(bars),events=events(ticker,bars),as_of=bars[-1]['as_of'],
                    status='READY',reason_codes=[],volume_state=volume_state(bars[-1]['volume']),coverage={'complete_sessions':len(bars),'submitted_sessions':len(snapshot['bars'])})
    if clock-finance_core.instant(bars[-1]['as_of'])>timedelta(hours=24):response.update(status='STALE',reason_codes=['COMPLETED_BAR_EXPIRED'])
    candidates=response['events']
    failures=[e for e in candidates if e['rule']=='FAILED_UP_BREAKOUT_OBSERVED']
    response['trap_radar']={'status':'READY' if failures else 'UNAVAILABLE','probability':None,'events':failures,'reason_codes':['LATER_OBSERVED_FAILURE_NOT_ORIGIN_LABEL','NOT_A_CALIBRATED_TRAP_RATE']}
    response['phase']={'status':'TENTATIVE' if candidates else 'UNAVAILABLE','value':None,'reason_codes':['EVENTS_DO_NOT_PROVE_A_FULL_WYCKOFF_PHASE']}
    return response
