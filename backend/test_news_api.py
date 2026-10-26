import http.client
import json
import unittest
import test_server as fixtures


class NewsApiTests(unittest.TestCase):
    setUp=fixtures.ChangePasswordTests.setUp
    tearDown=fixtures.ChangePasswordTests.tearDown
    authorize=fixtures.AdminTests.authorize
    def call(self,method,path,data=None,token='active'):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        connection.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token})
        response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result
    def test_roles_feed_gaps_and_private_queue(self):
        self.assertEqual(self.call('GET','/api/research/news',token='missing')[0],401)
        self.assertEqual(self.call('GET','/api/research/news')[1]['status'],'UNAVAILABLE')
        for path in ('sources','ingest','review','decide'):
            self.assertEqual(self.call('POST','/api/admin/news/'+path,{})[0],403)
        self.assertEqual(self.call('GET','/api/admin/news/proposals')[0],403)
        self.assertEqual(self.call('GET','/api/research/news/proposals?owner=other')[1]['proposals'],[])
        self.assertEqual(self.call('POST','/api/research/news/proposals',{})[0],400)
        self.authorize();self.assertEqual(self.call('GET','/api/admin/news/proposals',token='admin')[0],200)
