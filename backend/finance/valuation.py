"""A07 dated valuation cross-checks and fresh-quote gap gate."""
import json
import sqlite3
from decimal import Decimal
from datetime import datetime,timezone
from common.time import instant

FAMILIES={'FCFF':'OPERATING_CASHFLOW','FCFE':'OPERATING_CASHFLOW','P/E':'NORMALIZED_EARNINGS_MULTIPLE','DDM':'DIVIDEND','Gordon':'DIVIDEND','Asset-based':'ADJUSTED_ASSETS'}

def quote_gap(db,ticker,valuation_date,zone,methods,now=None):
    try:return _quote_gap(db,ticker,valuation_date,zone,methods,now)
    except (sqlite3.Error,ValueError,KeyError,TypeError,ArithmeticError):return {'status':'UNAVAILABLE','reason':'INVALID_OR_UNAVAILABLE_QUOTE_CONTEXT','price':None,'methods':[]}

def _quote_gap(db,ticker,valuation_date,zone,methods,now=None):
    now=now or datetime.now(timezone.utc)
    missing=lambda reason:{'status':'UNAVAILABLE','reason':reason,'price':None,'methods':[]}
    if valuation_date!=now.astimezone(zone).date():return missing('HISTORICAL_VALUATION_REQUIRES_POINT_IN_TIME_QUOTE')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='trading_instruments'").fetchone():return missing('NO_VERIFIED_FRESH_COMPANY_QUOTE')
    row=db.execute('SELECT payload FROM trading_instruments WHERE ticker=?',(ticker,)).fetchone()
    if not row:return missing('NO_VERIFIED_FRESH_COMPANY_QUOTE')
    rules=json.loads(row[0]);q=rules['quote'];asof=instant(q['as_of']);opened=instant(q['session_open']);closed=instant(q['session_close'])
    price=Decimal(str(q['price']))
    if not price.is_finite() or price<=0:return missing('INVALID_QUOTE_PRICE')
    if not opened<=asof<=now<=closed or asof.astimezone(zone).date()!=valuation_date:return missing('QUOTE_DATE_OR_SESSION_MISMATCH')
    if (now-asof).total_seconds()>float(q['max_age_seconds']):return missing('QUOTE_EXPIRED')
    values=[]
    for m in methods:
        if m['status']=='READY' and m['currency']==rules['currency']:
            values.append({'method':m['method'],'status':'READY','value':str(Decimal(m['value'])/price-1),'unit':'fraction','source_ids':m['source_ids'],
                'model_family':FAMILIES[m['method']]})
    if not values:return missing('NO_ELIGIBLE_SAME_CURRENCY_VALUE')
    return {'status':'READY','reason':None,'price':str(price),'currency':rules['currency'],'quote_as_of':q['as_of'],'source':rules['source'],'instrument_version':rules['version'],
        'methods':values,'policy':'METHOD_SPECIFIC_GAPS_NO_AVERAGED_FAIR_VALUE'}
