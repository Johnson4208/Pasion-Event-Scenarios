"""F08 private manual lot snapshots. Observations are never orders or fills."""
import json
import math
import re
import secrets
from datetime import datetime,timezone
from decimal import Decimal
import feasibility
import finance_core
import technical


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS portfolio_transactions(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES accounts(email),request_id TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(owner,request_id))')
    db.execute('CREATE TABLE IF NOT EXISTS portfolio_states(owner TEXT PRIMARY KEY REFERENCES accounts(email) ON DELETE CASCADE,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS portfolio_events(id TEXT PRIMARY KEY,owner TEXT REFERENCES accounts(email) ON DELETE CASCADE,revision INTEGER NOT NULL,known_at TEXT NOT NULL,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS portfolio_fx(pair TEXT PRIMARY KEY,payload TEXT NOT NULL)')


def transaction(db,owner,data):
    initialize(db)
    if not db.execute('SELECT 1 FROM portfolio_states WHERE owner=?',(owner,)).fetchone():raise ValueError('Confirm opening manual account first')
    if data['type'] not in ('BUY','SELL','DEPOSIT','WITHDRAWAL','DIVIDEND','SPLIT','FEE','TAX','FX','CORRECTION'):raise ValueError()
    request_id=data['request_id']
    if not isinstance(request_id,str) or not 1<=len(request_id)<=120:raise ValueError()
    stamp=finance_core.instant(data['occurred_at']);now=datetime.now(timezone.utc)
    if stamp>now:raise ValueError()
    record={'type':data['type'],'currency':currency(data['currency']),'occurred_at':stamp.isoformat(),
        'amount':amount(data['amount']),'quantity':amount(data.get('quantity')),'ticker':data.get('ticker') or None,
        'fees':amount(data.get('fees','0')),'taxes':amount(data.get('taxes','0')),'source_note':data['source_note']}
    if record['amount'] is None or not isinstance(record['source_note'],str) or not 1<=len(record['source_note'])<=200:raise ValueError()
    if record['type'] in ('BUY','SELL','SPLIT') and (not record['ticker'] or not re.fullmatch('[A-Z0-9.-]{1,16}',record['ticker']) or record['quantity'] is None or Decimal(record['quantity'])<=0):raise ValueError()
    existing=db.execute('SELECT payload FROM portfolio_transactions WHERE owner=? AND request_id=?',(owner,request_id)).fetchone()
    if existing:
        old=json.loads(existing[0])
        if any(old.get(k)!=v for k,v in record.items()):raise ValueError('Retry payload changed')
        return old
    record.update(id=secrets.token_hex(16),known_at=now.isoformat(),status='MANUAL_UNRECONCILED',balance_policy='NO_AUTOMATIC_CASH_OR_HOLDINGS_CHANGE',execution_policy='NOT_A_BROKER_ORDER_OR_FILL')
    db.execute('INSERT INTO portfolio_transactions VALUES (?,?,?,?)',(record['id'],owner,request_id,json.dumps(record)))
    feasibility.initialize(db)
    row=db.execute('SELECT payload FROM trading_accounts WHERE owner=?',(owner,)).fetchone()
    if row:
        baseline=json.loads(row[0]);baseline['status']='MANUAL_UNVERIFIED';db.execute('UPDATE trading_accounts SET payload=? WHERE owner=?',(json.dumps(baseline),owner))
    return record

def amount(value):
    if value is None or value=='':return None
    result=feasibility.decimal(value)
    if result<0:raise ValueError('Negative balance or cost')
    return str(result)


def currency(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Z]{3}',value):raise ValueError('Invalid currency')
    return value


