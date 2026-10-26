"""Reviewed financial facts, fiscal calendars and deterministic F03 calculations."""
import json
import re
import sqlite3
from urllib.parse import urlsplit
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from finance.contracts import envelope
from common.time import instant, eligible_at_origin, derived_known_at, InformationClocks
from finance.periods import validate_calendar, quarter_start, contiguous
from finance.periods import AccountingPeriod, BalanceAsOf
from dataclasses import asdict
from finance.metrics import annotate, returns_period
from finance.quality import screen

VERSION = 'f03-v1'
FLOW = {'revenue', 'net_income', 'net_income_common', 'operating_profit', 'ebit', 'reported_ebitda', 'adjusted_ebitda', 'proxy_ebitda', 'da_expense', 'cfo', 'capex', 'dividends'}
STOCK = {'assets', 'liabilities', 'equity', 'common_equity', 'debt', 'cash', 'accumulated_depreciation', 'current_assets', 'current_liabilities', 'receivables', 'shares_outstanding', 'diluted_shares', 'operating_nwc', 'restricted_cash', 'lease_debt'}
DEFINITIONS = {m: {'id': m, 'kind': 'flow' if m in FLOW else 'stock' if m in STOCK else 'nonadditive',
                    'unit': 'shares' if m in {'shares_outstanding', 'weighted_average_shares','diluted_shares'} else 'currency/share' if m=='dividend_per_share' else 'currency'}
               for m in FLOW | STOCK | {'weighted_average_shares','dividend_per_share'}}


@contextmanager
def database(root):
    db = sqlite3.connect(root / 'finance.sqlite3')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            db.executescript('''CREATE TABLE IF NOT EXISTS issuers(ticker TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calendars(ticker TEXT REFERENCES issuers(ticker), year TEXT, payload TEXT NOT NULL, PRIMARY KEY(ticker,year));
                CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, ticker TEXT REFERENCES issuers(ticker), payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY, ticker TEXT REFERENCES issuers(ticker), payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS definitions(id TEXT PRIMARY KEY, payload TEXT NOT NULL);''')
            for key, value in DEFINITIONS.items():
                db.execute('INSERT OR IGNORE INTO definitions VALUES (?,?)', (key, json.dumps(value)))
            yield db
    finally:
        db.close()


