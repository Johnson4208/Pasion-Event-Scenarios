import http.client
import json
import sqlite3
import time
import unittest
from unittest.mock import patch

import server
import test_server
from distribution import recommendations
from distribution.lab import Conflict, DEFAULTS, Lab, Run


class SimulationTests(unittest.TestCase):
    def make_run(self, **options):
        run = Run({**DEFAULTS, **options})
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
