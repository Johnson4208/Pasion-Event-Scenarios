"""Vietnamese daily chart replay for the admin lab. No live routing or account access."""
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from market import technical
import feasibility
import stock_models

SECTORS = {'FPT': 'Technology', 'HPG': 'Materials', 'MWG': 'Retail', 'PNJ': 'Retail', 'VCB': 'Banks'}
SOURCE = 'DNSE / Entrade · daily OHLCV · 2023–2025'
STRATEGY = 'vn-replay-v1'
PROFILES = ('Cân bằng', 'Thận trọng', 'Động lượng')


@lru_cache(maxsize=len(SECTORS))
def tape(symbol):
    bars = []
    path = Path(__file__).with_name('replay_data') / (symbol + '.csv')
    with path.open(encoding='ascii', newline='') as file:
        for row in csv.DictReader(file):
            close_time = row['date'] + 'T08:00:00+00:00'
            bars.append({k: int(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')}
                        | dict(date=row['date'], as_of=close_time, known_at=close_time))
    # The VSA engine emits causal, dated events, including follow-through on its own date.
    by_date = defaultdict(list)
    for event in technical.events(symbol, bars):
        by_date[event['observed_at'][:10]].append(event['rule'])
    return bars, {bar['date']: i for i, bar in enumerate(bars)}, by_date


@lru_cache(maxsize=731)
def session(day):
    """History ends at the previous close. The opening quote is only used by execution."""
    signals, opens = {}, {}
    for symbol in SECTORS:
        bars, indices, events = tape(symbol)
        index = indices.get(day)
        if index is None or index < 60:
            continue
        history = bars[:index]
        prior = history[-1]
        values = technical.indicators(history)
        _, momentum, trend, volatility = stock_models.features(history, len(history) - 1)
        signals[symbol] = dict(symbol=symbol, as_of=prior['date'], close=prior['close'],
                               rsi=values['RSI14']['value'], atr=values['ATR14']['value'],
                               rvol=values['RVOL20']['value'], sma20=values['SMA20']['value'],
                               momentum=momentum, trend=trend, volatility=volatility,
                               events=events.get(prior['date'], []))
        opens[symbol] = bars[index]['open']
    return signals, opens


def candidates_for(signals, profile):
    candidates = []
    for symbol, s in signals.items():
        # Lab ranking points, comparable across symbols within the same profile.
        trend_weight, momentum_weight, volatility_penalty = ((32, 24, 30), (22, 12, 85), (45, 55, 12))[profile]
        vsa = int('SPRING_FOLLOW_THROUGH' in s['events']) - int('UPTHRUST_CANDIDATE' in s['events'])
        utility = (50 + trend_weight*s['trend'] + momentum_weight*s['momentum']
                   - volatility_penalty*s['volatility'] + vsa + (s['rsi']-50)/50)
        suitable = s['volatility'] <= (0.055, 0.03, 0.09)[profile]
        candidates.append(dict(symbol=symbol, sector=SECTORS[symbol], suitable=suitable, data_status='READY',
                               horizon='5 sessions', utility_definition='lab profile score', utility_version=STRATEGY,
                               utility=round(utility, 4)))
    return candidates


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS paper_accounts(customer TEXT PRIMARY KEY,cash INTEGER,turnover INTEGER,trades INTEGER)')
    db.execute('CREATE INDEX IF NOT EXISTS paper_ranking ON paper_accounts(turnover DESC,customer)')
    db.execute('CREATE TABLE IF NOT EXISTS paper_positions(customer TEXT,symbol TEXT,quantity INTEGER,PRIMARY KEY(customer,symbol))')
    db.execute('''CREATE TABLE IF NOT EXISTS paper_fills(id INTEGER PRIMARY KEY, request TEXT UNIQUE,
                day TEXT, customer TEXT, symbol TEXT, side TEXT, quantity INTEGER, price INTEGER, signal_date TEXT,
                profile TEXT, prior_close INTEGER, sma20 REAL, rsi REAL)''')
    db.execute('CREATE INDEX IF NOT EXISTS paper_day ON paper_fills(day)')
    db.execute('''CREATE TABLE IF NOT EXISTS paper_symbols(symbol TEXT PRIMARY KEY,buys INTEGER,
                sells INTEGER,quantity INTEGER,notional INTEGER)''')


def trade(db, customer, profile, request, day, signals, opens, selection, initial_cash):
    """Run the same fractional-risk sizing used by Trade Planner against paper balances."""
    holdings = dict(db.execute('SELECT symbol,quantity FROM paper_positions WHERE customer=? AND quantity>0 ORDER BY symbol', (customer,)))
    # Prioritize reducing an existing position after weakness on the previous close.
    exits = [s for s in holdings if s in signals and signals[s]['close'] < signals[s]['sma20']]
    if exits:
        symbol, side = exits[0], 'SELL'
    elif selection and signals[selection]['close'] >= signals[selection]['sma20']:
        symbol, side = selection, 'BUY'
    else:
        return {'status':'WAIT_SIGNAL' if selection else 'NO_SELECTION'}
    quote = opens[symbol]
    signal = signals[symbol]
    opened = datetime.fromisoformat(day + 'T02:00:00+00:00')
    account = db.execute('SELECT cash FROM paper_accounts WHERE customer=?', (customer,)).fetchone()
    cash = account[0] if account else initial_cash
    equity = cash + sum(q*signals[s]['close'] for s,q in holdings.items() if s in signals)
    risk = (0.6, 0.35, 1.0)[profile]
    distance = min(quote-1, max(1, round(2*signal['atr'])))
    draft = dict(ticker=symbol, side=side, entry=quote, stop=quote-distance, target=quote+2*distance, risk=risk)
    rules = dict(currency='VND', venue='HOSE / PAPER', version=STRATEGY, tick=1, lot=100, fee_flat=0,
                 fee_per_share=0, fee_rate='0.001', sell_tax_rate=0, slippage_bps=0,
                 quote=dict(price=quote, as_of=opened.isoformat(), session_open=opened.isoformat(),
                            session_close=(opened+timedelta(hours=6)).isoformat(), max_age_seconds=3600))
    baseline = dict(status='REVIEWED', currency='VND', cash=cash, equity=equity, reserved_cash=0, sellable=holdings,
                    version='synthetic-cash', as_of=opened.isoformat(), expires_at=(opened+timedelta(hours=6)).isoformat())
    sizing = feasibility.calculate(draft, baseline, rules, opened)
    if sizing['status'] != 'READY':
        return {'status':sizing['reason_codes'][0], 'symbol':symbol}
    quantity = sizing['quantity']
    notional = quantity * quote
    # Bundled chart ticks and board lots make the model's 0.1% fee whole VND.
    balance = cash + (notional if side=='SELL' else -notional) - notional//1000
    db.execute('''INSERT INTO paper_accounts VALUES (?,?,?,1) ON CONFLICT(customer) DO UPDATE
                SET cash=excluded.cash,turnover=turnover+excluded.turnover,trades=trades+1''',(customer,balance,notional))
    db.execute('''INSERT INTO paper_positions VALUES (?,?,?) ON CONFLICT(customer,symbol)
                DO UPDATE SET quantity=quantity+excluded.quantity''',(customer,symbol,quantity if side=='BUY' else -quantity))
    db.execute('''INSERT INTO paper_fills(request,day,customer,symbol,side,quantity,price,signal_date,
                profile,prior_close,sma20,rsi) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
               (request,day,customer,symbol,side,quantity,quote,signal['as_of'],
                PROFILES[profile],signal['close'],signal['sma20'],signal['rsi']))
    db.execute('''INSERT INTO paper_symbols VALUES (?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET
                buys=buys+excluded.buys,sells=sells+excluded.sells,quantity=quantity+excluded.quantity,
                notional=notional+excluded.notional''',(symbol,int(side=='BUY'),int(side=='SELL'),quantity,notional))
    return dict(status='PAPER_FILL', side=side, symbol=symbol, quantity=quantity, price=quote, signal_date=signal['as_of'])


def records(db, sql, args=()):
    query = db.execute(sql, args)
    keys = [column[0] for column in query.description]
    return [dict(zip(keys,row)) for row in query]


def monitor(db, signals):
    symbols = records(db, 'SELECT * FROM paper_symbols ORDER BY notional DESC,symbol')
    return dict(source=SOURCE, strategy=STRATEGY, currency='VND', signals=signals, symbols=symbols,
                totals={key:sum(s[key] for s in symbols) for key in ('buys','sells','quantity','notional')},
                top_accounts=records(db, 'SELECT customer,cash,turnover,trades FROM paper_accounts ORDER BY turnover DESC,customer LIMIT 10'),
                fills=records(db, 'SELECT * FROM paper_fills ORDER BY id DESC LIMIT 20'))