def ingest(root, payload, reviewer, now=None, connection=None):
    now = now or datetime.now(timezone.utc)
    issuer, calendar = payload['issuer'], payload['calendar']
    ticker = issuer['ticker'].upper()
    if not re.fullmatch(r'[A-Z0-9.-]{1,16}', ticker) or not isinstance(issuer['name'], str) or not 1 <= len(issuer['name']) <= 200:
        raise ValueError('Invalid issuer.')
    starts, ends = date.fromisoformat(calendar['start']), date.fromisoformat(calendar['end'])
    quarters = [date.fromisoformat(v) for v in calendar['quarter_ends']]
    if len(quarters) != 4 or not starts <= quarters[0] or not all(a < b for a,b in zip(quarters, quarters[1:])) or quarters[-1] != ends:
        raise ValueError('Explicit fiscal quarter boundaries are required.')
    year = str(calendar['year'])
    validate_calendar(calendar)
    reports = {}
    for item in payload['reports']:
        report = {k: item[k] for k in ('id', 'document_id', 'published_at', 'indexed_at')}
        report.update(source_hash=item.get('source_hash'),parser_version=item.get('parser_version'))
        if item.get('source_url'):
            address=urlsplit(item['source_url'])
            if address.scheme!='https' or not address.hostname or address.username or address.password:
                raise ValueError('Filing citation must have an HTTPS source URL')
            report['source_url']=item['source_url']
        if item.get('source_kind'):
            report['source_kind']=item['source_kind']
        if not all(isinstance(report[k], str) and 1 <= len(report[k]) <= 200 for k in ('id', 'document_id')):
            raise ValueError('Invalid report identity.')
        instant(report['published_at']); instant(report['indexed_at'])
        reports[report['id']] = report
    accepted = []
    for item in payload['facts']:
        metric = item['definition_id']
        if metric not in DEFINITIONS or item.get('reviewed') is not True:
            raise ValueError('Only reviewed registered definitions are accepted.')
        start, end = date.fromisoformat(item['period_start']), date.fromisoformat(item['period_end'])
        kind = item['period_type']
        quarter_starts = [starts] + [v + timedelta(days=1) for v in quarters[:-1]]
        valid = (kind == 'Q' and (start,end) in list(zip(quarter_starts, quarters))) or (kind == 'YTD' and start == starts and end in quarters) or (kind == 'FY' and start == starts and end == ends)
        if metric in STOCK:
            valid = kind == 'INSTANT' and start == end and starts - timedelta(days=1) <= end <= ends
        if not valid:
            raise ValueError('Fact does not match its issuer fiscal calendar.')
        value = None if item['value'] is None else Decimal(str(item['value']))
        scale = Decimal(str(item['scale']))
        if (value is not None and not value.is_finite()) or not scale.is_finite() or scale <= 0:
            raise ValueError('Invalid decimal amount or scale.')
        if item['unit'] != DEFINITIONS[metric]['unit'] or not re.fullmatch('[A-Z]{3}', item['currency']):
            raise ValueError('Invalid currency or definition unit.')
        for key in ('scope', 'accounting_basis', 'restatement_basis', 'revision', 'id'):
            if not isinstance(item[key], str) or not 1 <= len(item[key]) <= 120:
                raise ValueError('Explicit fact context is required.')
        report = reports[item['report_id']]
        evidence = item['evidence']
        page=evidence.get('page')
        valid_page=(isinstance(page,int) and not isinstance(page,bool) and page>0) or (page is None and evidence.get('page_kind')=='UNPAGINATED_SECTION' and isinstance(evidence.get('section_id'),str) and bool(evidence['section_id']))
        if not valid_page or not all(isinstance(evidence.get(k), str) and 0 < len(evidence[k]) <= 200 for k in ('table', 'tag')):
            raise ValueError('Page/table/tag evidence is required.')
        known = instant(InformationClocks(report['published_at'],report['indexed_at'],now.isoformat()).known_at)
        fact = {k: item[k] for k in ('id','definition_id','period_start','period_end','period_type','currency','unit','scope','accounting_basis','restatement_basis','revision','report_id')}
        fact.update(ticker=ticker, value=None if value is None else str(value * scale), raw_value=item['value'], scale=str(scale),
                    fiscal_year=year, origin='ACTUAL', status='READY' if value is not None else 'UNAVAILABLE',
                    known_at=known.isoformat(), accepted_at=now.isoformat(), reviewer=reviewer,
                    source_ids=[item['id']], evidence={k: evidence[k] for k in ('page','table','tag')},
                    da_eligible=item.get('da_eligible') is True, calculation_version=VERSION, reason_codes=[] if value is not None else ['MISSING_REPORTED_VALUE'])
        fact['information_clocks']=asdict(InformationClocks(report['published_at'],report['indexed_at'],now.isoformat()))
        fact['period_context']=asdict(BalanceAsOf(ticker,end.isoformat())) if metric in STOCK else asdict(AccountingPeriod(ticker,year,kind,start.isoformat(),end.isoformat()))
        for key in ('ownership','financial_fact_key','structured_context','source_line_label'):
            if key in item:fact[key]=item[key]
        accepted.append(envelope(annotate(fact)))
    if not accepted or len(accepted) > 2000:
        raise ValueError('Submit between 1 and 2000 reviewed facts.')
    with (nullcontext(connection) if connection is not None else database(root)) as db:
        db.execute('INSERT INTO issuers VALUES (?,?) ON CONFLICT(ticker) DO UPDATE SET name=excluded.name', (ticker, issuer['name']))
        current = db.execute('SELECT payload FROM calendars WHERE ticker=? AND year=?', (ticker,year)).fetchone()
        if current and json.loads(current[0]) != calendar:
            raise ValueError('Registered fiscal calendar is immutable.')
        for row in db.execute('SELECT year,payload FROM calendars WHERE ticker=?',(ticker,)):
            registered=json.loads(row['payload'])
            if row['year']!=year and not (ends < date.fromisoformat(registered['start']) or starts > date.fromisoformat(registered['end'])):
                raise ValueError('Fiscal calendars cannot overlap.')
        db.execute('INSERT OR IGNORE INTO calendars VALUES (?,?,?)', (ticker,year,json.dumps(calendar)))
        for report in reports.values():
            db.execute('INSERT INTO reports VALUES (?,?,?)', (report['id'],ticker,json.dumps(report)))
        for fact in accepted:
            db.execute('INSERT INTO facts VALUES (?,?,?)', (fact['id'],ticker,json.dumps(fact)))
    return len(accepted)


