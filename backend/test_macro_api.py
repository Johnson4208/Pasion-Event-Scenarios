import http.client
import json
import unittest
import test_server as fixtures


class MacroApiTests(unittest.TestCase):
    setUp=fixtures.ChangePasswordTests.setUp
    tearDown=fixtures.ChangePasswordTests.tearDown
    authorize=fixtures.AdminTests.authorize

    def call(self,method,path,data=None,token='active'):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        connection.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token})
        response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result

    def test_role_and_empty_coverage_contract(self):
        self.assertEqual(self.call('GET','/api/research/macro?scope=world',token='missing')[0],401)
        self.assertEqual(self.call('GET','/api/research/macro?scope=japan')[1]['status'],'UNAVAILABLE')
        self.assertEqual(self.call('POST','/api/admin/macro/observations',{})[0],403)
        self.assertEqual(self.call('POST','/api/admin/macro/exposures',{})[0],403)
        self.assertEqual(self.call('GET','/api/research/macro?scope=unknown')[0],400)
        self.assertEqual(self.call('POST','/api/research/commodity-stress',{'exposure_id':'missing'})[1]['delta_ebit'],None)
        self.authorize()
        self.assertEqual(self.call('POST','/api/admin/macro/observations',{},token='admin')[0],400)
