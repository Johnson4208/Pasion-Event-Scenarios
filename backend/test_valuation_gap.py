import json,sqlite3,unittest
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from finance.valuation import quote_gap
class GapTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.execute('CREATE TABLE trading_instruments(ticker TEXT,payload TEXT)');self.now=datetime(2026,10,14,10,tzinfo=timezone.utc)
  self.rules={'quote':{'price':'100','as_of':self.now.isoformat(),'session_open':(self.now-timedelta(hours=1)).isoformat(),'session_close':(self.now+timedelta(hours=1)).isoformat(),'max_age_seconds':'60'},'currency':'USD','source':'Reviewed fixture','version':'v1'}
  self.db.execute('INSERT INTO trading_instruments VALUES (?,?)',('TEST',json.dumps(self.rules)))
  self.methods=[{'method':'FCFF','status':'READY','value':'120','currency':'USD','source_ids':['fact']}]
 def tearDown(self):self.db.close()
 def test_fresh_method_specific_gap(self):
  r=quote_gap(self.db,'TEST',self.now.date(),ZoneInfo('UTC'),self.methods,self.now);self.assertEqual(r['methods'][0]['value'],'0.2');self.assertEqual(r['instrument_version'],'v1')
 def test_stale_historical_and_currency_gate(self):
  r=quote_gap(self.db,'TEST',self.now.date(),ZoneInfo('UTC'),self.methods,self.now+timedelta(minutes=2));self.assertEqual(r['reason'],'QUOTE_EXPIRED')
  r=quote_gap(self.db,'TEST',(self.now-timedelta(days=1)).date(),ZoneInfo('UTC'),self.methods,self.now);self.assertEqual(r['status'],'UNAVAILABLE')
  self.methods[0]['currency']='VND';r=quote_gap(self.db,'TEST',self.now.date(),ZoneInfo('UTC'),self.methods,self.now);self.assertEqual(r['reason'],'NO_ELIGIBLE_SAME_CURRENCY_VALUE')