def unavailable(metric, reason='MISSING_COMPATIBLE_FACTS'):
    return {'definition_id':metric,'value':None,'unit':None,'status':'UNAVAILABLE','origin':'DERIVED',
            'reason_codes':[reason],'source_ids':[],'calculation_version':VERSION}


CONTEXT = ('currency','scope','accounting_basis','restatement_basis','unit')


def compatible(a, b, periods=True):
    return all(a.get(k) == b.get(k) for k in CONTEXT) and a.get('ownership')==b.get('ownership') and (not periods or all(a.get(k) == b.get(k) for k in ('period_start','period_end')))


def derive(metric, inputs, calculate, unit=None, periods=True):
    if not inputs or any(v['status'] != 'READY' or v['value'] is None for v in inputs):
        return unavailable(metric)
    if any(not compatible(inputs[0], v, periods) for v in inputs[1:]):
        return unavailable(metric, 'INCOMPATIBLE_CONTEXT')
    try:
        amount = calculate([Decimal(v['value']) for v in inputs])
        if not amount.is_finite():
            raise ValueError()
    except (ArithmeticError, ValueError):
        return unavailable(metric, 'INVALID_DENOMINATOR')
    result = {k: inputs[0][k] for k in CONTEXT + ('period_start','period_end','period_type')}
    if inputs[0].get('ownership') is not None:result['ownership']=inputs[0]['ownership']
    result.update(definition_id=metric,value=str(amount),unit=unit or result['unit'],status='READY',origin='DERIVED',
                  known_at=derived_known_at(v['known_at'] for v in inputs),source_ids=list(dict.fromkeys(s for v in inputs for s in v['source_ids'])),
                  calculation_version=VERSION,reason_codes=[])
    result['input_ids']=[envelope(v)['id'] for v in inputs]
    result['input_contexts']=[{k:v.get(k) for k in ('definition_id','unit','currency','period_start','period_end','period_type','scope','accounting_basis','restatement_basis','known_at','status','scale')} for v in inputs]
    return envelope(result)


def load(root, ticker, origin):
    with database(root) as db:
        issuer = db.execute('SELECT name FROM issuers WHERE ticker=?', (ticker,)).fetchone()
        calendars = [json.loads(r[0]) for r in db.execute('SELECT payload FROM calendars WHERE ticker=?', (ticker,))]
        raw = [json.loads(r[0]) for r in db.execute('SELECT payload FROM facts WHERE ticker=?', (ticker,))]
    facts = {}
    for fact in raw:
        if not eligible_at_origin(fact['known_at'],origin.isoformat()):
            continue
        key = tuple(fact[k] for k in ('definition_id','period_type','period_start','period_end') + CONTEXT)
        if key not in facts or instant(fact['known_at']) > instant(facts[key]['known_at']):
            facts[key] = fact
        elif instant(fact['known_at']) == instant(facts[key]['known_at']) and fact['id'] != facts[key]['id']:
            facts[key] = dict(fact, value=None, status='WITHHELD', reason_codes=['AMBIGUOUS_REVISION'])
    return {'ticker':ticker,'name':issuer[0] if issuer else ticker}, calendars, list(facts.values())


def positive_ratio(numerator, denominator):
    if denominator <= 0:
        raise ValueError('Positive denominator required.')
    return numerator/denominator


