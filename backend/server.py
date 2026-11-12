"""Local demonstration API. Run: python backend/server.py"""
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sqlite3
import time
import threading
from collections import deque
from contextlib import contextmanager
from decimal import InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from mailer import MailUnavailable, mail_settings, send_reset_email
import document_service
import security
import market_summary
import finance_core
import public_filing_demo
import sec_filings
import financial_sources
import valuation
import stock_models
from market import technical
from market import outcomes
import feasibility
import portfolio_ledger
import macro_evidence
import event_research
import event_news_preview
import event_horizons
import event_agent_store
import event_forecasts
import event_series_forecasts
import event_forecast_ledger
import news_evidence
import finance_ingestion
import watch_events
import analytic_assistant
import distribution_shadow
import admin_distribution_analytics
import operational_health
from documents import DocumentError, MAX_FILE_SIZE, search_document

ROOT = Path(__file__).resolve().parent
SESSIONS = {}
EMAIL = os.environ.get('SOLVAI_EMAIL', 'demo@solvai.com')
PASSWORD = os.environ.get('SOLVAI_PASSWORD', 'SolvAI2024!')
PRODUCTION = os.environ.get('PASION_ENV') == 'production'
ADMIN_EMAIL = os.environ.get('PASION_ADMIN_EMAIL', '' if PRODUCTION else 'eyyubxankisiyev@gmail.com').casefold()
RESET_SECRET = secrets.token_bytes(32)
RESET_LOCK = threading.RLock()
RESET_LIMITS = {}
UPLOAD_READ_TIMEOUT = 30
DATABASE_CONTEXT = threading.local()


class ExclusiveHTTPServer(ThreadingHTTPServer):
    # Windows otherwise permits overlapping listeners and requests hit stale APIs.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def reset_hash(email, code):
    return hmac.digest(RESET_SECRET, (email + ':' + code).encode(), 'sha256')

@contextmanager
def database():
    db = sqlite3.connect(ROOT / 'accounts.sqlite3')
    db.execute('PRAGMA foreign_keys = ON')
    previous = getattr(DATABASE_CONTEXT, 'connection', None)
    DATABASE_CONTEXT.connection = db
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS accounts (email TEXT PRIMARY KEY, name TEXT NOT NULL, salt BLOB NOT NULL, password_hash BLOB NOT NULL)')
            columns = {row[1] for row in db.execute('PRAGMA table_info(accounts)')}
            if 'disabled' not in columns:
                db.execute('ALTER TABLE accounts ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0')
            if 'created' not in columns:
                db.execute('ALTER TABLE accounts ADD COLUMN created REAL')
            if 'is_admin' not in columns:
                db.execute('ALTER TABLE accounts ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY)')
            security.initialize(db)
            db.execute('CREATE TABLE IF NOT EXISTS password_resets (email TEXT PRIMARY KEY, code_hash BLOB NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, sent_at REAL NOT NULL, account_hash BLOB NOT NULL)')
            if not PRODUCTION and not db.execute("SELECT 1 FROM settings WHERE key = 'demo-initialized'").fetchone():
                salt = secrets.token_bytes(16)
                db.execute('INSERT OR IGNORE INTO accounts (email, name, salt, password_hash, created) VALUES (?, ?, ?, ?, ?)', (EMAIL.casefold(), 'Demo account', salt, password_hash(PASSWORD, salt), time.time()))
                db.execute("INSERT INTO settings VALUES ('demo-initialized')")
            yield db
    finally:
        DATABASE_CONTEXT.connection = previous
        db.close()

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000)

def is_admin_email(email):
    if email.casefold() == ADMIN_EMAIL:
        return True
    with database() as db:
        row = db.execute('SELECT is_admin FROM accounts WHERE email = ?', (email.casefold(),)).fetchone()
    return bool(row and row[0])

def account_profile(email):
    with database() as db:
        row = db.execute('SELECT name FROM accounts WHERE email = ?', (email.casefold(),)).fetchone()
    return {'name': row[0], 'email': email.casefold()} if row else None

