import http.client
import json
import unittest
from datetime import datetime,timezone
import test_server as fixtures


class PortfolioApiTests(unittest.TestCase):
    setUp=fixtures.ChangePasswordTests.setUp
    tearDown=fixtures.ChangePasswordTests.tearDown
    authorize=fixtures.AdminTests.authorize

    def call(self,method,path,data=None,token='active'):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        connection.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token})
        response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result

    def test_ownership_roles_and_revision_boundary(self):
        self.assertEqual(self.call('GET','/api/portfolio/snapshot',token='missing')[0],401)
        payload={'owner':'another@example.com','expected_revision':0,'currency':'USD','cash':'0','reserved_cash':'0','source':'MANUAL_CONFIRMED','as_of':datetime.now(timezone.utc).isoformat(),'lots':[],'watchlist':['ONLYWATCH'],'targets':[]}
        self.assertEqual(self.call('POST','/api/portfolio/snapshot',payload)[0],200)
        self.assertEqual(self.call('POST','/api/portfolio/snapshot',payload)[0],409)
        self.assertEqual(self.call('POST','/api/admin/portfolio/fx',{})[0],403)
        self.authorize()
        self.assertIsNone(self.call('GET','/api/portfolio/snapshot?owner='+self.email,token='admin')[1]['state'])
        self.assertEqual(self.call('GET','/api/portfolio/snapshot')[1]['state']['cash'],'0')