def select(facts, metric, kind, end, start=None):
    matches = [v for v in facts if v['definition_id'] == metric and v['period_type'] == kind and v['period_end'] == end and (start is None or v['period_start'] == start)]
    if len(matches) != 1:
        return unavailable(metric, 'AMBIGUOUS_CONTEXT' if len(matches) > 1 else 'MISSING_COMPATIBLE_FACTS')
    return {k:v for k,v in matches[0].items() if k not in ('reviewer','raw_value')}


def period_fact(facts, calendars, metric, kind, end):
    if metric == 'ebitda':
        ebit = period_fact(facts,calendars,'ebit',kind,end)
        da = period_fact(facts,calendars,'da_expense',kind,end)
        if da['status']=='READY' and not all(next((f for f in facts if f['id']==s),{}).get('da_eligible') is True for s in da['source_ids']):
            return unavailable(metric,'DA_NOT_VERIFIED_AS_EBIT_EXPENSE')
        return derive(metric,[ebit,da],lambda v:v[0]+v[1])
    if metric in STOCK:
        return select(facts,metric,'INSTANT',end)
    direct = select(facts,metric,kind,end)
    if kind != 'TTM' and (direct['status'] == 'READY' or direct['reason_codes'] != ['MISSING_COMPATIBLE_FACTS']):
        return direct
    cal = next((c for c in calendars if end in c['quarter_ends']), None)
    if kind == 'Q' and cal and metric in FLOW:
        index = cal['quarter_ends'].index(end)
        current = select(facts,metric,'YTD',end,cal['start'])
        if index == 0:
            if current['status'] == 'READY':
                current.update(origin='DERIVED',input_ids=[current['id']])
                current.pop('id',None)
                current['period_type'] = 'Q'
                if current.get('period_context'):current['period_context']={**current['period_context'],'basis':'Q'}
            return current
        prior_end = cal['quarter_ends'][index-1]
        prior = select(facts,metric,'YTD',prior_end,cal['start'])
        if index == 1 and prior['status']!='READY':
            prior = select(facts,metric,'Q',prior_end,cal['start'])
        result = derive(metric,[current,prior],lambda v:v[0]-v[1],periods=False)
        if result['status'] == 'READY':
            result.pop('id',None)
            result.update(period_start=quarter_start(cal,index),period_end=end,period_type='Q')
        return result
    if kind == 'TTM' and metric in FLOW:
        if cal:
            index = cal['quarter_ends'].index(end)
            if index == 3:
                annual = select(facts,metric,'FY',end,cal['start'])
                if annual['status']=='READY':
                    annual.update(origin='DERIVED',input_ids=[annual['id']])
                    annual.pop('id',None)
                    annual['period_type']='TTM'
                    if annual.get('period_context'):annual['period_context']={**annual['period_context'],'basis':'TTM'}
                    return annual
            previous = next((c for c in calendars if date.fromisoformat(c['end'])+timedelta(days=1)==date.fromisoformat(cal['start'])),None)
            if previous:
                annual = select(facts,metric,'FY',previous['end'],previous['start'])
                current = select(facts,metric,'YTD',end,cal['start'])
                prior = select(facts,metric,'YTD',previous['quarter_ends'][index],previous['start'])
                bridged = derive(metric,[annual,current,prior],lambda v:v[0]+v[1]-v[2],periods=False)
                if bridged['status']=='READY':
                    bridged.pop('id',None)
                    bridged.update(period_start=(date.fromisoformat(prior['period_end'])+timedelta(days=1)).isoformat(),period_end=end,period_type='TTM')
                    return bridged
        boundaries = sorted({e for c in calendars for e in c['quarter_ends'] if e <= end})[-4:]
        if len(boundaries) != 4 or boundaries[-1] != end:
            return unavailable(metric,'INCOMPLETE_TTM')
        quarters = [period_fact(facts,calendars,metric,'Q',e) for e in boundaries]
        if any(q['status'] != 'READY' for q in quarters) or not contiguous(quarters):
            return unavailable(metric,'INCOMPLETE_TTM')
        result = derive(metric,quarters,lambda v:sum(v),periods=False)
        if result['status'] == 'READY':
            result.pop('id',None)
            result.update(period_start=quarters[0]['period_start'],period_end=end,period_type='TTM')
        return result
    return direct


