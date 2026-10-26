"""Read-only admin monitoring. Manual portfolio observations are NOT broker fills.

Do not derive executed volume, trading rankings, or platform-wide tape volume
from manually entered transactions or shadow capacity slots.
"""
import json
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import distribution_shadow
import portfolio_ledger


def _number(v):
    try:
        n = Decimal(str(v))
        return n if n.is_finite() and n >= 0 else None
    except (ValueError, TypeError, InvalidOperation):
        return None


def overview(db, limit=12):
    distribution_shadow.initialize(db)
    portfolio_ledger.initialize(db)
    snapshot = distribution_shadow.state(db)
    totals=defaultdict(lambda:{'count':0,'quantity':Decimal(0),'notional':Decimal(0)})
    accounts=defaultdict(lambda:{'count':0,'notional':Decimal(0),'by_currency':defaultdict(Decimal)})
    symbols=defaultdict(lambda:{'count':0,'quantity':Decimal(0),'by_currency':defaultdict(Decimal)})
    count=0
    exclusions=Counter()
    for owner,raw in db.execute('SELECT owner,payload FROM portfolio_transactions'):
        try:
            item=json.loads(raw)
            side=item.get('type')
            if side not in ('BUY','SELL'):
                continue
            quantity=_number(item.get('quantity'))
            amount=_number(item.get('amount'))
            currency=item.get('currency')
            ticker=item.get('ticker')
            if quantity is None or amount is None or not isinstance(currency,str) or not ticker:
                exclusions['INCOMPLETE_MANUAL_RECORD']+=1
                continue
            count+=1
            total=totals[currency]
            total['count']+=1; total['quantity']+=quantity; total['notional']+=amount
            acc=accounts[owner]
            acc['count']+=1; acc['notional']+=amount; acc['by_currency'][currency]+=amount
            sym=symbols[ticker]
            sym['count']+=1; sym['quantity']+=quantity; sym['by_currency'][currency]+=amount
        except (ValueError,TypeError,KeyError):
            exclusions['INVALID_RECORD']+=1
    # Rankings MUST be grouped within a single currency: adding VND to USD is meaningless.
    ranking=[]
    for owner,acc in accounts.items():
        for currency,value in acc['by_currency'].items():
            # admin-only, masked reference; avoid displaying emails in analytics cards
            first=owner.split('@')[0]
            alias=(first[:2]+'***') if first else '***'
            ranking.append({'account_ref':alias,'account_id':owner,'currency':currency,'manual_notional':str(value),
                'manual_trade_records':acc['count'],'basis':'MANUAL_UNRECONCILED_NOT_EXECUTED'})
    ranking.sort(key=lambda a:(a['currency'],-Decimal(a['manual_notional']),a['account_id']))
    result={'version':1,'status':'READ_ONLY_RESEARCH_MONITOR', 'generated_at':datetime.now(timezone.utc).isoformat(),
      'broker_confirmed':{'status':'UNAVAILABLE','executed_quantity':None,'executed_notional':None,
        'top_executed_accounts':None,'reason_codes':['NO_VERIFIED_BROKER_FILL_FEED']},
      'manual_activity':{'status':'AVAILABLE_UNVERIFIED','trade_records':count,
        'by_currency':[{'currency':c,'count':v['count'],'quantity':str(v['quantity']), 'notional':str(v['notional'])} for c,v in sorted(totals.items())],
        'top_accounts':ranking[:limit],
        'top_symbols':sorted([{'ticker':t,'record_count':v['count'],'quantity':str(v['quantity']),
          'by_currency':[{'currency':c,'notional':str(n)} for c,n in sorted(v['by_currency'].items())]} for t,v in symbols.items()],key=lambda o:-o['record_count'])[:limit],
        'excluded':dict(exclusions),
        'disclaimer':'User-entered BUY/SELL records only; no exchange volume, validated fills or executed trades.'},
      'distribution':{'status':snapshot['status'], 'pools':snapshot['pools'],
        'candidate_count':db.execute('SELECT COUNT(*) FROM distribution_candidates').fetchone()[0],
        'withheld_count':sum(1 for (p,) in db.execute('SELECT payload FROM distribution_candidates') if json.loads(p).get('status')=='WITHHELD'),
        'transition_count':db.execute('SELECT COUNT(*) FROM distribution_transitions').fetchone()[0],
        'recent_candidates':snapshot['candidates'][:limit],
        'recent_events':snapshot['events'][:limit],
        'capacity_basis':'SIMULATED_REVIEW_SLOTS_NOT_MARKET_SHARES',
        'live_allocations':None,'live_allocation_status':'WITHHELD_NOT_IMPLEMENTED'}}
    return result
