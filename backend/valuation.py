"""F04 versioned assumptions, dated operating forecasts and eligible valuations."""
from finance.forecast import operating_year
from finance.valuation import quote_gap, FAMILIES
import json
import secrets
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import finance_core as finance

VERSION='f04-v1'
UNITS={key:'fraction' for key in ('revenue_growth','ebit_margin','tax_rate','da_pct','capex_pct','nwc_pct','interest_pct','nci_income_pct','net_borrowing_pct','risk_free_rate','equity_risk_premium','debt_cost','debt_weight','terminal_growth','dividend_growth')}
UNITS.update(beta='x',pe_multiple='x',nci_value='currency',nonoperating_value='currency',adjusted_equity_value='currency',terminal_stability='boolean',recurring_dividend='boolean',sector_policy='category',next_dividend_date='date')
DRIVERS=('revenue_growth','ebit_margin','tax_rate','da_pct','capex_pct','nwc_pct','interest_pct','nci_income_pct','net_borrowing_pct')
RATES=('risk_free_rate','beta','equity_risk_premium','debt_cost','debt_weight','tax_rate')
METHODS=('FCFF','FCFE','P/E','DDM','Gordon','Asset-based')


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS valuation_assumptions(id TEXT PRIMARY KEY, owner TEXT REFERENCES accounts(email) ON DELETE CASCADE, ticker TEXT NOT NULL, scenario TEXT NOT NULL, definition TEXT NOT NULL, version TEXT NOT NULL, payload TEXT NOT NULL, reviewed_at TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS valuation_runs(id TEXT PRIMARY KEY, owner TEXT REFERENCES accounts(email) ON DELETE CASCADE, payload TEXT NOT NULL)')


def register(db,owner,ticker,scenario,rows):
    initialize(db)
    if scenario not in ('base','upside','downside') or not isinstance(rows,list) or not 1<=len(rows)<=50:
        raise ValueError('Invalid assumption scenario.')
    result=[]
    for row in rows:
        key=row['definition']
        if key not in UNITS or row['unit']!=UNITS[key]:
            raise ValueError('Invalid assumption definition or unit.')
        value=row['value']
        if key=='next_dividend_date':
            value=date.fromisoformat(value).isoformat()
        elif key=='sector_policy':
            if value not in ('industrial','bank','insurer'):
                raise ValueError('Explicit sector policy required.')
        else:
            value=Decimal(str(value))
            if not value.is_finite():
                raise ValueError('Finite assumption required.')
            if key in ('terminal_stability','recurring_dividend') and value not in (0,1):
                raise ValueError('Boolean assumption required.')
            if key in ('tax_rate','debt_weight') and not 0<=value<=1:
                raise ValueError('Fraction outside allowed bounds.')
            if key in ('ebit_margin','da_pct','capex_pct','nwc_pct','interest_pct','nci_income_pct') and not 0<=value<=1:
                raise ValueError('Invalid operating driver.')
            if key=='revenue_growth' and value<=-1:
                raise ValueError('Revenue growth must exceed -100%.')
            value=str(value)
        effective=finance.instant(row['effective_from'])
        currency=row.get('currency')
        if UNITS[key]=='currency' and (not isinstance(currency,str) or not re.fullmatch('[A-Z]{3}',currency)):
            raise ValueError('Currency assumption requires an explicit currency.')
        sources=row.get('source_ids',[])
        if not isinstance(sources,list) or not all(isinstance(s,str) for s in sources):
            raise ValueError('Invalid assumption evidence.')
        record={'id':secrets.token_hex(16),'ticker':ticker,'scenario':scenario,'definition':key,'value':value,'unit':UNITS[key],
                'effective_from':effective.isoformat(),'known_at':datetime.now(timezone.utc).isoformat(),'source_ids':sources,
                'version':secrets.token_hex(8),'origin':'ASSUMPTION','status':'UNVERIFIED','currency':currency}
        db.execute('INSERT INTO valuation_assumptions VALUES (?,?,?,?,?,?,?,NULL)',(record['id'],owner,ticker,scenario,key,record['version'],json.dumps(record)))
        result.append(record)
    return result


def review(db,root,owner,ids):
    initialize(db)
    for identity in ids:
        row=db.execute('SELECT ticker,payload FROM valuation_assumptions WHERE id=? AND owner=?',(identity,owner)).fetchone()
        if not row:
            raise ValueError('Assumption not found for owner.')
        record=json.loads(row[1])
        if not record['source_ids']:
            raise ValueError('Source evidence is required before review.')
        for source in record['source_ids']:
            evidence=finance.evidence(root,source)
            if not evidence or evidence['ticker']!=row[0] or evidence['status']!='READY':
                raise ValueError('Accepted issuer evidence is required.')
            if record['unit']=='currency' and evidence['currency']!=record['currency']:
                raise ValueError('Assumption evidence currency mismatch.')
        if db.execute('SELECT reviewed_at FROM valuation_assumptions WHERE id=?',(identity,)).fetchone()[0] is not None:
            raise ValueError('Assumption version is already reviewed.')
        db.execute('UPDATE valuation_assumptions SET reviewed_at=? WHERE id=?',(datetime.now(timezone.utc).isoformat(),identity))


def load_assumptions(db,owner,ticker,scenario,origin):
    initialize(db)
    selected={}
    registered_scenario=False
    for chosen in ('base',scenario) if scenario!='base' else ('base',):
        for row in db.execute('SELECT payload,reviewed_at FROM valuation_assumptions WHERE owner=? AND ticker=? AND scenario=? ORDER BY rowid',(owner,ticker,chosen)):
            record=json.loads(row[0])
            known=max(finance.instant(record['known_at']),finance.instant(row[1])) if row[1] else finance.instant(record['known_at'])
            if known>origin or finance.instant(record['effective_from'])>origin:
                continue
            record.update(known_at=known.isoformat(),status='VERIFIED' if row[1] else 'UNVERIFIED')
            selected[record['definition']]=record
            if chosen==scenario:
                registered_scenario=True
    return selected,registered_scenario


def unavailable(method,reason):
    return {'method':method,'status':'WITHHELD','reason_codes':[reason],'value':None,'currency':None,'unit':'currency/share','source_ids':[],'assumption_ids':[],'sensitivity':[],'calculation_version':VERSION}


def next_year(value,years):
    try:
        return value.replace(year=value.year+years)
    except ValueError:
        return value.replace(year=value.year+years,day=28)


def calculate(db,root,owner,payload):
    ticker=payload['ticker'].upper()
    scenario=payload.get('scenario','base')
    if scenario not in ('base','upside','downside'):
        raise ValueError('Invalid scenario.')
    valuation_date=date.fromisoformat(payload['valuation_date'])
    today=datetime.now(timezone.utc)
    valuation_zone=ZoneInfo(payload.get('valuation_timezone','Asia/Shanghai'))
    if valuation_date>today.astimezone(valuation_zone).date():
        raise ValueError('Future valuation date not permitted.')
    origin=min(today,datetime.combine(valuation_date,datetime.max.time(),tzinfo=valuation_zone).astimezone(timezone.utc))
    period=payload.get('period','FY')
    if period not in ('FY','TTM'):
        raise ValueError('Annual base required.')
    base=finance.company(root,ticker,period,payload.get('period_end'),origin.isoformat())
    assumptions,registered=load_assumptions(db,owner,ticker,scenario,origin)
    def require(keys):
        if not registered:
            raise ValueError('SCENARIO_NOT_REGISTERED')
        if any(k not in assumptions for k in keys):
            raise ValueError('MISSING_ASSUMPTIONS')
        if any(assumptions[k]['status']!='VERIFIED' for k in keys):
            raise ValueError('UNVERIFIED_ASSUMPTIONS')
        return {k:Decimal(assumptions[k]['value']) for k in keys if k not in ('sector_policy','next_dividend_date')}
    def actual(keys):
        facts=[base['metrics'][key] for key in keys]
        if any(f['status']!='READY' for f in facts):
            raise ValueError('MISSING_ACTUAL_BASE')
        context=('currency','scope','accounting_basis','restatement_basis','period_end')
        if any(any(f.get(k)!=facts[0].get(k) for k in context) for f in facts[1:]):
            raise ValueError('INCOMPATIBLE_ACTUAL_CONTEXT')
        return {k:Decimal(base['metrics'][k]['value']) for k in keys}
    methods=[]
    forecast=[]
    currency=None
    for method in METHODS:
        used=[]; facts_used=[]; flows=[]
        try:
            require(['sector_policy']); used.append('sector_policy')
            sector=assumptions['sector_policy']['value']
            if method in ('FCFF','FCFE') and sector!='industrial':
                raise ValueError('INDUSTRIAL_CASHFLOW_INELIGIBLE_FOR_SECTOR')
            if method in ('FCFF','FCFE'):
                used+=list(DRIVERS)+list(RATES)+['terminal_growth','terminal_stability']
                drivers=require(list(dict.fromkeys(used)))
                if drivers['terminal_stability']!=1:
                    raise ValueError('TERMINAL_ECONOMICS_NOT_JUSTIFIED')
                facts_used=['revenue','ebit','ebitda','operating_nwc','diluted_shares']
                if method=='FCFE':
                    facts_used+=['net_income_common']
                else:
                    facts_used+=['debt','cash','restricted_cash','lease_debt']
                    used+=['nci_value','nonoperating_value']; drivers.update(require(['nci_value','nonoperating_value']))
                amounts=actual(facts_used)
                if amounts['revenue']<=0:
                    raise ValueError('POSITIVE_REVENUE_BASE_REQUIRED')
                shares=amounts['diluted_shares']
                if shares<=0:
                    raise ValueError('INVALID_DILUTED_SHARES')
                ke=drivers['risk_free_rate']+drivers['beta']*drivers['equity_risk_premium']
                wacc=ke*(1-drivers['debt_weight'])+drivers['debt_cost']*(1-drivers['tax_rate'])*drivers['debt_weight']
                rate=wacc if method=='FCFF' else ke
                growth=drivers['terminal_growth']
                if rate<=growth or rate<=0:
                    raise ValueError('DISCOUNT_RATE_MUST_EXCEED_TERMINAL_GROWTH')
                revenue=amounts['revenue']; nwc=amounts['operating_nwc']
                end=date.fromisoformat(base['period_end'])
                for year in range(1,6):
                    cash_date=next_year(end,year)
                    if cash_date<=valuation_date:
                        raise ValueError('ACTUAL_BASE_TOO_OLD_FOR_FORECAST')
                    row=operating_year(revenue,nwc,drivers,cash_date.isoformat(),base['metrics']['revenue']['currency'])
                    row['assumption_ids']=[assumptions[k]['id'] for k in DRIVERS]
                    row['source_ids']=list(dict.fromkeys(s for k in facts_used for s in base['metrics'][k]['source_ids']))
                    flows.append(row);revenue=Decimal(row['revenue']);nwc=Decimal(row['closing_nwc'])
                selected='fcff' if method=='FCFF' else 'fcfe'
                bridge=amounts.get('debt',0)-amounts.get('cash',0)+amounts.get('restricted_cash',0)+amounts.get('lease_debt',0)+drivers.get('nci_value',0)-drivers.get('nonoperating_value',0) if method=='FCFF' else Decimal(0)
                def discounted(discount,terminal):
                    if discount<=terminal or discount<=0:
                        raise ValueError('INVALID_SENSITIVITY_RATE')
                    value=sum(Decimal(row[selected])/(1+discount)**(Decimal((date.fromisoformat(row['cash_date'])-valuation_date).days)/365) for row in flows)
                    terminal_cash=Decimal(flows[-1][selected])*(1+terminal)
                    if terminal_cash<=0:
                        raise ValueError('NONPOSITIVE_STABLE_TERMINAL_CASHFLOW')
                    tv=terminal_cash/(discount-terminal)
                    value+=tv/(1+discount)**(Decimal((date.fromisoformat(flows[-1]['cash_date'])-valuation_date).days)/365)
                    per_share=(value-bridge)/shares
                    if per_share<=0:
                        raise ValueError('NO_POSITIVE_RESIDUAL_EQUITY_VALUE')
                    return per_share
                value=discounted(rate,growth)
                sensitivity=[]
                for shift in (Decimal('-.01'),Decimal(0),Decimal('.01')):
                    for g_shift in (Decimal('-.005'),Decimal(0),Decimal('.005')):
                        try:
                            sensitivity.append({'discount_rate':str(rate+shift),'terminal_growth':str(growth+g_shift),'value':str(discounted(rate+shift,growth+g_shift)),'status':'READY'})
                        except ValueError:
                            sensitivity.append({'discount_rate':str(rate+shift),'terminal_growth':str(growth+g_shift),'value':None,'status':'WITHHELD'})
                details={'ke':str(ke),'wacc':str(wacc),'equity_bridge':str(bridge),'discount_basis':'ACT/365, year-end cash flows',
                    'capital_assumptions':{k:str(drivers[k]) for k in RATES},'terminal_growth':str(growth),
                    'equity_bridge_components':{k:str(amounts.get(k,drivers.get(k,0))) for k in ('debt','cash','restricted_cash','lease_debt','nci_value','nonoperating_value')} if method=='FCFF' else {},
                    'terminal_stability':'REVIEWED','valuation_date':valuation_date.isoformat()}
                # Margin sensitivity follows the same operating and tax cash bridge.
                for margin_shift in (Decimal('-.02'),Decimal('.02')):
                    margin=drivers['ebit_margin']+margin_shift
                    if not 0<=margin<=1:
                        continue
                    adjusted_flows=[]
                    for row in flows:
                        adjusted=dict(row)
                        revenue_at=Decimal(row['revenue']); ebit_at=revenue_at*margin
                        interest_at=revenue_at*drivers['interest_pct']
                        common_at=ebit_at-interest_at-max(Decimal(0),ebit_at-interest_at)*drivers['tax_rate']-revenue_at*drivers['nci_income_pct']
                        adjusted['fcff']=str(ebit_at*(1-drivers['tax_rate'])+Decimal(row['da'])-Decimal(row['capex'])-Decimal(row['delta_nwc']))
                        adjusted['fcfe']=str(common_at+Decimal(row['da'])-Decimal(row['capex'])-Decimal(row['delta_nwc'])+Decimal(row['net_borrowing']))
                        adjusted_flows.append(adjusted)
                    original_flows=flows; flows=adjusted_flows
                    try:
                        sensitivity.append({'ebit_margin':str(margin),'value':str(discounted(rate,growth)),'status':'READY'})
                    except ValueError:
                        sensitivity.append({'ebit_margin':str(margin),'value':None,'status':'WITHHELD'})
                    finally:
                        flows=original_flows
            elif method=='P/E':
                used+=['pe_multiple']; multiple=require(['pe_multiple'])['pe_multiple']
                facts_used=['eps']; eps=actual(facts_used)['eps']
                if eps<=0 or multiple<=0:
                    raise ValueError('POSITIVE_COMMON_EPS_AND_COMPARABLE_MULTIPLE_REQUIRED')
                value=eps*multiple; sensitivity=[{'multiple':str(multiple*s),'value':str(value*s),'status':'READY'} for s in (Decimal('.9'),Decimal(1),Decimal('1.1'))]; details={'cross_check':'Normalized comparable P/E assumption; not an independent forecast'}
            elif method in ('DDM','Gordon'):
                used+=['risk_free_rate','beta','equity_risk_premium','dividend_growth','recurring_dividend','next_dividend_date']
                drivers=require(used)
                if drivers['recurring_dividend']!=1:
                    raise ValueError('RECURRING_DIVIDEND_NOT_VERIFIED')
                facts_used=['dividend_per_share']; dividend=actual(facts_used)['dividend_per_share']
                rate=drivers['risk_free_rate']+drivers['beta']*drivers['equity_risk_premium']; growth=drivers['dividend_growth']
                if rate<=growth or rate<=0 or dividend<=0 or growth<=-1:
                    raise ValueError('INVALID_DIVIDEND_PERPETUITY')
                payment=date.fromisoformat(assumptions['next_dividend_date']['value'])
                if payment<=valuation_date:
                    raise ValueError('FUTURE_DIVIDEND_PAYMENT_DATE_REQUIRED')
                duration=Decimal((payment-valuation_date).days)/365
                if method=='DDM':
                    flows=[{'cash_date':next_year(payment,i-1).isoformat(),'dividend_per_share':str(dividend*(1+growth)**i),'origin':'FORECAST'} for i in range(1,6)]
                def dividend_value(discount):
                    if discount<=growth or discount<=0:
                        raise ValueError('INVALID_DIVIDEND_PERPETUITY')
                    if method=='Gordon':
                        return dividend*(1+growth)/(discount-growth)*(1+discount)**(1-duration)
                    value=sum(Decimal(r['dividend_per_share'])/(1+discount)**(Decimal((date.fromisoformat(r['cash_date'])-valuation_date).days)/365) for r in flows)
                    return value+Decimal(flows[-1]['dividend_per_share'])*(1+growth)/(discount-growth)/(1+discount)**(Decimal((date.fromisoformat(flows[-1]['cash_date'])-valuation_date).days)/365)
                value=dividend_value(rate)
                sensitivity=[]
                for shift in (Decimal('-.01'),Decimal(0),Decimal('.01')):
                    sensitivity.append({'ke':str(rate+shift),'value':str(dividend_value(rate+shift)) if rate+shift>growth and rate+shift>0 else None,'status':'READY' if rate+shift>growth and rate+shift>0 else 'WITHHELD'})
                details={'evidence_family':'DIVIDEND','next_payment':payment.isoformat(),'discount_basis':'ACT/365, explicit annual dividend payment dates','cross_check':'DDM and Gordon share dividend/rate assumptions; correlated evidence'}
            else:
                used+=['adjusted_equity_value']; adjusted=require(['adjusted_equity_value'])['adjusted_equity_value']
                facts_used=['diluted_shares']; shares=actual(facts_used)['diluted_shares']
                if shares<=0 or adjusted<=0:
                    raise ValueError('INVALID_ADJUSTED_ASSETS_OR_SHARES')
                value=adjusted/shares; sensitivity=[{'equity_value':str(adjusted*s),'value':str(value*s),'status':'READY'} for s in (Decimal('.9'),Decimal(1),Decimal('1.1'))]; details={'cross_check':'Reviewed adjusted net assets, not a P/B shortcut'}
            currency=base['metrics'][facts_used[0]]['currency']
            if any(assumptions[k]['unit']=='currency' and assumptions[k]['currency']!=currency for k in used):
                raise ValueError('INCOMPATIBLE_ASSUMPTION_CURRENCY')
            result={'method':method,'status':'READY','value':str(value),'unit':'currency/share','currency':currency,'origin':'FORECAST',
                    'reason_codes':[],'source_ids':list(dict.fromkeys([s for k in facts_used for s in base['metrics'][k]['source_ids']]+[s for k in used for s in assumptions[k]['source_ids']])),
                    'assumption_ids':list(dict.fromkeys(assumptions[k]['id'] for k in used)),'forecast':flows,'sensitivity':sensitivity,
                    'details':details,'evidence_family':FAMILIES[method],'calculation_version':VERSION,'known_at':max([base['metrics'][k]['known_at'] for k in facts_used]+[assumptions[k]['known_at'] for k in used],key=finance.instant)}
            sensitive_values=[Decimal(s['value']) for s in sensitivity if s['status']=='READY' and s['value'] is not None]
            result['sensitivity_band']={'low':str(min(sensitive_values)),'base':str(value),'high':str(max(sensitive_values)),'unit':'currency/share','currency':currency}
            result['actual_base']={k:base['metrics'][k] for k in facts_used}
            methods.append(result)
            if method in ('FCFF','FCFE') and not forecast:
                forecast=flows
        except (ValueError, ArithmeticError) as error:
            methods.append(unavailable(method,str(error) if isinstance(error,ValueError) else 'INVALID_CALCULATION'))
    result={'version':1,'run_id':secrets.token_hex(16),'calculation_version':VERSION,'ticker':ticker,'scenario':scenario,'valuation_date':valuation_date.isoformat(),
            'base':base,'assumptions':list(assumptions.values()),'forecast':forecast,'methods':methods,
            'summary':'Method-specific estimates only; no composite buy score or averaged fair value.',
            'quote_gap':quote_gap(db,ticker,valuation_date,valuation_zone,methods),
            'cross_check_policy':{'FCFF_FCFE':'CORRELATED_OPERATING_ASSUMPTIONS','DDM_Gordon':'CORRELATED_DIVIDEND_AND_EQUITY_RATE_INPUTS','consensus':'NO_FORCED_AVERAGE_OR_INDEPENDENCE_CLAIM'}}
    db.execute('INSERT INTO valuation_runs VALUES (?,?,?)',(result['run_id'],owner,json.dumps(result)))
    return result