def company(root, ticker, kind='TTM', end=None, origin=None):
    if kind not in ('Q','YTD','FY','TTM'):
        raise ValueError('Choose Q, YTD, FY or TTM.')
    origin = instant(origin) if origin else datetime.now(timezone.utc)
    if origin > datetime.now(timezone.utc):
        raise ValueError('Future research origin is not permitted.')
    identity, calendars, facts = load(root,ticker.upper(),origin)
    ends = sorted({v['period_end'] for v in facts if v['period_type'] != 'INSTANT' and (kind != 'FY' or v['period_type']=='FY')})
    end = end or (ends[-1] if ends else None)
    if end is not None:
        date.fromisoformat(end)
    values = {m:period_fact(facts,calendars,m,kind,end) for m in DEFINITIONS} if end else {m:unavailable(m) for m in DEFINITIONS}
    da = values['da_expense']
    if da['status'] == 'READY' and not all(next((f for f in facts if f['id']==s), {}).get('da_eligible') is True for s in da['source_ids']):
        da = unavailable('da_expense','DA_NOT_VERIFIED_AS_EBIT_EXPENSE')
    if da['status']=='READY' and Decimal(da['value'])<0:
        da = unavailable('da_expense','NEGATIVE_DA_REQUIRES_EXPLICIT_POSITIVE_ADDBACK_CONVENTION')
    values['ebitda'] = derive('ebitda',[values['ebit'],da],lambda v:v[0]+v[1])
    for name, numerator, denominator in [('net_margin','net_income','revenue'),('ebitda_margin','ebitda','revenue'),('cfo_margin','cfo','revenue'),('cash_conversion','cfo','net_income')]:
        values[name] = derive(name,[values[numerator],values[denominator]],lambda v:v[0]/v[1]*100,unit='%')
    for name,num,den in [('current_ratio','current_assets','current_liabilities'),('debt_equity','debt','equity')]:
        values[name] = derive(name,[values[num],values[den]],lambda v:v[0]/v[1],unit='x')
    values['working_capital'] = derive('working_capital',[values['current_assets'],values['current_liabilities']],lambda v:v[0]-v[1])
    for name, income, balance in [('roa','net_income','assets'),('roe','net_income_common','common_equity')]:
        flow = values[income]
        opening_date = (date.fromisoformat(flow['period_start'])-timedelta(days=1)).isoformat() if flow['status']=='READY' else None
        opening = select(facts,balance,'INSTANT',opening_date)
        closing = values[balance]
        result = derive(name,[flow,opening,closing],lambda v:positive_ratio(v[0],(v[1]+v[2])/2)*100,unit='%',periods=False)
        values[name] = returns_period(result,flow)
    annual_ebit = values['ebitda'] if kind in ('FY','TTM') else unavailable('ebitda','ANNUAL_DENOMINATOR_REQUIRED')
    values['debt_ebitda'] = derive('debt_ebitda',[values['debt'],annual_ebit],lambda v:positive_ratio(v[0],v[1]),unit='x',periods=False)
    if values['debt_ebitda']['status']=='READY':
        values['debt_ebitda'].update(period_start=annual_ebit['period_start'],period_end=annual_ebit['period_end'],period_type=kind)
    # EPS uses common profit and weighted-average shares, never subtracted YTD EPS.
    ni, shares = values['net_income_common'], values['weighted_average_shares']
    if ni['status']=='READY' and shares['status']=='READY':
        adjusted = dict(shares,unit='currency')
        values['eps'] = derive('eps',[ni,adjusted],lambda v:positive_ratio(v[0],v[1]),unit='currency/share')
    else:
        values['eps'] = unavailable('eps')
    relations = []
    for label, metric in [('Revenue vs income','net_margin'),('Earnings vs cash','cash_conversion'),('Debt vs annual EBITDA','debt_ebitda')]:
        relations.append({'label':label,'metric':metric,'result':values[metric]})
    capital_sales=derive('working_capital_sales',[values['working_capital'],values['revenue']],lambda v:v[0]/v[1]*100,unit='%',periods=False)
    if capital_sales['status']=='READY':
        capital_sales.update(period_start=values['revenue']['period_start'],period_type=kind)
    relations.append({'label':'Working capital vs sales','metric':'working_capital_sales','result':capital_sales})
    values={key:envelope(annotate(value)) for key,value in values.items()}
    cal=next((c for c in calendars if end in c['quarter_ends']),None)
    previous=next((c for c in calendars if cal and date.fromisoformat(c['end'])+timedelta(days=1)==date.fromisoformat(cal['start'])),None)
    prior={}
    if previous:
        prior_end=previous['quarter_ends'][cal['quarter_ends'].index(end)]
        prior={key:period_fact(facts,calendars,key,kind,prior_end) for key in ('revenue','net_income')}
        prior['net_margin']=derive('net_margin',[prior['net_income'],prior['revenue']],lambda v:positive_ratio(v[0],v[1])*100,unit='%')
        prior['working_capital']=derive('working_capital',[period_fact(facts,calendars,'current_assets',kind,prior_end),period_fact(facts,calendars,'current_liabilities',kind,prior_end)],lambda v:v[0]-v[1])
    quality=screen(values,prior)
    relations=[{**r,'result':envelope(r['result'])} for r in relations]
    return {'version':1,'contract_version':'a01-v1','mode':'reviewed','company':identity,'period':kind,'period_end':end,'available_ends':ends,
            'origin':origin.isoformat(),'status':'READY' if any(v['status']=='READY' for v in values.values()) else 'UNAVAILABLE',
            'metrics':values,'quality':quality,'summary':relations,'series':{m:[envelope(period_fact(facts,calendars,m,kind,e)) for e in ends] for m in ('revenue','net_income','ebitda','cfo')}}


