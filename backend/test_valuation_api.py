import http.client
import json
import unittest
from datetime import date
import test_server as fixtures


class ValuationApiTests(unittest.TestCase):
    setUp=fixtures.ChangePasswordTests.setUp
    tearDown=fixtures.ChangePasswordTests.tearDown
    authorize=fixtures.AdminTests.authorize

    def call(self,method,path,data=None,token='active'):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        connection.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token})
        response=connection.getresponse()
        result=response.status,json.loads(response.read())
        connection.close()
        return result

    def test_auth_and_review_permissions(self):
        self.assertEqual(self.call('POST','/api/research/valuation',{},'missing')[0],401)
        self.assertEqual(self.call('POST','/api/admin/finance/assumptions/review',{})[0],403)

    def test_unverified_registry_and_owner_scoped_runs(self):
        status,data=self.call('POST','/api/research/assumptions',{'ticker':'TEST','assumptions':[{'definition':'sector_policy','value':'industrial','unit':'category','effective_from':'2020-01-01T00:00:00Z','source_ids':[]}]})
        self.assertEqual(status,200)
        self.assertEqual(data['assumptions'][0]['status'],'UNVERIFIED')
        status,run=self.call('POST','/api/research/valuation',{'ticker':'TEST','valuation_date':date.today().isoformat()})
        self.assertEqual(status,200)
        self.assertTrue(all(m['value'] is None for m in run['methods']))
        path='/api/research/valuation/runs/'+run['run_id']
        self.assertEqual(self.call('GET',path)[0],200)
        self.authorize()
        self.assertEqual(self.call('GET',path,token='admin')[0],404)

    def test_review_rejects_missing_source_and_fake_owner(self):
        status,data=self.call('POST','/api/research/assumptions',{'ticker':'TEST','assumptions':[{'definition':'sector_policy','value':'bank','unit':'category','effective_from':'2020-01-01T00:00:00Z'}]})
        self.authorize()
        self.assertEqual(self.call('POST','/api/admin/finance/assumptions/review',{'owner':self.email,'assumption_ids':[data['assumptions'][0]['id']]},'admin')[0],400)