def save(db,owner,data):
    initialize(db)
    row=db.execute('SELECT revision,payload FROM portfolio_states WHERE owner=?',(owner,)).fetchone()
    revision=row[0] if row else 0
    if type(data['expected_revision']) is not int:raise ValueError('Integer revision required')
    if data['expected_revision']!=revision:raise RuntimeError('Portfolio revision changed; refresh before saving.')
    state={'currency':currency(data['currency']),'cash':amount(data['cash']),'reserved_cash':amount(data['reserved_cash']),
           'as_of':finance_core.instant(data['as_of']).isoformat(),'source':data.get('source','MANUAL'),'lots':[],'targets':[],'watchlist':[]}
    if finance_core.instant(state['as_of'])>datetime.now(timezone.utc):raise ValueError('Future account snapshot')
    if state['source'] not in ('MANUAL_CONFIRMED','IMPORTED_UNVERIFIED'):raise ValueError('Explicit confirmation/source required')
    if state['cash'] is not None and state['reserved_cash'] is not None and Decimal(state['reserved_cash'])>Decimal(state['cash']):raise ValueError('Reservations exceed cash')
    for lot in data['lots']:
        if not re.fullmatch('[A-Z0-9.-]{1,16}',lot['ticker']):raise ValueError('Invalid ticker')
        quantity=amount(lot['quantity']);cost=amount(lot['unit_cost'])
        if quantity is None or Decimal(quantity)<=0:raise ValueError('Positive holding quantity required')
        sector=lot.get('sector','Unknown')
        if not isinstance(sector,str) or not 0<len(sector)<=100:raise ValueError('Invalid sector')
        identity=lot.get('id') or secrets.token_hex(16)
        if not isinstance(identity,str) or not 1<=len(identity)<=100:raise ValueError('Invalid lot identity')
        state['lots'].append({'id':identity,'ticker':lot['ticker'],'quantity':quantity,'unit_cost':cost,'currency':currency(lot['currency']),
                              'sector':sector,'source':state['source'],'as_of':state['as_of']})
    if len(state['lots'])>500 or len({lot['id'] for lot in state['lots']})!=len(state['lots']):raise ValueError('Invalid lot collection')
    for ticker in data.get('watchlist',[]):
        if not isinstance(ticker,str) or not re.fullmatch('[A-Z0-9.-]{1,16}',ticker):raise ValueError('Invalid watchlist symbol')
        if ticker not in state['watchlist']:state['watchlist'].append(ticker)
    for target in data.get('targets',[]):
        if not re.fullmatch('[A-Z0-9.-]{1,16}',target['ticker']):raise ValueError('Invalid target symbol')
        price=amount(target['price'])
        if price is None or Decimal(price)<=0:raise ValueError('Positive alert price required')
        state['targets'].append({'ticker':target['ticker'],'price':price,'currency':currency(target['currency']),'status':'WATCHING_UNVERIFIED','source':state['source']})
    if len(state['watchlist'])>500 or len(state['targets'])>500:raise ValueError('Portfolio watch/alert capacity exceeded')
    revision+=1
    state.update(revision=revision,known_at=datetime.now(timezone.utc).isoformat())
    if row:
        updated=db.execute('UPDATE portfolio_states SET revision=?,payload=? WHERE owner=? AND revision=?',(revision,json.dumps(state),owner,revision-1))
        if updated.rowcount!=1:raise RuntimeError('Portfolio revision changed; refresh before saving.')
    else:db.execute('INSERT INTO portfolio_states VALUES (?,?,?)',(owner,revision,json.dumps(state)))
    db.execute('INSERT INTO portfolio_events VALUES (?,?,?,?,?)',(secrets.token_hex(16),owner,revision,state['known_at'],json.dumps({'type':'MANUAL_SNAPSHOT','state':state,'order_status':'NO_EXECUTION_EVENT'})))
    # Editing observations invalidates previously reviewed trading state; never infer reserves/equity.
    feasibility.initialize(db)
    existing=db.execute('SELECT payload FROM trading_accounts WHERE owner=?',(owner,)).fetchone()
    if existing:
        baseline=json.loads(existing[0]);baseline.update(status='MANUAL_UNVERIFIED',equity=None,cash=state['cash'],reserved_cash=state['reserved_cash'],
            currency=state['currency'],sellable={},source='Portfolio state changed; submit a new equity/cash/sellability reconciliation')
        db.execute('UPDATE trading_accounts SET payload=? WHERE owner=?',(json.dumps(baseline),owner))
    return state


def register_fx(db,data):
    initialize(db)
    source=currency(data['from']);target=currency(data['to']);rate=feasibility.decimal(data['rate'])
    if rate<=0 or data.get('reviewed') is not True or not isinstance(data['source'],str) or not data['source'].strip():raise ValueError('Reviewed FX source required')
    finance_core.instant(data['as_of']);finance_core.instant(data['expires_at'])
    record={k:data[k] for k in ('from','to','as_of','expires_at','source')};record['rate']=str(rate)
    db.execute('INSERT INTO portfolio_fx VALUES (?,?) ON CONFLICT(pair) DO UPDATE SET payload=excluded.payload',(source+'/'+target,json.dumps(record)))
    return {'status':'REVIEWED','pair':source+'/'+target}