def compare(root,tickers,kind,end=None):
    origin=datetime.now(timezone.utc).isoformat()
    results = [company(root,t,kind,end,origin) for t in tickers]
    rows = []
    for metric in ('revenue','net_income','ebitda','cfo','net_margin','roa','roe','current_ratio','debt_ebitda','eps'):
        cells = [c['metrics'][metric] for c in results]
        ready = all(c['status']=='READY' for c in cells)
        comparable = ready and all(compatible(cells[0],c) and cells[0].get('period_type')==c.get('period_type') for c in cells[1:])
        rows.append({'definition_id':metric,'comparable':comparable,'reason_codes':[] if comparable else ['NOT_COMPARABLE_CONTEXT_OR_COVERAGE'], 'cells':cells})
    return {'version':1,'companies':[r['company'] for r in results],'period':kind,'rows':rows}


def evidence(root,fact_id):
    with database(root) as db:
        row = db.execute('SELECT payload FROM facts WHERE id=?',(fact_id,)).fetchone()
        if not row:
            return None
        fact = json.loads(row[0])
        if instant(fact['known_at']) > datetime.now(timezone.utc):
            return None
        report = json.loads(db.execute('SELECT payload FROM reports WHERE id=?',(fact['report_id'],)).fetchone()[0])
        excerpt=None
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='finance_source_excerpts'").fetchone():
            row=db.execute('SELECT payload FROM finance_source_excerpts WHERE fact_id=?',(fact_id,)).fetchone()
            if row:
                citation=json.loads(row[0]);excerpt={k:citation.get(k) for k in ('section_id','page','page_kind','table','tag','row','column','excerpt','row_context','column_context','source_hash','parser_version','ownership')}
    # Reviewed financial citation only; never expose the admin original or storage path.
    return envelope({k:fact[k] for k in ('id','ticker','definition_id','value','unit','currency','period_start','period_end','period_type','scope','accounting_basis','restatement_basis','revision','known_at','accepted_at','evidence','origin','status')} | {'report_id':report['id'],'published_at':report['published_at'],'indexed_at':report['indexed_at'],'source_hash':report.get('source_hash'),'parser_version':report.get('parser_version'),'source_excerpt':excerpt,'source_url':report.get('source_url'),'source_kind':report.get('source_kind'),'source_line_label':fact.get('source_line_label')} | {'source_ids':fact.get('source_ids',[fact['id']]),'calculation_version':fact.get('calculation_version',VERSION),'reason_codes':fact.get('reason_codes',[]),'scale':fact.get('scale','1')})
