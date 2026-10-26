import sqlite3, tempfile, unittest
from pathlib import Path
from contextlib import closing
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from distribution import capacity as c

class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'capacity.db'
        self.now=datetime.now(timezone.utc);self.end=(self.now+timedelta(hours=1)).isoformat()
        with closing(sqlite3.connect(self.path)) as db, db:
            c.initialize(db);db.commit();db.execute('BEGIN IMMEDIATE')
            base=dict(side='BUY',window_start=(self.now-timedelta(minutes=1)).isoformat(),window_end=self.end,
                      source_id='reviewed-tape',policy_version='test',same_window_tape_verified=True,capacity=1000)
            c.budget(db,dict(base,id='parent',venue='*',symbol='*'),self.now)
            for key in ('a','b'):
                c.budget(db,dict(base,id=key,venue='X',symbol=key,parent_id='parent'),self.now)
    def tearDown(self):self.temp.cleanup()
    def send(self, action, pid='one', rev=0, **extra):
        request=dict(idempotency_key=f'{pid}-{action}-{rev}',action=action,position_id=pid,expected_revision=rev,source_id='manual-shadow-event',**extra)
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            return c.event(db,request,self.now)
    def offer(self,pid='one',q=400,budget='a'):
        return self.send('Offer',pid,quantity=q,budget_id=budget,expires_at=self.end)
    def used(self):
        with closing(sqlite3.connect(self.path)) as db:return c.usage(db,'parent')
    def test_concurrent_parent_budget_and_retry(self):
        def reserve(args):
            try:self.offer(*args);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reserve,[('one',700,'a'),('two',700,'b')]))
        self.assertEqual(sum(results),1);self.assertEqual(self.used(),700)
        winner='one' if results[0] else 'two';budget='a' if results[0] else 'b'
        self.assertTrue(self.offer(winner,700,budget)['replayed']);self.assertEqual(self.used(),700)
        with self.assertRaises(ValueError):self.offer(winner,600,budget)
    def test_order_replaces_offer_cancel_retains_fills_and_late_fill_blocks(self):
        self.offer();self.send('Ordered',rev=1);self.assertEqual(self.used(),400)
        self.send('PartialFill',rev=2,quantity=200);self.assertEqual(self.used(),400)
        self.send('CancelRequested',rev=3);self.assertEqual(self.used(),400)
        self.send('CancelConfirmed',rev=4);self.assertEqual(self.used(),200)
        self.send('LateFill',rev=5,quantity=50);self.assertEqual(self.used(),250)
        with self.assertRaises(ValueError):self.offer('two',100,'b')
        self.send('Bust',rev=6);self.assertEqual(self.used(),250)
    def test_revision_ttl_and_no_unverified_capacity(self):
        self.offer()
        with self.assertRaises(ValueError):self.send('Ordered',rev=0)
        with self.assertRaises(ValueError):self.send('Expired',rev=1)
        self.now+=timedelta(hours=2)
        self.send('Expired',rev=1);self.assertEqual(self.used(),0)
        with self.assertRaises(ValueError):self.offer('two')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError):c.budget(db,dict(id='bad',venue='X',symbol='a',side='BUY',window_start=self.end,window_end=self.end,source_id='ADV',policy_version='test',capacity=1000,same_window_tape_verified=False),self.now)
