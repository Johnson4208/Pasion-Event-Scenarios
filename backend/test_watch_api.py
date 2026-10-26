import http.client,json,unittest
import test_server as fixtures
class WatchApiTests(unittest.TestCase):
 setUp=fixtures.ChangePasswordTests.setUp
 tearDown=fixtures.ChangePasswordTests.tearDown
 def call(self,method,path,data=None,token='active'):
  c=http.client.HTTPConnection('127.0.0.1',self.http.server_port);c.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token});r=c.getresponse();result=r.status,json.loads(r.read());c.close();return result
 def test_session_owner_and_finance_admin_boundary(self):
  self.assertEqual(self.call('GET','/api/research/watch',token='missing')[0],401)
  self.assertEqual(self.call('POST','/api/research/watch',{'owner':'other','intent_type':'WATCH','ticker':'TEST'})[0],200)
  self.assertEqual(len(self.call('GET','/api/research/watch?owner=other')[1]['intents']),1)
  self.assertEqual(self.call('POST','/api/research/watch/acknowledge',{'event_id':'other'})[0],400)
  for path in ('observations','stages'):
   self.assertEqual(self.call('GET','/api/admin/finance/'+path+'?document_id=doc')[0],403)
  self.assertEqual(self.call('POST','/api/admin/finance/stages',{})[0],403)
