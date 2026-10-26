import json
import sqlite3
import unittest
from datetime import datetime,timezone,timedelta
import watch_events as w
import feasibility

class WatchTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY)');self.db.executemany('INSERT INTO accounts VALUES (?)',[('one',),('two',)])
  self.now=datetime(2026,10,13,12,tzinfo=timezone.utc)
 def tearDown(self):self.db.close()
 def quote(self,version='v1',now=None):
  now=now or self.now;feasibility.initialize(self.db)
  r={'version':version,'currency':'USD','source':'Reviewed fixture','quote':{'price':'110','as_of':now.isoformat(),'session_open':(self.now-timedelta(hours=1)).isoformat(),'session_close':(self.now+timedelta(hours=1)).isoformat(),'max_age_seconds':60}}
  self.db.execute('INSERT OR REPLACE INTO trading_instruments VALUES (?,?)',('TEST',json.dumps(r)))
 def alert(self):return w.save(self.db,'one',{'intent_type':'PRICE_ALERT','ticker':'TEST','target':'100','currency':'USD','direction':'ABOVE'},self.now)
 def test_replay_throttle_ownership_ack(self):
  self.alert();self.quote();first=w.evaluate(self.db,'one',self.now)['created'][0];self.assertTrue(first['notification'])
  self.assertEqual(w.evaluate(self.db,'one',self.now)['created'],[])
  self.quote('v2',self.now+timedelta(seconds=10));next=w.evaluate(self.db,'one',self.now+timedelta(seconds=10))['created'][0];self.assertEqual(next['delivery'],'THROTTLED')
  self.assertEqual(w.read(self.db,'two')['events'],[])
  with self.assertRaises(ValueError):w.acknowledge(self.db,'two',{'event_id':first['id']})
  w.acknowledge(self.db,'one',{'event_id':first['id']});w.acknowledge(self.db,'one',{'event_id':first['id']})
  self.assertEqual(len(w.read(self.db,'one')['acknowledgments']),1)
 def test_stale_missing_and_consent_gates(self):
  self.alert();self.assertFalse(w.evaluate(self.db,'one',self.now)['created'][0]['notification'])
  self.quote();result=w.evaluate(self.db,'one',self.now+timedelta(minutes=2))['created'][0];self.assertEqual(result['reason'],'QUOTE_EXPIRED')
  with self.assertRaises(ValueError):w.save(self.db,'one',{'intent_type':'WATCH','ticker':'TEST','imported':True})
  w.save(self.db,'one',{'intent_type':'WATCH','ticker':'TEST','imported':True,'consent':True})
  with self.assertRaises(ValueError):w.save(self.db,'one',{'intent_type':'ORDER','ticker':'TEST'})