def fx(db,source,target,clock):
    if source==target:return Decimal(1)
    row=db.execute('SELECT payload FROM portfolio_fx WHERE pair=?',(source+'/'+target,)).fetchone()
    if not row:return None
    rate=json.loads(row[0])
    if not finance_core.instant(rate['as_of'])<=clock<finance_core.instant(rate['expires_at']):return None
    return Decimal(rate['rate'])


def mark(db,ticker,clock):
    row=db.execute('SELECT payload FROM trading_instruments WHERE ticker=?',(ticker,)).fetchone()
    if not row:return None
    instrument=json.loads(row[0]);quote=instrument['quote'];as_of=finance_core.instant(quote['as_of'])
    if as_of>clock or (clock-as_of).total_seconds()>float(quote['max_age_seconds']):return None
    if not finance_core.instant(quote['session_open'])<=as_of<=finance_core.instant(quote['session_close']):return None
    return {'value':Decimal(str(quote['price'])),'currency':instrument['currency'],'as_of':quote['as_of'],'source':instrument['source']}


def contributions(weights,returns):
    if not weights or set(weights)!=set(returns):return {'status':'UNAVAILABLE','reason':'INCOMPLETE_RETURN_COVERAGE'}
    if any(not math.isfinite(v) or v<0 for v in weights.values()) or sum(weights.values())>1+1e-8:return {'status':'UNAVAILABLE','reason':'INVALID_COMPLETE_WEIGHTS'}
    if any(len(v)<60 for v in returns.values()) or len({len(v) for v in returns.values()})!=1:return {'status':'UNAVAILABLE','reason':'60_ALIGNED_RETURNS_REQUIRED'}
    if not all(math.isfinite(v) for values in returns.values() for v in values):return {'status':'UNAVAILABLE','reason':'INVALID_RETURNS'}
    keys=list(weights);n=len(returns[keys[0]]);means={k:sum(returns[k])/n for k in keys}
    covariance=[[sum((a-means[x])*(b-means[y]) for a,b in zip(returns[x],returns[y]))/(n-1) for y in keys] for x in keys]
    diagonal=sum(covariance[i][i] for i in range(len(keys)))/len(keys)
    shrunk=[[.5*covariance[i][j]+(.5*diagonal if i==j else 0) for j in range(len(keys))] for i in range(len(keys))]
    marginal=[sum(shrunk[i][j]*weights[keys[j]] for j in range(len(keys))) for i in range(len(keys))]
    variance=sum(weights[k]*marginal[i] for i,k in enumerate(keys))
    if not math.isfinite(variance) or variance<=0:return {'status':'UNAVAILABLE','reason':'INVALID_OR_ZERO_VARIANCE'}
    volatility=math.sqrt(variance)
    return {'status':'READY','daily_volatility':volatility,'shrinkage':.5,'covariance_target':'TRACE_OVER_DIMENSION_TIMES_IDENTITY','sample_count':n,'risk_basis':'CURRENT_WEIGHTS_HISTORICAL_RETURN_SCENARIO_NOT_ACTUAL_ACCOUNT_PERFORMANCE','basis':'Aligned same-currency completed-session returns',
            'components':{k:weights[k]*marginal[i]/volatility for i,k in enumerate(keys)}}


