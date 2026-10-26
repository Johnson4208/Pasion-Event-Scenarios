import json,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import distribution_shadow as d
import test_server as fixtures
import http.client

class ShadowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'shadow.db';self.now=datetime.now(timezone.utc)
  with closing(sqlite3.connect(self.path)) as db, db:
   db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY,disabled INTEGER)');db.execute("INSERT INTO accounts VALUES ('owner',0)")
   self.pool=d.pool(db,{'capacity_slots':1,'horizon':'30 sessions','utility_definition':'net scenario utility','utility_version':'v1','policy':'Manual shadow review','expires_at':(self.now+timedelta(hours=1)).isoformat(),'reviewed':True})['pool']
   for key in ('one','two'):
    c={'id':key,'pool_id':self.pool['id'],'owner':'owner','ticker':'TEST','draft':{'ticker':'TEST'},'shadow_gate_passed':True,'account_version':'a','instrument_version':'i','expires_at':(self.now+timedelta(minutes=10)).isoformat()}
    c['policy_version']=d.engine.VERSION
    db.execute('INSERT INTO distribution_candidates VALUES (?,?)',(key,json.dumps(c)))
 def tearDown(self):self.temp.cleanup()
 def request(self,key,candidate='one',action='RESERVE_SHADOW_SLOT'):
  with closing(sqlite3.connect(self.path,timeout=10)) as db, db:
   db.execute('BEGIN IMMEDIATE')
   return d.transition(db,{'candidate_id':candidate,'pool_id':self.pool['id'],'idempotency_key':key,'action':action})
 def test_concurrent_retry_reserves_once_and_release_is_single_shot(self):
  with patch('feasibility.for_owner',return_value={'status':'READY','account_version':'a','instrument_version':'i'}):
   with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.request('retry'),range(4)))
   self.assertEqual(sum(not r['replayed'] for r in results),1)
   with self.assertRaises(ValueError):self.request('other','two')
   self.request('release',action='RELEASE_SHADOW_SLOT')
   with self.assertRaises(ValueError):self.request('rereserve')
   self.request('two','two')
  with closing(sqlite3.connect(self.path)) as db, db:self.assertEqual(d.state(db)['pools'][0]['reserved_slots'],1)
 def test_failed_gate_never_exposes_allocation(self):
  with closing(sqlite3.connect(self.path)) as db,db,patch('feasibility.for_owner',return_value={'status':'WITHHELD','reason_codes':['QUOTE_REQUIRED']}),patch('finance_core.evidence',return_value=None):
   result=d.candidate(db,Path(self.temp.name),{'owner':'owner','pool_id':self.pool['id'],'draft':{'ticker':'TEST'},'fact_id':'missing','review_note':'Review needed'})['candidate']
   self.assertEqual(result['status'],'WITHHELD');self.assertIsNone(result['allocation_quantity']);self.assertFalse(result['shadow_gate_passed'])

class ShadowApiTests(unittest.TestCase):
 setUp=fixtures.ChangePasswordTests.setUp
 tearDown=fixtures.ChangePasswordTests.tearDown
 authorize=fixtures.AdminTests.authorize
 def call(self,method,path,data=None,token='active'):
  c=http.client.HTTPConnection('127.0.0.1',self.http.server_port);c.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token});r=c.getresponse();result=r.status,json.loads(r.read());c.close();return result
 def test_admin_boundary_and_no_user_routes(self):
  self.assertEqual(self.call('GET','/api/admin/distribution')[0],403)
  self.assertEqual(self.call('POST','/api/admin/distribution/transitions',{})[0],403)
  self.assertEqual(self.call('POST','/api/admin/distribution/shadow',{})[0],403)
  self.authorize();self.assertEqual(self.call('GET','/api/admin/distribution',token='admin')[1]['status'],'SHADOW_ONLY_NO_ALLOCATION')
  self.assertEqual(self.call('POST','/api/admin/distribution/shadow',{},token='admin')[0],400)
