"""F07 shared Decimal/lot sizing. Trusted state is loaded by the server, not the draft."""
import json
import secrets
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import finance_core
from finance.contracts import envelope

VERSION='f07-v1'


def decimal(value):
    if isinstance(value,bool):raise ValueError('Invalid decimal')
    amount=Decimal(str(value))
    if not amount.is_finite():raise ValueError('Invalid decimal')
    return amount


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS trading_instruments(ticker TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS trading_accounts(owner TEXT PRIMARY KEY REFERENCES accounts(email) ON DELETE CASCADE,payload TEXT NOT NULL)')


def baseline(db,owner,data):
    initialize(db)
    record={k:data[k] for k in ('currency','equity','cash','reserved_cash','as_of','expires_at','sellable')}
    if not isinstance(record['currency'],str) or not re.fullmatch('[A-Z]{3}',record['currency']):raise ValueError('Invalid account currency')
    for key in ('equity','cash','reserved_cash'):
        value=decimal(record[key])
        if value<0:raise ValueError('Negative account state')
        record[key]=str(value)
    if decimal(record['reserved_cash'])>decimal(record['cash']):raise ValueError('Reservations exceed cash')
    finance_core.instant(record['as_of']);finance_core.instant(record['expires_at'])
    if not isinstance(record['sellable'],dict):raise ValueError('Invalid holdings')
    record['sellable']={k:str(decimal(v)) for k,v in record['sellable'].items()}
    if any(decimal(v)<0 for v in record['sellable'].values()):raise ValueError('Negative holdings')
    record.update(version=secrets.token_hex(16),status='MANUAL_UNVERIFIED',source='Manual account baseline',known_at=datetime.now(timezone.utc).isoformat())
    db.execute('INSERT INTO trading_accounts VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET payload=excluded.payload',(owner,json.dumps(record)))
    return record


def review_account(db,owner):
    initialize(db);row=db.execute('SELECT payload FROM trading_accounts WHERE owner=?',(owner,)).fetchone()
    if not row:raise ValueError('Account missing')
    record=json.loads(row[0]);record.update(status='REVIEWED',reviewed_at=datetime.now(timezone.utc).isoformat())
    for key in ('equity','cash','reserved_cash'):
        if decimal(record[key])<0:raise ValueError('Reconciliation requires known balances')
    db.execute('UPDATE trading_accounts SET payload=? WHERE owner=?',(json.dumps(record),owner))


def instrument(db,data):
    initialize(db)
    record={k:data[k] for k in ('ticker','venue','currency','lot','tick','fee_flat','fee_per_share','fee_rate','sell_tax_rate','slippage_bps','calendar','source','quote')}
    for key in ('lot','tick','fee_flat','fee_per_share','fee_rate','sell_tax_rate','slippage_bps'):
        value=decimal(record[key])
        if value<0 or (key in ('lot','tick') and value<=0):raise ValueError('Invalid instrument rule')
        record[key]=str(value)
    if decimal(record['lot'])!=decimal(record['lot']).to_integral_value():raise ValueError('Integer venue lot required')
    record.update(version=secrets.token_hex(16),shortable=False,known_at=datetime.now(timezone.utc).isoformat())
    if data.get('liquidity_max_quantity') is not None:
        cap=decimal(data['liquidity_max_quantity'])
        if cap<0 or cap!=cap.to_integral_value():raise ValueError('Invalid reviewed liquidity cap')
        record['liquidity_max_quantity']=str(cap)
    if decimal(record['slippage_bps'])>=10000 or decimal(record['fee_rate'])>1 or decimal(record['sell_tax_rate'])>1:raise ValueError('Invalid cost fractions')
    if data.get('reviewed') is not True or not all(isinstance(record[k],str) and record[k].strip() for k in ('venue','currency','calendar','source')):raise ValueError('Reviewed rules required')
    quote=record['quote']
    if decimal(quote['price'])<=0 or not 0<decimal(quote['max_age_seconds'])<=86400:raise ValueError('Invalid quote')
    for key in ('as_of','session_open','session_close'):finance_core.instant(quote[key])
    db.execute('INSERT INTO trading_instruments VALUES (?,?) ON CONFLICT(ticker) DO UPDATE SET payload=excluded.payload',(record['ticker'],json.dumps(record)))
    return {'ticker':record['ticker'],'version':record['version'],'status':'REVIEWED'}


def withheld(reason,quantity=None):
    return {'version':1,'calculation_version':VERSION,'status':'WITHHELD','quantity':quantity,'shares':quantity,'reason_codes':[reason],
            'scenarios':[],'kelly':{'status':'WITHHELD','reason_codes':['VALIDATED_TRADE_EDGE_REQUIRED']},'order_status':'DRAFT_ONLY'}


def calculate(draft,account,rules,clock=None):
    clock=clock or datetime.now(timezone.utc)
    if draft.get('sizing_mode','fractional')!='fractional':return withheld('VALIDATED_TRADE_EDGE_REQUIRED')
    if account is None:return withheld('ACCOUNT_BASELINE_REQUIRED')
    if rules is None:return withheld('REVIEWED_INSTRUMENT_QUOTE_REQUIRED')
    if account.get('status')!='REVIEWED':return withheld('ACCOUNT_REVIEW_REQUIRED')
    if finance_core.instant(account['as_of'])>clock or finance_core.instant(account['expires_at'])<=clock:return withheld('ACCOUNT_STATE_STALE_OR_FUTURE')
    if account['currency']!=rules['currency']:return withheld('VERIFIED_FX_REQUIRED')
    quote=rules['quote'];as_of=finance_core.instant(quote['as_of']);opened=finance_core.instant(quote['session_open']);closed=finance_core.instant(quote['session_close'])
    if not opened<=as_of<=closed or as_of>clock or not opened<=clock<=closed:return withheld('QUOTE_OR_TRADING_SESSION_INVALID')
    if (clock-as_of).total_seconds()>float(decimal(quote['max_age_seconds'])):return withheld('QUOTE_EXPIRED')
    entry,stop,target=[decimal(draft[k]) for k in ('entry','stop','target')]
    risk=decimal(draft['risk'])
    if min(entry,stop,target)<=0 or not 0<risk<=100:raise ValueError('Invalid draft')
    direction=draft.get('direction','Long');side=draft.get('side','BUY' if direction=='Long' else 'SHORT')
    if direction not in ('Long','Short') or side not in ('BUY','SELL','SHORT'):raise ValueError('Invalid side')
    if not (stop<entry<target if direction=='Long' else target<entry<stop):return withheld('STOP_TARGET_DIRECTION_INVALID')
    if side=='SHORT':return withheld('VERIFIED_BORROW_AND_MARGIN_REQUIRED')
    if side=='SELL' and direction!='Long':return withheld('SELL_REDUCTION_REQUIRES_LONG_HOLDING')
    tick=decimal(rules['tick']);lot=int(decimal(rules['lot']))
    if any(p%tick!=0 for p in (entry,stop,target)):return withheld('PRICE_TICK_MISMATCH')
    cash=decimal(account['cash'])-decimal(account['reserved_cash']);equity=decimal(account['equity'])
    budget=equity*risk/100;flat=decimal(rules['fee_flat']);per_share=decimal(rules['fee_per_share']);rate=decimal(rules['fee_rate']);tax=decimal(rules['sell_tax_rate']);slip=decimal(rules['slippage_bps'])/10000
    buy_unit=entry*(1+slip)*(1+rate)+per_share
    stop_exit=stop*(1-slip);target_exit=target*(1-slip)
    risk_basis=draft.get('risk_basis','STOP_COST_ADJUSTED')
    if risk_basis not in ('STOP_COST_ADJUSTED','GAP_STRESS'):raise ValueError('Invalid risk basis')
    risk_exit=stop_exit
    if risk_basis=='GAP_STRESS':
        gap_stress=decimal(draft.get('gap_slippage_pct','5'))/100
        if not 0<=gap_stress<1:raise ValueError('Invalid gap stress')
        risk_exit=stop*(1-gap_stress)*(1-slip)
    stop_unit=max(Decimal(0),entry-risk_exit)+entry*slip+per_share*2+entry*(1+slip)*rate+risk_exit*(rate+tax)
    if stop_unit<=0:return withheld('INVALID_COST_ADJUSTED_RISK')
    risk_lots=max(0,int(((budget-flat*2)/stop_unit/lot).to_integral_value(rounding=ROUND_FLOOR)))
    cash_lots=max(0,int(((cash-flat)/buy_unit/lot).to_integral_value(rounding=ROUND_FLOOR)))
    if side=='SELL':
        held=decimal(account['sellable'].get(draft['ticker'],'0'))
        cash_lots=int((held/lot).to_integral_value(rounding=ROUND_FLOOR))
    quantity=min(risk_lots,cash_lots)*lot
    if rules.get('liquidity_max_quantity') is not None:
        quantity=min(quantity,max(0,int((decimal(rules['liquidity_max_quantity'])/lot).to_integral_value(rounding=ROUND_FLOOR)))*lot)
    if draft.get('requested_quantity') is not None:
        requested=decimal(draft['requested_quantity'])
        if requested<0 or requested%lot!=0:return withheld('REQUESTED_QUANTITY_NOT_A_LOT')
        quantity=min(quantity,int(requested))
    if quantity<=0:return withheld('REVIEWED_LIQUIDITY_BELOW_MINIMUM_LOT' if rules.get('liquidity_max_quantity') is not None and decimal(rules['liquidity_max_quantity'])<lot else 'CASH_RISK_OR_HOLDINGS_BELOW_MINIMUM_LOT',0)
    q=Decimal(quantity);entry_cost=q*buy_unit+flat
    exit_cost=lambda price:q*(per_share+price*(rate+tax))+flat
    def pnl(price):
        if direction=='Long':return q*(price-entry*(1+slip))-q*(per_share+entry*(1+slip)*rate)-flat-exit_cost(price)
        return q*(entry-price)-q*(per_share+entry*rate)-flat-exit_cost(price)
    stop_pnl=pnl(stop_exit);target_pnl=pnl(target_exit)
    # Unresolved and gap outcomes are stress scenarios, never assigned invented probabilities.
    gap=decimal(draft.get('gap_slippage_pct','5'))/100
    if not 0<=gap<1:raise ValueError('Invalid gap stress')
    gap_price=stop*(1-gap) if direction=='Long' else stop*(1+gap)
    cash_after=cash-entry_cost if side=='BUY' else cash+q*entry-exit_cost(entry)
    if cash_after<0 or (side=='SELL' and q>decimal(account['sellable'].get(draft['ticker'],'0'))):return withheld('CASH_OR_HOLDINGS_CONSTRAINT_FAILED')
    return {'version':1,'calculation_version':VERSION,'status':'READY','quantity':quantity,'shares':quantity,'currency':rules['currency'],'venue':rules['venue'],
            'lot':lot,'tick':str(tick),'available_cash':str(cash),'cash_after':str(cash_after),'riskBudget':str(budget),'maxLoss':str(max(Decimal(0),-stop_pnl)),
            'potentialProfit':str(target_pnl),'positionValue':str(q*entry),'ratio':str(target_pnl/abs(stop_pnl)) if stop_pnl<0 else None,
            'stop_risk_policy':'STOP_IS_NOT_MAXIMUM_LOSS_UNDER_GAPS_OR_MARKET_IMPACT','liquidity_status':'REVIEWED_CAP' if rules.get('liquidity_max_quantity') is not None else 'NOT_ASSESSED_DRAFT_ONLY',
            'risk_basis':risk_basis,'sizing_stress_loss_per_share':str(stop_unit),
            'account_version':account['version'],'instrument_version':rules['version'],'quote_as_of':quote['as_of'],
            'expires_at':min(finance_core.instant(account['expires_at']),closed,as_of+timedelta_seconds(quote['max_age_seconds'])).isoformat(),
            'reason_codes':[],'order_status':'DRAFT_ONLY','kelly':{'status':'WITHHELD','reason_codes':['VALIDATED_TRADE_EDGE_REQUIRED']},
            'scenarios':[{'outcome':name,'net_pnl':str(value),'currency':rules['currency'],'probability':None,'basis':'HYPOTHETICAL_STRESS'} for name,value in [('TARGET_HIT',target_pnl),('STOP_HIT',stop_pnl),('UNRESOLVED_AT_ENTRY',pnl(entry)),('GAP_SLIPPAGE',pnl(gap_price))]]}


def timedelta_seconds(value):
    from datetime import timedelta
    return timedelta(seconds=float(decimal(value)))


def for_owner(db,owner,draft):
    initialize(db)
    account=db.execute('SELECT payload FROM trading_accounts WHERE owner=?',(owner,)).fetchone()
    rule=db.execute('SELECT payload FROM trading_instruments WHERE ticker=?',(draft['ticker'],)).fetchone()
    result=calculate(draft,json.loads(account[0]) if account else None,json.loads(rule[0]) if rule else None)
    input_clocks=[]
    if account:
        context=json.loads(account[0]);input_clocks.extend(context[k] for k in ('as_of','known_at','reviewed_at') if context.get(k))
    if rule:
        context=json.loads(rule[0]);input_clocks.extend([context['quote']['as_of']]);input_clocks.extend([context['known_at']] if context.get('known_at') else [])
    result['result_contract']=envelope({'definition_id':'execution_feasible_draft_quantity','value':result['quantity'],'unit':'shares',
        'status':result['status'],'origin':'DERIVED','known_at':max(input_clocks,key=finance_core.instant) if input_clocks else None,'as_of':result.get('quote_as_of'),
        'source_ids':[v for v in (result.get('account_version'),result.get('instrument_version')) if v],
        'calculation_version':VERSION,'reason_codes':result['reason_codes'],'eligibility':{'order_status':'DRAFT_ONLY','expires_at':result.get('expires_at')}},object_type='DecisionEligibility')
    return result


def outcome_rates(wins,losses,unresolved):
    if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in (wins,losses,unresolved)):raise ValueError('Invalid path counts')
    total=wins+losses+unresolved;resolved=wins+losses
    return {'conditional_target_hit':wins/resolved if resolved else None,'unconditional_target_hit':wins/total if total else None,'resolved':resolved,'unresolved':unresolved}