def snapshot(db,root,owner):
    initialize(db);feasibility.initialize(db);clock=datetime.now(timezone.utc)
    row=db.execute('SELECT payload FROM portfolio_states WHERE owner=?',(owner,)).fetchone()
    if not row:return {'version':1,'status':'UNAVAILABLE','revision':0,'state':None,'lots':[],'reason_codes':['NO_MANUAL_LEDGER'],'performance':{'status':'UNAVAILABLE','reason':'RECONCILED_CASHFLOW_HISTORY_REQUIRED'}}
    state=json.loads(row[0]);lots=[];known=Decimal(0);cost=Decimal(0);complete=state['cash'] is not None and state['source']=='MANUAL_CONFIRMED';cost_complete=True
    sectors={};currencies={};by_ticker={}
    for lot in state['lots']:
        quote=mark(db,lot['ticker'],clock);value=None;basis=None;reason=[]
        if quote:
            conversion=fx(db,quote['currency'],state['currency'],clock)
            if conversion is not None:value=Decimal(lot['quantity'])*quote['value']*conversion
            else:reason.append('MISSING_PRICE_FX')
        else:reason.append('MISSING_OR_STALE_PRICE')
        if lot['unit_cost'] is not None and lot['currency']==state['currency']:basis=Decimal(lot['quantity'])*Decimal(lot['unit_cost'])
        else:cost_complete=False;reason.append('MISSING_COST_OR_HISTORICAL_COST_FX')
        if state['source']!='MANUAL_CONFIRMED':reason.append('UNVERIFIED_HOLDING_SOURCE')
        if value is None:complete=False
        else:known+=value;by_ticker[lot['ticker']]=by_ticker.get(lot['ticker'],Decimal(0))+value
        if basis is not None:cost+=basis
        lots.append({**lot,'market_value':str(value) if value is not None else None,'cost_basis':str(basis) if basis is not None else None,
                     'unrealized_pnl':str(value-basis) if value is not None and basis is not None and state['source']=='MANUAL_CONFIRMED' else None,'mark':{k:str(v) for k,v in quote.items()} if quote else None,'reason_codes':reason})
        for groups,key in ((sectors,lot['sector']),(currencies,lot['currency'])):
            entry=groups.setdefault(key,{'known_value':Decimal(0),'unknown_lots':0})
            if value is None:entry['unknown_lots']+=1
            else:entry['known_value']+=value
    total=known+Decimal(state['cash']) if complete else None
    def exposure(groups):return {k:{'known_value':str(v['known_value']),'unknown_lots':v['unknown_lots'],'weight':str(v['known_value']/total) if total is not None and total>0 and not v['unknown_lots'] else None} for k,v in groups.items()}
    risk={'status':'UNAVAILABLE','reason':'COMPLETE_MARKS_FX_AND_ALIGNED_RETURNS_REQUIRED'}
    if total is not None and total>0 and by_ticker:
        series={}
        for ticker in by_ticker:
            history=technical.analyze(root,ticker)
            bars=history['bars']
            if history.get('currency')!=state['currency'] or len(bars)<61:break
            series[ticker]={b['as_of'][:10]:b['close']/a['close']-1 for a,b in zip(bars,bars[1:])}
        if set(series)==set(by_ticker):
            dates=sorted(set.intersection(*(set(v) for v in series.values())))
            risk=contributions({k:float(v/total) for k,v in by_ticker.items()},{k:[series[k][d] for d in dates] for k in by_ticker})
    from finance.portfolio import stress
    journal=[{'id':row[0],'revision':row[1],'known_at':row[2],'intent_type':'MANUAL_OBSERVATION_NOT_TRANSACTION'} for row in db.execute('SELECT id,revision,known_at FROM portfolio_events WHERE owner=? ORDER BY revision DESC LIMIT 100',(owner,))]
    return {'version':1,'revision':state['revision'],'state':state,'lots':lots,'status':'READY' if complete else 'PARTIAL',
            'currency':state['currency'],'known_holdings_value':str(known),'total_value':str(total) if total is not None else None,
            'unrealized_pnl':str(known-cost) if complete and cost_complete else None,'coverage':{'priced_lots':sum(l['market_value'] is not None for l in lots),'total_lots':len(lots)},
            'concentration':{k:str(v/total) for k,v in by_ticker.items()} if total is not None and total>0 else None,
            'sector_exposure':exposure(sectors),'currency_exposure':exposure(currencies),'risk':risk,
            'observation_history':journal,'transactions':[json.loads(r[0]) for r in db.execute('SELECT payload FROM portfolio_transactions WHERE owner=? ORDER BY rowid DESC LIMIT 200',(owner,))],
            'stress':stress(known,Decimal(state['cash'])) if complete else {'status':'UNAVAILABLE','reason':'INCOMPLETE_MARK_OR_FX_COVERAGE'},
            'realized_pnl':{'status':'UNAVAILABLE','value':None,'reason':'RECONCILED_TRANSACTIONS_AND_COST_BASIS_REQUIRED'},
            'available_budget':{'status':'MANUAL_CONTEXT_ONLY' if state['cash'] is not None and state['reserved_cash'] is not None else 'UNAVAILABLE',
                'cash_after_entered_reserves':str(Decimal(state['cash'])-Decimal(state['reserved_cash'])) if state['cash'] is not None and state['reserved_cash'] is not None else None,
                'currency':state['currency'],'execution_policy':'REQUIRES_SEPARATE_FEASIBILITY_RECONCILIATION'},
            'performance':{'status':'UNAVAILABLE','twr':None,'mwr':None,'reason':'MANUAL_OBSERVATIONS_ARE_NOT_RECONCILED_TRANSACTION_HISTORY'},
            'execution':{'status':'UNAVAILABLE','reason':'NO_ORDERS_OR_FILLS_IN_MANUAL_LEDGER'}}
