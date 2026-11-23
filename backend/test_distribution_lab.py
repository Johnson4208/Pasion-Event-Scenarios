import http.client
import json
from collections import Counter
from datetime import date
import sqlite3
import time
import unittest
from unittest.mock import patch

import server
import test_server
from distribution import recommendations, paper_market
from distribution.lab import Conflict, DEFAULTS, Lab, Run


class SimulationTests(unittest.TestCase):
    def make_run(self, **options):
        run = Run({**DEFAULTS, 'mode':'benchmark', 'start_date':'2025-01-01', **options})
        self.addCleanup(run.directory.cleanup)
        return run

    def test_two_year_clock_and_reproducible_seed(self):
        first = self.make_run(days=730, daily_requests=3, customers=2)
        repeat = self.make_run(days=730, daily_requests=3, customers=2, speed=60)
        for _ in range(730):
            first.advance()
            repeat.advance()
        self.assertEqual(first.status, 'completed')
        self.assertEqual(first.history[-1]['date'], '2026-12-31')
        self.assertEqual(first.history, repeat.history)
        self.assertEqual(first.events, repeat.events)
        self.assertEqual(first.totals['selected'], sum(first.symbols.values()))
        self.assertEqual(first.totals['requests'], first.totals['selected'] + first.totals['withheld'])
        self.assertGreater(first.totals['redirected'], 0)
        self.assertGreater(first.totals['withheld'], 0)
        self.assertEqual(first.symbols['SIM_LOW'], 0)
        with sqlite3.connect(first.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM recommendation_requests').fetchone()[0],
                             first.totals['requests'])

    def test_failed_day_rolls_back_engine_and_metrics(self):
        run = self.make_run(daily_requests=20)
        original = recommendations.decide_in_transaction
        calls = 0
        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise sqlite3.OperationalError('synthetic failure')
            return original(*args)
        with patch.object(recommendations, 'decide_in_transaction', fail_second):
            with self.assertRaises(sqlite3.OperationalError):
                run.advance()
        self.assertEqual(run.day, 0)
        self.assertEqual(run.totals['requests'], 0)
        with sqlite3.connect(run.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM recommendation_requests').fetchone()[0], 0)

    def test_controls_stale_commands_and_date_of_changes(self):
        service = Lab()
        def send(action, **values):
            run = service.run
            return service.command(dict(action=action, values=values, run_id=run.id if run else None,
                                        revision=run.revision if run else 0))['run']
        send('create', days=40, customers=2, speed=1, daily_requests=8)
        self.addCleanup(service.run.directory.cleanup)
        send('step')
        stale = dict(action='update', values={'add_customers':2}, run_id=service.run.id,
                     revision=service.run.revision)
        send('update', add_customers=3, max_per_symbol=1)
        with self.assertRaises(Conflict):
            service.command(stale)
        with self.assertRaises(ValueError):
            send('update', daily_requests=0)
        self.assertEqual(service.run.changes[-1]['day'], 2)
        send('start')
        deadline = time.monotonic() + 3
        while service.state()['run']['day'] == 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        stopped = send('pause')
        self.assertEqual(stopped['history'][0]['customers'], 2)
        self.assertEqual(stopped['history'][1]['customers'], 5)
        self.assertEqual(stopped['status'], 'paused')
        self.assertEqual(send('step')['day'], stopped['day'] + 1)
        old_db = service.run.db
        fresh = send('create', days=1)
        self.addCleanup(service.run.directory.cleanup)
        self.assertFalse(old_db.exists())
        self.assertEqual(fresh['day'], 0)
        self.assertEqual(send('step')['status'], 'completed')

    def test_replay_orders_reconcile_and_reference_prior_session(self):
        run = self.make_run(mode='historical', start_date='2024-01-01', days=90, customers=3)
        for _ in range(90):
            run.advance()
        self.assertEqual(run.history[0]['requests'], 0)  # New Year's Day
        totals = run.paper['totals']
        self.assertGreater(totals['buys'], 0)
        self.assertGreater(totals['sells'], 0)
        self.assertEqual(totals['notional'], sum(day['paper']['notional'] for day in run.history))
        cash, positions = {}, Counter()
        with sqlite3.connect(run.db) as db:
            for customer,symbol,side,qty,price,signal_day,day,request in db.execute(
                    'SELECT customer,symbol,side,quantity,price,signal_date,day,request FROM paper_fills ORDER BY id'):
                self.assertLess(date.fromisoformat(signal_day),date.fromisoformat(day))
                self.assertEqual(qty % 100, 0)
                bars, indices, _ = paper_market.tape(symbol)
                self.assertEqual(price, bars[indices[day]]['open'])
                self.assertEqual(signal_day, bars[indices[day]-1]['date'])
                value = qty*price
                if side == 'BUY':
                    decision = json.loads(db.execute('SELECT result FROM recommendation_requests WHERE id=?',(request,)).fetchone()[0])
                    self.assertEqual(decision['symbol'],symbol)
                positions[customer,symbol] += qty if side=='BUY' else -qty
                cash[customer] = cash.get(customer,run.config['initial_cash']) + (value if side=='SELL' else -value) - value//1000
                self.assertGreaterEqual(positions[customer,symbol],0)
                self.assertGreaterEqual(cash[customer],0)
            self.assertEqual(cash,dict(db.execute('SELECT customer,cash FROM paper_accounts')))
        self.assertEqual(totals['buys']+totals['sells'],sum(row['trades'] for row in run.paper['top_accounts']))

    def test_replay_failure_rolls_back_both_ledgers(self):
        run = self.make_run(mode='historical', start_date='2024-01-02', days=1)
        with patch.object(paper_market,'monitor',side_effect=sqlite3.OperationalError('rollback')):
            with self.assertRaises(sqlite3.OperationalError):
                run.advance()
        self.assertEqual(run.day,0)
        self.assertIsNone(run.paper)
        with sqlite3.connect(run.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM recommendation_requests').fetchone()[0],0)
        run.advance()
        self.assertEqual(run.day,1)
        self.assertEqual(sum(s['notional'] for s in run.paper['symbols']),run.history[0]['paper']['notional'])

    def test_replay_uses_no_execution_day_data_for_ranking(self):
        day = '2024-05-10'
        expected, opens = paper_market.session(day)
        original = paper_market.tape
        def different_market(symbol):
            bars, indices, events = original(symbol)
            i = indices[day]
            altered = [dict(b,open=b['open']*2,close=b['close']*2,volume=0) for b in bars[i:]]
            return bars[:i]+altered, indices, events
        with patch.object(paper_market,'tape',different_market):
            actual, new_opens = paper_market.session.__wrapped__(day)
        self.assertEqual(expected,actual)
        self.assertNotEqual(opens,new_opens)
        ranks = [paper_market.candidates_for(expected,profile) for profile in range(3)]
        self.assertNotEqual(ranks[0],ranks[1])
        service = Lab()
        with self.assertRaises(ValueError):
            service.command(dict(action='create',revision=0,values={'start_date':'2025-12-31','days':2}))


class AdminApiTests(unittest.TestCase):
    setUp = test_server.ChangePasswordTests.setUp
    tearDown = test_server.ChangePasswordTests.tearDown
    authorize = test_server.AdminTests.authorize

    def call(self, method, token, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        try:
            conn.request(method, '/api/admin/distribution/lab', json.dumps(body) if body else None,
                         {'Cookie': 'solvai_session=' + token, 'Content-Type':'application/json', **headers})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_admin_only_local_http_and_isolated_storage(self):
        service = Lab()
        self.authorize()
        with patch.object(server.distribution_lab, 'lab', service):
            for method in ('GET','POST'):
                self.assertEqual(self.call(method,'missing')[0], 401)
                self.assertEqual(self.call(method,'active')[0], 403)
                self.assertEqual(self.call(method,'admin',Host='external.example')[0], 403)
            self.assertEqual(self.call('POST','admin',Origin='https://external.example')[0], 403)
            with patch.object(server,'PRODUCTION',True):
                self.assertEqual(self.call('GET','admin')[0], 403)
            self.assertEqual(self.call('GET','admin')[1]['run'], None)
            status, body = self.call('POST','admin',dict(action='create', revision=0, values={'days':1}))
            self.assertEqual(status, 200)
            self.addCleanup(service.run.directory.cleanup)
            run = body['run']
            cmd = dict(action='step', revision=run['revision'], run_id=run['id'])
            self.assertEqual(self.call('POST','admin',cmd)[1]['run']['status'], 'completed')
            self.assertEqual(self.call('POST','admin',cmd)[0], 409)
            with server.database() as db:
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='recommendation_exposures'").fetchone())
