import http.client
import json
import unittest
import test_server as fixtures


class StockApiTests(unittest.TestCase):
    setUp=fixtures.ChangePasswordTests.setUp
    tearDown=fixtures.ChangePasswordTests.tearDown
    authorize=fixtures.AdminTests.authorize

    def call(self,method,path,body=None,token='active'):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        connection.request(method,path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token})
        response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result

    def test_member_can_read_unavailable_contract_but_not_freeze_or_evaluate(self):
        self.assertEqual(self.call('GET','/api/market/stock/FPT/analysis',token='missing')[0],401)
        status,result=self.call('GET','/api/market/stock/FPT/analysis')
        self.assertEqual(status,200)
        self.assertEqual(len(result['horizons']),4)
        self.assertTrue(all(h['p_up'] is None and h['status']=='UNAVAILABLE' for h in result['horizons']))
        for path in ['/api/admin/market/models/freeze','/api/admin/market/models/evaluate']:
            self.assertEqual(self.call('POST',path,{})[0],403)

    def test_admin_cannot_install_an_unverified_provider_or_probabilities(self):
        self.authorize()
        self.assertEqual(self.call('POST','/api/admin/market/models/freeze',{'ticker':'FPT','provider_verified':False,'p_up':.99},'admin')[0],400)
