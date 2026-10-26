import http.client,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import operational_health as h
import test_server as fixtures

class HealthTests(unittest.TestCase):
 def test_failed_probe_isolated_and_traces_sanitized(self):
  with tempfile.TemporaryDirectory() as temp,patch('market_summary.summary',side_effect=OSError('secret internal path')):
   result=h.report(Path(temp));provider=result['subsystems'][0]
   self.assertEqual(provider['reason_codes'],['SUBSYSTEM_PROBE_FAILED'])
   self.assertEqual(len(result['subsystems']),6);self.assertNotIn('secret',json.dumps(result))
  db=sqlite3.connect(':memory:')
  try:
   h.trace(db,'trace','/api/admin/documents/private?password=secret',403);row=db.execute('SELECT * FROM request_traces').fetchone()
   self.assertEqual(row[2],'admin');self.assertEqual(row[4],'ACCESS_DENIED');self.assertNotIn('secret',str(row))
   h.archive(db,result);self.assertEqual(db.execute('SELECT count(*) FROM health_runs').fetchone()[0],1)
  finally:db.close()

class HealthApiTests(unittest.TestCase):
 setUp=fixtures.ChangePasswordTests.setUp
 tearDown=fixtures.ChangePasswordTests.tearDown
 authorize=fixtures.AdminTests.authorize
 def call(self,path,token='active'):
  c=http.client.HTTPConnection('127.0.0.1',self.http.server_port);c.request('GET',path,headers={'Cookie':'solvai_session='+token});r=c.getresponse();result=r.status,json.loads(r.read()),r.getheader('X-Trace-ID');c.close();return result
 def test_role_and_shared_trace_contract(self):
  status,data,header=self.call('/api/admin/health');self.assertEqual(status,403);self.assertEqual(data['trace_id'],header);self.assertEqual(data['error']['code'],'ACCESS_DENIED')
  self.authorize();status,data,header=self.call('/api/admin/health','admin');self.assertEqual(status,200);self.assertEqual(len(data['subsystems']),6);self.assertEqual(data['trace_id'],header)
  self.assertEqual(self.call('/api/admin/data-health')[0],403)
  status,data,header=self.call('/api/admin/data-health','admin');self.assertEqual(status,200)
  self.assertEqual(data['release_manifest']['packages'][0]['stage'],'P0.0')
  self.assertFalse(data['release_manifest']['live_routing'])