class Handler(BaseHTTPRequestHandler):
    def event_forecast_api(self):
        if not self.current_session():
            self.respond(401, {'message': 'Please sign in again.'})
            return
        address = urlparse(self.path).path
        try:
            if self.command == 'GET':
                if address.endswith('/forecast-options'):
                    self.respond(200, {'version': 1, 'profiles': event_series_forecasts.options(),
                                      'policy': 'SOURCE_BACKED_RESEARCH_NOT_PROSPECTIVELY_CALIBRATED'})
                else:
                    self.respond(200, {'version': 1, **event_forecast_ledger.summary()})
                return
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 10000:
                raise ValueError()
            payload = json.loads(self.read_document_body(size))
            fields = {'category', 'factor', 'focus', 'horizon', 'basis'}
            if not isinstance(payload, dict) or set(payload) - fields:
                raise ValueError()
            context = {key: payload.get(key, 'END_STATE' if key == 'basis' else 'World' if key == 'focus' else '')
                       for key in fields}
            if any(not isinstance(value, str) for value in context.values()):
                raise ValueError()
            context['focus'] = context['focus'].strip() or 'World'
            if context['factor'] not in event_news_preview._TOPICS.get(context['category'], {}):
                raise ValueError()
            if context['basis'] not in event_forecasts.BASES:
                raise ValueError()
            horizon_info = event_horizons.info(context['horizon'])
            event_news_preview.event_feed_sources.geography(context['focus'])
            model = event_forecasts.forecast(**context)
            if model.get('status') != 'REFERENCE_ESTIMATE_AVAILABLE':
                model = event_series_forecasts.prepare(**context)
            ready = model.get('status') in ('REFERENCE_ESTIMATE_AVAILABLE', 'RESEARCH_ESTIMATE_AVAILABLE')
            recording = {'status': 'NOT_RECORDED'}
            if model.get('status') == 'RESEARCH_ESTIMATE_AVAILABLE':
                try:
                    recording = event_forecast_ledger.record(model)
                except (ValueError, OSError, sqlite3.Error):
                    recording = {'status': 'RECORDING_UNAVAILABLE'}
                else:
                    try:
                        event_forecast_ledger.resolve_due()
                    except (ValueError, OSError, sqlite3.Error):
                        recording['resolution_status'] = 'TEMPORARILY_UNAVAILABLE'
            self.respond(200, {'version': 1, **context,
                              'status': 'FORECAST_AVAILABLE' if ready else 'UNAVAILABLE',
                              'generated_at': model.get('as_of') or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                              'scenario_forecast': model, 'forecast_recording': recording,
                              'horizon_info': horizon_info, 'evidence_status': 'NOT_REQUESTED',
                              'items': [], 'outcomes': [], 'source_count': 0,
                              'dynamic_scenarios': {'ranked_scenarios': []},
                              'coverage': {'status': 'NOT_REQUESTED'}, 'calibrated_probability': False})
        except (ValueError, KeyError, TypeError, AttributeError, DocumentError):
            self.respond(400, {'message': 'Select a supported forecast question, region and horizon.'})
        except (OSError, sqlite3.Error):
            self.respond(503, {'message': 'Forecast preparation is temporarily unavailable. Existing data was preserved.'})

    def trade_outcomes_api(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=10000:raise ValueError()
            data=json.loads(self.read_document_body(size));ticker=data['ticker']
            if not re.fullmatch('[A-Z0-9.-]{1,16}',ticker):raise ValueError()
            if not isinstance(data['origins'],list) or not 1<=len(data['origins'])<=200 or len(set(data['origins']))!=len(data['origins']):raise ValueError()
            snapshot=technical.analyze(ROOT,ticker)
            if snapshot['status'] not in ('READY','STALE'):
                self.respond(200,{'version':1,'status':'UNAVAILABLE','reason_codes':['REVIEWED_COMPLETE_OHLCV_REQUIRED']});return
            paths=[outcomes.first_touch(snapshot['bars'],i,data['horizon'],data['stop'],data['target'],data.get('direction','Long'),data['fee_rate'],data['fixed_fee'],data['slippage_bps'],data['quantity']) for i in data['origins']]
            self.respond(200,{'version':1,'status':'RETROSPECTIVE_SCENARIO','ticker':ticker,'paths':paths,'summary':outcomes.summarize(paths),'source_as_of':snapshot['as_of'],'source_ids':[snapshot.get('snapshot_id') or snapshot.get('snapshot_hash') or snapshot['as_of']],'execution_policy':'NO_ORDER_OR_VALIDATED_EDGE'})
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Invalid completed-path scenario or explicit cost assumptions.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Historical path research unavailable.'})

    def distribution_api(self):
        if not self.require_admin():return
        try:
            with database() as db:
                distribution_shadow.initialize(db)
                db.commit()
                # Serialize capacity read/check/write and retries in the same SQLite transaction.
                db.execute('BEGIN IMMEDIATE')
                if self.command=='GET':result=admin_distribution_analytics.overview(db) if urlparse(self.path).path.endswith('/monitor') else distribution_shadow.state(db)
                else:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=50000:raise ValueError()
                    data=json.loads(self.read_document_body(size));path=urlparse(self.path).path
                    result=distribution_shadow.pool(db,data) if path.endswith('/pools') else distribution_shadow.candidate(db,ROOT,data) if path.endswith(('/candidates','/shadow')) else distribution_shadow.transition(db,data)
            self.respond(200,result)
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Shadow gates, capacity or transition verification failed.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Shadow Distribution unavailable.'})

    def assistant_api(self):
        session=self.current_session()
        if not session:self.respond(401,{'message':'Please sign in again.'});return
        owner=session['email'].casefold()
        if not analytic_assistant.permit(owner):self.respond(429,{'message':'Assistant query limit reached. Try again in a minute.'});return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=10000:raise ValueError()
            data=json.loads(self.read_document_body(size))
            with database() as db:result=analytic_assistant.answer(ROOT,db,owner,data)
            self.respond(200,result)
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Select a supported read-only finance tool, issuer and period.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Reviewed assistant context unavailable.'})

    def watch_api(self):
        session=self.current_session()
        if not session:self.respond(401,{'message':'Please sign in again.'});return
        try:
            with database() as db:
                owner=session['email'].casefold()
                if self.command=='GET':result=watch_events.read(db,owner)
                else:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=100000:raise ValueError()
                    data=json.loads(self.read_document_body(size));path=urlparse(self.path).path
                    result=watch_events.evaluate(db,owner) if path.endswith('/evaluate') else watch_events.acknowledge(db,owner,data) if path.endswith('/acknowledge') else watch_events.save(db,owner,data)
            self.respond(200,result)
        except (ValueError,KeyError,TypeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Invalid watch intent, consent, alert units or acknowledgment.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Watch event service unavailable.'})

    def finance_stage_api(self):
        if not self.require_admin():return
        try:
            if self.command=='GET':
                query=parse_qs(urlparse(self.path).query);document_id=query.get('document_id',[''])[0]
                result=finance_ingestion.observations(ROOT,document_id) if urlparse(self.path).path.endswith('/observations') else finance_ingestion.history(ROOT,document_id)
            else:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2_000_000:raise ValueError()
                data=json.loads(self.read_document_body(size));reviewer=self.current_session()['email'].casefold()
                result=finance_ingestion.decide(ROOT,data,reviewer) if urlparse(self.path).path.endswith('/decide') else finance_ingestion.stage(ROOT,data,reviewer)
            self.respond(200,result)
        except sqlite3.IntegrityError:self.respond(409,{'message':'Financial revision or review decision already exists.'})
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Invalid staged observation, source coordinates, accounting context or review decision.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Financial ingestion unavailable.'})

    def news_api(self):
        session=self.current_session()
        if not session:self.respond(401,{'message':'Please sign in again.'});return
        path=urlparse(self.path).path
        try:
            with database() as db:
                if self.command=='GET':
                    query=parse_qs(urlparse(self.path).query)
                    result=news_evidence.review_queue(db) if path=='/api/admin/news/proposals' else news_evidence.proposals(db,session['email'].casefold()) if path.endswith('/proposals') else news_evidence.feed(db,session['email'].casefold(),query.get('origin',[None])[0])
                else:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=200000:raise ValueError()
                    data=json.loads(self.read_document_body(size))
                    if path.startswith('/api/admin/'):
                        if not self.require_admin():return
                        action={'sources':news_evidence.register,'ingest':news_evidence.ingest,'review':news_evidence.review,'decide':news_evidence.decide}[path.rsplit('/',1)[1]]
                        result=action(db,data)
                    elif path.endswith('/bookmarks'):result=news_evidence.bookmark(db,session['email'].casefold(),data)
                    else:result=news_evidence.propose(db,session['email'].casefold(),data)
            self.respond(200,result)
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Invalid permitted source, claim evidence, bookmark or supported driver proposal.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'News evidence storage unavailable.'})

    def event_api(self):
        session=self.current_session()
        if not session:self.respond(401,{'message':'Please sign in again.'});return
        path=urlparse(self.path).path
        try:
            with database() as db:
                if self.command=='GET':
                    query=parse_qs(urlparse(self.path).query)
                    result=event_research.evidence(db,query.get('origin',[None])[0]) if path.endswith('/evidence') else event_research.history(db,session['email'].casefold())
                else:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=200000:raise ValueError()
                    data=json.loads(self.read_document_body(size))
                    if path=='/api/admin/events/evidence':
                        if not self.require_admin():return
                        result=event_research.ingest(db,data)
                    elif path.endswith('/resolve'):result=event_research.resolve(db,session['email'].casefold(),data)
                    else:result=event_research.save(db,session['email'].casefold(),data)
            self.respond(200,result)
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Invalid event definition, weights, evidence cutoff or outcome maturity.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Event research storage unavailable.'})

    def macro_api(self):
        path=urlparse(self.path).path
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=500000:raise ValueError()
            data=json.loads(self.read_document_body(size))
            if path.startswith('/api/admin/'):
                if not self.require_admin():return
                result=macro_evidence.ingest(ROOT,data) if path.endswith('/observations') else macro_evidence.exposure(ROOT,data)
            else:result=macro_evidence.stress(ROOT,data)
            self.respond(200,result)
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError):self.respond(400,{'message':'Invalid reviewed vintage, exposure evidence or scenario units.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Macro evidence storage unavailable.'})

    def portfolio_write(self):
        session=self.current_session()
        if not session:self.respond(401,{'message':'Please sign in again.'});return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=500000:raise ValueError()
            data=json.loads(self.read_document_body(size))
            with database() as db:
                if urlparse(self.path).path=='/api/admin/portfolio/fx':
                    if not self.require_admin():return
                    result=portfolio_ledger.register_fx(db,data)
                elif urlparse(self.path).path=='/api/portfolio/transactions':result=portfolio_ledger.transaction(db,session['email'].casefold(),data)
                else:result=portfolio_ledger.save(db,session['email'].casefold(),data)
            self.respond(200,{'version':1,'state':result})
        except (RuntimeError,sqlite3.IntegrityError):self.respond(409,{'message':'Portfolio revision changed; refresh before saving.'})
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Invalid portfolio cash, lot, currency or source context.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Portfolio storage unavailable.'})

    def trade_api(self):
        session=self.current_session()
        if not session:self.respond(401,{'message':'Please sign in again.'});return
        path=urlparse(self.path).path
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=100000:raise ValueError()
            data=json.loads(self.read_document_body(size))
            with database() as db:
                if path=='/api/admin/trades/instruments':
                    if not self.require_admin():return
                    if not re.fullmatch('[A-Z0-9.-]{1,16}',data['ticker']):raise ValueError()
                    result=feasibility.instrument(db,data)
                elif path=='/api/admin/portfolio/review':
                    if not self.require_admin():return
                    feasibility.review_account(db,data['owner'].casefold());result={'status':'REVIEWED'}
                elif path=='/api/portfolio/baseline':
                    result=feasibility.baseline(db,session['email'].casefold(),data)
                else:
                    if not re.fullmatch('[A-Z0-9.-]{1,16}',data['ticker']):raise ValueError()
                    result=feasibility.for_owner(db,session['email'].casefold(),data)
            self.respond(200,result)
        except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,DocumentError):self.respond(400,{'message':'Invalid trade, account or instrument state.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Trade feasibility storage unavailable.'})

    def technical_ingest(self):
        if not self.require_admin():return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8_000_000:raise ValueError()
            data=json.loads(self.read_document_body(size));ticker=data['ticker'].upper()
            if not re.fullmatch('[A-Z0-9.-]{1,16}',ticker):raise ValueError()
            self.respond(201,technical.ingest(ROOT,ticker,data))
        except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,DocumentError):
            self.respond(400,{'message':'Invalid OHLCV, source, sessions or corporate-action policy.'})
        except (sqlite3.Error,OSError):self.respond(503,{'message':'Technical data storage unavailable.'})

    def stock_model_admin(self):
        if not self.require_admin():
            return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8_000_000:
                raise ValueError()
            data=json.loads(self.read_document_body(size))
            if urlparse(self.path).path=='/api/admin/market/models/freeze':
                ticker=data['ticker'].upper()
                if not re.fullmatch('[A-Z0-9.-]{1,16}',ticker) or data.get('provider_verified') is not True:
                    raise ValueError()
                result=stock_models.freeze(ROOT,ticker,data['horizon_sessions'],data['bars'],data['source'])
            else:
                result=stock_models.evaluate(ROOT,data['model_id'],data['bars'])
            self.respond(200,result)
        except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,DocumentError):
            self.respond(400,{'message':'Invalid completed sessions or model validation inputs.'})
        except (sqlite3.Error,OSError):
            self.respond(503,{'message':'Stock model storage is unavailable.'})

    def valuation_api(self):
        session=self.current_session()
        if not session:
            self.respond(401,{'message':'Please sign in again.'})
            return
        owner=session['email'].casefold()
        path=urlparse(self.path).path
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=100000:
                raise ValueError()
            data=json.loads(self.read_document_body(size))
            if not isinstance(data,dict):
                raise ValueError()
            with database() as db:
                if path=='/api/admin/finance/assumptions/review':
                    if not self.require_admin():
                        return
                    target=data['owner'].strip().casefold()
                    ids=data['assumption_ids']
                    if not isinstance(ids,list) or not 1<=len(ids)<=50 or not all(isinstance(v,str) for v in ids):
                        raise ValueError()
                    valuation.review(db,ROOT,target,ids)
                    result={'reviewed':len(ids)}
                else:
                    ticker=data['ticker'].upper()
                    if not re.fullmatch('[A-Z0-9.-]{1,16}',ticker):
                        raise ValueError()
                    if path=='/api/research/assumptions':
                        result={'version':1,'assumptions':valuation.register(db,owner,ticker,data.get('scenario','base'),data['assumptions'])}
                    else:
                        result=valuation.calculate(db,ROOT,owner,data)
            self.respond(200,result)
        except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,DocumentError):
            self.respond(400,{'message':'Invalid valuation assumptions, review evidence or valuation date.'})
        except (sqlite3.Error,OSError):
            self.respond(503,{'message':'Valuation storage is unavailable.'})

    def finance_ingest(self):
        if not self.require_admin():
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2_000_000:
                raise ValueError()
            payload = json.loads(self.read_document_body(size))
            if not isinstance(payload, dict) or not isinstance(payload.get('reports'), list):
                raise ValueError()
            for report in payload['reports']:
                document = document_service.get_document(ROOT, report['document_id'])
                if document['status'] != 'ready':
                    raise ValueError('Source document must be ready.')
                _, original = document_service.get_original(ROOT, report['document_id'])
                report['source_hash'] = hashlib.sha256(original).hexdigest()
                report['parser_version'] = 'pasion-document-service-v1'
            count = finance_core.ingest(ROOT,payload,self.current_session()['email'].casefold())
            self.respond(201, {'accepted':count,'message':'Reviewed financial facts accepted.'})
        except sqlite3.IntegrityError:
            self.respond(409, {'message':'Fact or report identity already exists. Submit a new revision identity.'})
        except (ValueError, TypeError, KeyError, InvalidOperation, DocumentError):
            self.respond(400, {'message':'Invalid reviewed financial facts, fiscal calendar or source document.'})
        except (sqlite3.Error, OSError):
            self.respond(503, {'message':'Financial storage is unavailable.'})

    def finance_research(self):
        if not self.current_session():
            self.respond(401, {'message':'Please sign in again.'})
            return
        address = urlparse(self.path)
        query = parse_qs(address.query)
        try:
            if address.path == '/api/research/compare':
                tickers = query.get('tickers',[''])[0].split(',')
                if not 1 <= len(tickers) <= 4 or not all(re.fullmatch('[A-Za-z0-9.-]{1,16}',t) for t in tickers):
                    raise ValueError()
                result = finance_core.compare(ROOT,tickers,query.get('period',['TTM'])[0],query.get('end',[None])[0])
            elif address.path.startswith('/api/research/company/'):
                ticker = address.path.removeprefix('/api/research/company/')
                if not re.fullmatch('[A-Za-z0-9.-]{1,16}',ticker):
                    raise ValueError()
                result = finance_core.company(ROOT,ticker,query.get('period',['TTM'])[0],query.get('end',[None])[0],query.get('origin',[None])[0])
            else:
                fact_id = unquote(address.path.split('/')[4])
                result = finance_core.evidence(ROOT,fact_id)
                if result is None:
                    self.respond(404, {'message':'Reviewed evidence not found.'})
                    return
            self.respond(200,result)
        except (ValueError, KeyError, TypeError):
            self.respond(400, {'message':'Invalid research period or company request.'})
        except (sqlite3.Error, OSError):
            self.respond(503, {'message':'Financial research storage is unavailable.'})

    def log_message(self, format, *args):
        # Default HTTP logging records query strings, which can contain private searches.
        pass

    def policy_guard(self):
        policy = security.route_policy(urlparse(self.path).path)
        if not policy:
            return True
        if policy == 'admin':
            return self.require_admin()
        if not self.current_session():
            self.respond(401, {'message': 'Please sign in again.'})
            return False
        return True

    def read_document_body(self, size):
        deadline = time.monotonic() + UPLOAD_READ_TIMEOUT
        previous_timeout = self.connection.gettimeout()
        chunks = []
        remaining = size
        try:
            while remaining:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise TimeoutError()
                self.connection.settimeout(budget)
                chunk = self.rfile.read1(min(65536, remaining))
                if not chunk:
                    self.close_connection = True
                    raise DocumentError('The document upload did not finish. Please try again.')
                chunks.append(chunk)
                remaining -= len(chunk)
        except TimeoutError:
            self.close_connection = True
            raise DocumentError('The document upload timed out. Check your connection and try again.', 408)
        finally:
            self.connection.settimeout(previous_timeout)
        return b''.join(chunks)

    def admin_documents(self, method):
        if not self.require_admin():
            return
        address = urlparse(self.path)
        segments = address.path.rstrip('/').split('/')[4:]
        try:
            if not segments:
                if method == 'GET':
                    filters = parse_qs(address.query)
                    self.respond(200, {'documents': document_service.list_documents(
                        ROOT, file_type=filters.get('type', [''])[0], query=filters.get('q', [''])[0],
                        start=filters.get('from', [''])[0], end=filters.get('to', [''])[0],
                        order=filters.get('order', ['newest'])[0]),
                                       'capabilities': document_service.capabilities()})
                    return
                if method == 'POST':
                    if self.headers.get('Transfer-Encoding'):
                        raise DocumentError('Upload a document with a known file size.')
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                    except ValueError:
                        raise DocumentError('Invalid document upload.')
                    if not 0 < size <= MAX_FILE_SIZE:
                        raise DocumentError('Choose a document up to 10 MB.', 413)
                    filename = unquote(self.headers.get('X-Document-Name', ''))
                    content = self.read_document_body(size)
                    self.respond(202, {'document': document_service.save_upload(ROOT, filename, content)})
                    return
            elif len(segments) == 1:
                if method == 'GET':
                    self.respond(200, {'document': document_service.get_document(ROOT, segments[0])})
                    return
                if method == 'DELETE':
                    document_service.delete_document(ROOT, segments[0])
                    self.respond(200, {'message': 'Document deleted.'})
                    return
            elif len(segments) == 2:
                document = document_service.get_document(ROOT, segments[0])
                if method == 'GET' and segments[1] == 'download':
                    name, content = document_service.get_original(ROOT, segments[0])
                    with database() as db:
                        security.audit(db, self.current_session()['email'].casefold(), 'GET:admin.download', 200)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(name, safe=''))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    self.wfile.write(content)
                    return
                if method == 'POST' and segments[1] == 'retry':
                    self.respond(202, {'document': document_service.retry_document(ROOT, segments[0])})
                    return
                if segments[1] in ('search', 'ask') and document['status'] != 'ready':
                    raise DocumentError(document.get('error') or 'The document is still processing. Try again when it is ready.', 409)
                if method == 'GET' and segments[1] == 'search':
                    query = parse_qs(address.query).get('q', [''])[0].strip()
                    if not 1 <= len(query) <= 300:
                        raise DocumentError('Enter a search of 1 to 300 characters.')
                    self.respond(200, {'matches': search_document(document, query)})
                    return
                if method == 'POST' and segments[1] == 'ask':
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                        if not 0 < size <= 12000:
                            raise ValueError()
                        data = json.loads(self.read_document_body(size))
                        if not isinstance(data, dict):
                            raise ValueError()
                    except (ValueError, TypeError, UnicodeDecodeError):
                        raise DocumentError('Invalid document question.')
                    result = document_service.ask_document(document, data.get('question', ''), data.get('mode', 'answer'), data.get('language', 'en'))
                    self.respond(200, result)
                    return
            self.respond(404, {'message': 'Not found.'})
        except DocumentError as error:
            self.respond(error.status, {'message': str(error)})
        except (sqlite3.Error, OSError):
            self.respond(500, {'message': 'Unable to save or read the document. Please try again.'})

    def reset_password(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
            email = data.get('email')
            if not isinstance(email, str) or len(email) > 254:
                raise ValueError()
            email = email.strip().casefold()
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                raise ValueError()
        except (ValueError, TypeError, UnicodeDecodeError):
            self.respond(400, {'message': 'Please provide a valid email address.'})
            return
        requesting = self.path == '/api/forgot-password'
        with RESET_LOCK:
            now = time.time()
            for key, values in list(RESET_LIMITS.items()):
                while values and values[0] <= now - 600:
                    values.popleft()
                if not values:
                    RESET_LIMITS.pop(key, None)
            key = (self.client_address[0], requesting)
            events = RESET_LIMITS.setdefault(key, deque())
            if len(events) >= (10 if requesting else 30):
                self.respond(429, {'message': 'Too many attempts. Please try again in 10 minutes.'})
                return
            events.append(now)
            if requesting:
                try:
                    config = mail_settings(ROOT)
                except MailUnavailable as error:
                    self.respond(503, {'message': str(error)})
                    return
                with database() as db:
                    account = db.execute('SELECT password_hash, disabled FROM accounts WHERE email = ?', (email,)).fetchone()
                    previous = db.execute('SELECT sent_at FROM password_resets WHERE email = ?', (email,)).fetchone()
                    if previous and previous[0] > now - 60:
                        self.respond(429, {'message': 'Please wait 60 seconds before requesting another code.'})
                        return
                    if account and not account[1]:
                        code = f'{secrets.randbelow(1000000):06d}'
                        try:
                            send_reset_email(email, code, config)
                        except MailUnavailable as error:
                            self.respond(503, {'message': str(error)})
                            return
                        db.execute('INSERT OR REPLACE INTO password_resets (email, code_hash, expires, attempts, sent_at, account_hash) VALUES (?, ?, ?, 0, ?, ?)', (email, reset_hash(email, code), now + 600, now, account[0]))
                self.respond(200, {'message': 'If this email belongs to an active account, a six-digit code has been sent. Check your inbox and spam folder.'})
                return
            code = data.get('code')
            password = data.get('newPassword')
            if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
                self.respond(400, {'message': 'Enter the six-digit code from your email.'})
                return
            if not isinstance(password, str) or not 8 <= len(password) <= 1024:
                self.respond(400, {'message': 'Use a new password with 8 to 1024 characters.'})
                return
            if password != data.get('confirmPassword'):
                self.respond(400, {'message': 'Passwords do not match.'})
                return
            with database() as db:
                reset = db.execute('SELECT code_hash, expires, attempts, account_hash FROM password_resets WHERE email = ?', (email,)).fetchone()
                account = db.execute('SELECT password_hash, disabled FROM accounts WHERE email = ?', (email,)).fetchone()
                valid = bool(reset and account and not account[1] and reset[1] > now and reset[2] < 5 and hmac.compare_digest(reset[3], account[0]) and hmac.compare_digest(reset[0], reset_hash(email, code)))
                if not valid:
                    if reset:
                        db.execute('UPDATE password_resets SET attempts = attempts + 1 WHERE email = ?', (email,))
                    self.respond(400, {'message': 'The code is invalid or expired. Request a new code if needed.'})
                    return
                salt = secrets.token_bytes(16)
                result = db.execute('UPDATE accounts SET salt = ?, password_hash = ? WHERE email = ? AND disabled = 0 AND password_hash = ?', (salt, password_hash(password, salt), email, account[0]))
                if not result.rowcount:
                    self.respond(400, {'message': 'The code is no longer valid. Please request a new code.'})
                    return
                db.execute('DELETE FROM password_resets WHERE email = ?', (email,))
            for token, session in list(SESSIONS.items()):
                if session['email'].casefold() == email:
                    SESSIONS.pop(token, None)
            self.respond(200, {'message': 'Your password has been reset. Sign in with your new password.'})

    def current_session(self):
        token = self.session_token()
        session = SESSIONS.get(token)
        if session and session['expires'] > time.time():
            with database() as db:
                row = db.execute('SELECT disabled FROM accounts WHERE email = ?', (session['email'].casefold(),)).fetchone()
            if row and not row[0]:
                return session
        SESSIONS.pop(token, None)
        return None

    def require_admin(self):
        session = self.current_session()
        if not session:
            self.respond(401, {'message': 'Please sign in again.'})
            return False
        if not is_admin_email(session['email']):
            self.respond(403, {'message': 'Administrator access is required.'})
            return False
        return True

    def admin_accounts(self):
        if not self.require_admin():
            return
        with database() as db:
            rows = db.execute('SELECT email, name, disabled, created, is_admin FROM accounts ORDER BY email').fetchall()
        self.respond(200, {'accounts': [{'email': email, 'name': name, 'disabled': bool(disabled), 'created': created, 'isAdmin': bool(is_admin or email == ADMIN_EMAIL), 'isOwner': email == ADMIN_EMAIL} for email, name, disabled, created, is_admin in rows]})

    def admin_action(self):
        if not self.require_admin():
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or not isinstance(data.get('email'), str):
                raise ValueError()
            email = data['email'].strip().casefold()
            action = data.get('action')
            if action not in ('rename', 'enable', 'disable', 'reset-password', 'delete', 'grant-admin', 'revoke-admin'):
                raise ValueError()
        except (ValueError, TypeError, UnicodeDecodeError):
            self.respond(400, {'message': 'Invalid account action.'})
            return
        if email == ADMIN_EMAIL and action != 'rename':
            self.respond(400, {'message': 'The owner account is protected. Use Change password to update your own password.'})
            return
        self.audit_action = 'admin.account.' + action
        with database() as db:
            if not db.execute('SELECT 1 FROM accounts WHERE email = ?', (email,)).fetchone():
                self.respond(404, {'message': 'Account not found.'})
                return
            if action == 'rename':
                name = data.get('name')
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                    self.respond(400, {'message': 'Enter a name of 1 to 100 characters.'})
                    return
                db.execute('UPDATE accounts SET name = ? WHERE email = ?', (name.strip(), email))
            elif action in ('grant-admin', 'revoke-admin'):
                disabled = db.execute('SELECT disabled FROM accounts WHERE email = ?', (email,)).fetchone()[0]
                if action == 'grant-admin' and disabled:
                    self.respond(400, {'message': 'Enable this account before making it an administrator.'})
                    return
                db.execute('UPDATE accounts SET is_admin = ? WHERE email = ?', (int(action == 'grant-admin'), email))
            elif action in ('enable', 'disable'):
                db.execute('UPDATE accounts SET disabled = ? WHERE email = ?', (int(action == 'disable'), email))
            elif action == 'reset-password':
                password = data.get('password')
                if not isinstance(password, str) or not 8 <= len(password) <= 1024:
                    self.respond(400, {'message': 'Use a password with 8 to 1024 characters.'})
                    return
                salt = secrets.token_bytes(16)
                db.execute('UPDATE accounts SET salt = ?, password_hash = ? WHERE email = ?', (salt, password_hash(password, salt), email))
            else:
                db.execute('DELETE FROM accounts WHERE email = ?', (email,))
        if action in ('disable', 'reset-password', 'delete', 'revoke-admin'):
            for token, session in list(SESSIONS.items()):
                if session['email'].casefold() == email:
                    SESSIONS.pop(token, None)
        message = {'delete': 'Account deleted.', 'grant-admin': 'Administrator access granted.', 'revoke-admin': 'Administrator access removed.'}.get(action, 'Account updated.')
        self.respond(200, {'message': message})

    def session_token(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get('Cookie', ''))
        return cookie['solvai_session'].value if 'solvai_session' in cookie else ''

    def change_password(self):
        token = self.session_token()
        session = self.current_session()
        if not session or session['expires'] <= time.time():
            self.respond(401, {'message': 'Please sign in again to change your password.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
            current = data.get('currentPassword', '')
            new = data.get('newPassword', '')
            confirm = data.get('confirmPassword', '')
            if not isinstance(current, str) or not 1 <= len(current) <= 1024:
                raise ValueError()
            if not isinstance(new, str) or not 8 <= len(new) <= 1024:
                self.respond(400, {'message': 'Use a new password with 8 to 1024 characters.'})
                return
            if new != confirm:
                self.respond(400, {'message': 'Passwords do not match.'})
                return
            if current == new:
                self.respond(400, {'message': 'Choose a password different from your current password.'})
                return
        except (ValueError, TypeError, UnicodeDecodeError):
            self.respond(400, {'message': 'Please provide your current and new passwords.'})
            return
        email = session['email'].casefold()
        with database() as db:
            account = db.execute('SELECT salt, password_hash FROM accounts WHERE email = ?', (email,)).fetchone()
            valid = bool(account and hmac.compare_digest(password_hash(current, account[0]), account[1]))
            if not valid:
                self.respond(400, {'message': 'Your current password is incorrect.'})
                return
            salt = secrets.token_bytes(16)
            hashed = password_hash(new, salt)
            if account:
                result = db.execute('UPDATE accounts SET salt = ?, password_hash = ? WHERE email = ? AND password_hash = ?', (salt, hashed, email, account[1]))
                if not result.rowcount:
                    self.respond(409, {'message': 'Your password changed during this request. Please try again.'})
                    return
            else:
                db.execute('INSERT INTO accounts (email, name, salt, password_hash, created) VALUES (?, ?, ?, ?, ?)', (email, 'Demo account', salt, hashed, time.time()))
        for other_token, other_session in list(SESSIONS.items()):
            if other_token != token and other_session['email'].casefold() == email:
                SESSIONS.pop(other_token, None)
        self.respond(200, {'message': 'Your password has been changed.'})

    def respond(self, status, data, cookie=None):
        trace_id=secrets.token_hex(16)
        data={**data,'trace_id':trace_id,'contract_version':'f16-v1'}
        try:
            active_trace_db=getattr(DATABASE_CONTEXT,'connection',None)
            if active_trace_db is not None:operational_health.trace(active_trace_db,trace_id,urlparse(self.path).path,status)
            else:
                with database() as trace_db:operational_health.trace(trace_db,trace_id,urlparse(self.path).path,status)
        except (sqlite3.Error,OSError):pass  # telemetry failure cannot disable unrelated responses
        path = urlparse(self.path).path
        action = ('admin.request' if security.route_policy(path) == 'admin' else
                  'analytics.request' if security.route_policy(path) else
                  path.removeprefix('/api/') if path in ('/api/login', '/api/register', '/api/logout', '/api/change-password', '/api/forgot-password', '/api/reset-password') else None)
        if action:
            session = SESSIONS.get(self.session_token())
            def write_audit(db):
                security.audit(db, getattr(self, 'audit_actor', session['email'].casefold() if session else None),
                               self.command + ':' + getattr(self, 'audit_action', action), status)
            active_db = getattr(DATABASE_CONTEXT, 'connection', None)
            if active_db is not None:
                write_audit(active_db)
            else:
                with database() as db:
                    write_audit(db)
        if status >= 400:
            data = {**data, 'error': {'code': {400: 'INVALID_REQUEST', 401: 'AUTHENTICATION_REQUIRED', 403: 'ACCESS_DENIED', 404: 'NOT_FOUND', 409: 'CONFLICT', 413: 'PAYLOAD_TOO_LARGE', 429: 'RATE_LIMITED'}.get(status, 'SERVICE_UNAVAILABLE' if status == 503 else 'REQUEST_FAILED')}}
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Trace-ID',trace_id)
        if cookie:
            if PRODUCTION:
                cookie += '; Secure'
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        if not self.policy_guard():
            return
        address = urlparse(self.path).path
        if address in ('/api/admin/health','/api/admin/data-health'):
            try:
                result=operational_health.report(ROOT)
                with database() as db:operational_health.archive(db,result)
                self.respond(200,result)
            except (sqlite3.Error,OSError):self.respond(503,{'message':'Health archive unavailable.'})
            return
        if address in ('/api/admin/distribution','/api/admin/distribution/monitor'):self.distribution_api();return
        if address == '/api/research/financial-sources':
            session = self.current_session()
            self.respond(200, financial_sources.catalog(ROOT, is_admin_email(session['email'])))
            return
        sec_route=re.fullmatch(r'/api/research/sec/([A-Za-z0-9.-]{1,16})',address)
        if sec_route:
            if not self.current_session():
                self.respond(401,{'message':'Please sign in again.'});return
            try:
                self.respond(200,sec_filings.research(sec_route[1],parse_qs(urlparse(self.path).query).get('refresh',['0'])[0]=='1',root=ROOT))
            except sec_filings.FilingUnavailable as exc:
                self.respond(422,{'status':'UNAVAILABLE','reason_code':exc.reason})
            except (ValueError,KeyError,TypeError,ArithmeticError,OSError,sqlite3.Error):
                self.respond(503,{'status':'UNAVAILABLE','reason_code':'SEC_RESEARCH_UNAVAILABLE'})
            return
        if address=='/api/research/examples/apple-2025':
            if not self.current_session():
                self.respond(401,{'message':'Please sign in again.'})
                return
            try:self.respond(200,public_filing_demo.calculate())
            except (ValueError,KeyError,TypeError,ArithmeticError,sqlite3.Error,OSError) as exc:
                self.respond(503,{'message':'Public filing demonstration unavailable.'})
            return
        if address=='/api/research/watch':self.watch_api();return
        if address in ('/api/admin/finance/observations','/api/admin/finance/stages'):
            self.finance_stage_api();return
        if address in ('/api/research/news','/api/research/news/proposals','/api/admin/news/proposals'):
            self.news_api();return
        if address=='/api/research/events/agent':
            if not self.current_session():
                self.respond(401,{'message':'Please sign in again.'});return
            q=parse_qs(urlparse(self.path).query)
            try:
                category=q.get('category',[''])[0];factor=q.get('factor',[''])[0]
                focus=q.get('focus',['World'])[0];horizon=q.get('horizon',['30 days'])[0]
                if factor not in event_news_preview._TOPICS.get(category,{}) or horizon not in event_horizons.HORIZONS:
                    raise ValueError('Invalid research watch')
                self.respond(200,event_agent_store.read(category,factor,focus,horizon))
            except (ValueError,TypeError,OverflowError):
                self.respond(400,{'message':'Invalid event intelligence watch.'})
            return
        if address in ('/api/research/events/forecast-options', '/api/research/events/forecast-history'):
            self.event_forecast_api();return
        if address=='/api/research/events/live':
            if not self.current_session():
                self.respond(401,{'message':'Please sign in again.'});return
            try:
                q=parse_qs(urlparse(self.path).query)
                result=event_news_preview.analyze(q.get('category',[''])[0],q.get('factor',[''])[0],q.get('focus',[''])[0],q.get('horizon',['30 days'])[0],basis=q.get('basis',['END_STATE'])[0])
                self.respond(200,result)
            except ValueError:self.respond(400,{'message':'Unsupported event research configuration.'})
            except event_news_preview.Unavailable as exc:self.respond(503,{'status':'UNAVAILABLE','reason_code':str(exc),'items':[],'outcomes':[],
                                                                          'coverage':getattr(exc,'coverage',None)})
            return
        if address in ('/api/research/events','/api/research/events/evidence'):
            self.event_api();return
        if address in ('/api/research/macro','/api/research/commodity-exposures'):
            try:
                query=parse_qs(urlparse(self.path).query)
                result=macro_evidence.summary(ROOT,query.get('scope',['world'])[0],query.get('origin',[None])[0]) if address.endswith('/macro') else macro_evidence.exposures(ROOT,query.get('ticker',[''])[0])
                self.respond(200,result)
            except (ValueError,KeyError,TypeError):self.respond(400,{'message':'Invalid macro scope, origin or issuer.'})
            except (sqlite3.Error,OSError):self.respond(503,{'message':'Macro evidence unavailable.'})
            return
        if address=='/api/portfolio/snapshot':
            session=self.current_session()
            if not session:self.respond(401,{'message':'Please sign in again.'});return
            try:
                with database() as db:result=portfolio_ledger.snapshot(db,ROOT,session['email'].casefold())
                self.respond(200,result)
            except (sqlite3.Error,OSError,ArithmeticError,ValueError,KeyError):self.respond(503,{'message':'Portfolio snapshot unavailable.'})
            return
        technical_route=re.fullmatch('/api/market/([A-Za-z0-9.-]{1,16})/indicators',address)
        if technical_route:
            if not self.current_session():
                self.respond(401,{'message':'Please sign in again.'});return
            try:self.respond(200,technical.analyze(ROOT,technical_route[1].upper(),parse_qs(urlparse(self.path).query).get('origin',[None])[0]))
            except (ValueError,KeyError,TypeError):self.respond(400,{'message':'Invalid technical research origin.'})
            except (sqlite3.Error,OSError):self.respond(503,{'message':'Technical diagnostics unavailable.'})
            return
        stock_route=re.fullmatch('/api/market/stock/([A-Za-z0-9.-]{1,16})/analysis',address)
        if stock_route:
            if not self.current_session():
                self.respond(401,{'message':'Please sign in again.'})
                return
            try:
                self.respond(200,stock_models.analysis(ROOT,stock_route[1].upper()))
            except (sqlite3.Error,OSError,ValueError,KeyError):
                self.respond(503,{'message':'Stock analysis is unavailable.'})
            return
        if re.fullmatch('/api/research/valuation/runs/[a-f0-9]{32}',address):
            session=self.current_session()
            if not session:
                self.respond(401,{'message':'Please sign in again.'})
                return
            with database() as db:
                valuation.initialize(db)
                row=db.execute('SELECT payload FROM valuation_runs WHERE id=? AND owner=?',(address.rsplit('/',1)[1],session['email'].casefold())).fetchone()
            self.respond(200,json.loads(row[0])) if row else self.respond(404,{'message':'Valuation run not found.'})
            return
        if address == '/api/research/compare' or address.startswith('/api/research/company/') or re.fullmatch('/api/research/facts/[^/]+/evidence',address):
            self.finance_research()
            return
        if urlparse(self.path).path == '/api/market/summary':
            if not self.current_session():
                self.respond(401, {'message': 'Please sign in again.'})
                return
            mode = parse_qs(urlparse(self.path).query).get('mode', ['demo'])[0]
            try:
                self.respond(200, market_summary.summary(mode))
            except ValueError:
                self.respond(400, {'message': 'Choose demo or provider market mode.'})
            return
        if urlparse(self.path).path == '/api/permissions':
            session = self.current_session()
            if not session:
                self.respond(401, {'message': 'Please sign in again.'})
                return
            self.respond(200, {'permissions': security.permissions(is_admin_email(session['email']))})
            return
        if urlparse(self.path).path == '/api/admin/documents' or urlparse(self.path).path.startswith('/api/admin/documents/'):
            self.admin_documents('GET')
            return
        if self.path == '/api/admin/accounts':
            self.admin_accounts()
            return
        if self.path != '/api/session':
            self.respond(404, {'message': 'Not found.'})
            return
        token = self.session_token()
        session = self.current_session()
        authenticated = bool(session and session['expires'] > time.time())
        if session and not authenticated:
            SESSIONS.pop(token, None)
        self.respond(200, {'authenticated': authenticated, 'isAdmin': bool(authenticated and is_admin_email(session['email'])), 'user': account_profile(session['email']) if authenticated else None})

    def do_POST(self):
        if not self.policy_guard():
            return
        if urlparse(self.path).path == '/api/admin/financial-sources':
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024:
                    raise ValueError('Invalid configuration size.')
                data = json.loads(self.read_document_body(size))
                if not isinstance(data, dict):
                    raise ValueError('Invalid configuration.')
                financial_sources.configure(ROOT, data.get('email'))
                self.respond(200, financial_sources.catalog(ROOT, True))
            except (ValueError, TypeError, UnicodeError) as exc:
                self.respond(400, {'message': str(exc)})
            except DocumentError as exc:
                self.respond(400, {'message': str(exc)})
            except OSError:
                self.respond(503, {'message': 'Cannot save source configuration.'})
            return
        if urlparse(self.path).path == '/api/research/events/forecast':
            self.event_forecast_api();return
        if urlparse(self.path).path=='/api/trades/outcomes':
            self.trade_outcomes_api();return
        if urlparse(self.path).path in ('/api/admin/distribution/pools','/api/admin/distribution/candidates','/api/admin/distribution/transitions','/api/admin/distribution/shadow'):
            self.distribution_api();return
        if urlparse(self.path).path=='/api/research/assistant':self.assistant_api();return
        if urlparse(self.path).path in ('/api/research/watch','/api/research/watch/evaluate','/api/research/watch/acknowledge'):
            self.watch_api();return
        if urlparse(self.path).path in ('/api/admin/finance/stages','/api/admin/finance/stages/decide'):
            self.finance_stage_api();return
        if urlparse(self.path).path in ('/api/admin/news/sources','/api/admin/news/ingest','/api/admin/news/review','/api/admin/news/decide','/api/research/news/bookmarks','/api/research/news/proposals'):
            self.news_api();return
        if urlparse(self.path).path in ('/api/research/events','/api/research/events/resolve','/api/admin/events/evidence'):
            self.event_api();return
        if urlparse(self.path).path in ('/api/admin/macro/observations','/api/admin/macro/exposures','/api/research/commodity-stress'):
            self.macro_api();return
        if urlparse(self.path).path in ('/api/portfolio/snapshot','/api/portfolio/transactions','/api/admin/portfolio/fx'):
            self.portfolio_write();return
        if urlparse(self.path).path in ('/api/trades/feasibility','/api/portfolio/baseline','/api/admin/portfolio/review','/api/admin/trades/instruments'):
            self.trade_api();return
        if urlparse(self.path).path=='/api/admin/market/ohlcv':
            self.technical_ingest();return
        if urlparse(self.path).path in ('/api/admin/market/models/freeze','/api/admin/market/models/evaluate'):
            self.stock_model_admin()
            return
        if urlparse(self.path).path in ('/api/research/valuation','/api/research/assumptions','/api/admin/finance/assumptions/review'):
            self.valuation_api()
            return
        if urlparse(self.path).path == '/api/admin/finance/facts':
            self.finance_ingest()
            return
        if urlparse(self.path).path == '/api/admin/documents' or urlparse(self.path).path.startswith('/api/admin/documents/'):
            self.admin_documents('POST')
            return
        if self.path in ('/api/forgot-password', '/api/reset-password'):
            self.reset_password()
            return
        if self.path == '/api/admin/accounts':
            self.admin_action()
            return
        if self.path == '/api/change-password':
            self.change_password()
            return
        if self.path == '/api/logout':
            token = self.session_token()
            session = self.current_session()
            self.audit_actor = session['email'].casefold() if session else None
            SESSIONS.pop(token, None)
            self.respond(200, {'message': 'Signed out.'}, 'solvai_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            return
        if self.path not in ('/api/login', '/api/register'):
            self.respond(404, {'message': 'Not found.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
            email = data.get('email', '')
            if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                raise ValueError()
        except (ValueError, TypeError, UnicodeDecodeError):
            self.respond(400, {'message': 'Please provide a valid email address.'})
            return
        password = data.get('password', '')
        if not isinstance(password, str) or not 1 <= len(password) <= 1024:
            self.respond(400, {'message': 'Please provide a password of at most 1024 characters.'})
            return
        if self.path == '/api/login':
            with database() as db:
                account = db.execute('SELECT salt, password_hash, disabled FROM accounts WHERE email = ?', (email.casefold(),)).fetchone()
            valid = bool(account and hmac.compare_digest(password_hash(password, account[0]), account[1]))
            if not valid:
                self.respond(401, {'message': 'Email or password is incorrect.'})
                return
            if account[2]:
                self.respond(403, {'message': 'Your account is disabled. Please contact an administrator.'})
                return
            token = secrets.token_urlsafe(32)
            duration = 604800 if data.get('remember') == 'true' else 3600
            SESSIONS[token] = {'email': email, 'expires': time.time() + duration}
            self.audit_actor = email.casefold()
            cookie = f'solvai_session={token}; HttpOnly; SameSite=Strict; Path=/'
            if data.get('remember') == 'true':
                cookie += '; Max-Age=604800'
            self.respond(200, {'message': 'You are signed in to PASION.', 'isAdmin': is_admin_email(email), 'user': account_profile(email)}, cookie)
        else:
            name = data.get('name', '')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                self.respond(400, {'message': 'Please provide your full name.'})
                return
            if len(password) < 8:
                self.respond(400, {'message': 'Use a password with at least 8 characters.'})
                return
            if email.casefold() in (EMAIL.casefold(), ADMIN_EMAIL):
                self.respond(409, {'message': 'An account with this email already exists. Please sign in.'})
                return
            salt = secrets.token_bytes(16)
            hashed = password_hash(password, salt)
            try:
                with database() as db:
                    db.execute('INSERT INTO accounts (email, name, salt, password_hash, created) VALUES (?, ?, ?, ?, ?)', (email.casefold(), name.strip(), salt, hashed, time.time()))
            except sqlite3.IntegrityError:
                self.respond(409, {'message': 'An account with this email already exists. Please sign in.'})
                return
            self.audit_actor = email.casefold()
            self.respond(201, {'message': 'Account created. You can now sign in.'})

    def do_DELETE(self):
        if not self.policy_guard():
            return
        if urlparse(self.path).path.startswith('/api/admin/documents/'):
            self.admin_documents('DELETE')
            return
        self.respond(404, {'message': 'Not found.'})

    def do_PUT(self):
        if self.policy_guard():
            self.respond(404, {'message': 'Not found.'})

    do_PATCH = do_PUT

if __name__ == '__main__':
    if PRODUCTION and not ADMIN_EMAIL:
        raise SystemExit('Set PASION_ADMIN_EMAIL before starting production mode.')
    try:
        http = ExclusiveHTTPServer(('127.0.0.1', 8000), Handler)
    except OSError as error:
        raise SystemExit('Unable to start PASION API on 127.0.0.1:8000. Another backend may already be running. Stop it before starting a new instance. ' + str(error))
    document_service.resume_processing(ROOT)
    print('PASION API running at http://127.0.0.1:8000', flush=True)
    http.serve_forever()

