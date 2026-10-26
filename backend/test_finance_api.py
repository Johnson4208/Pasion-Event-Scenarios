import http.client
import json
import unittest
from unittest.mock import patch
import test_server as fixtures
import server
import test_finance_core as finance_fixtures


class FinanceApiTests(unittest.TestCase):
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

    def test_member_cannot_ingest_and_anonymous_cannot_read(self):
        self.assertEqual(self.call('POST','/api/admin/finance/facts',{})[0],403)
        for path in ['/api/research/company/TEST','/api/research/compare?tickers=TEST','/api/research/facts/private/evidence']:
            self.assertEqual(self.call('GET',path,token='missing')[0],401)

    def test_review_ingestion_and_member_evidence_do_not_expose_admin_document(self):
        self.authorize()
        fixture=finance_fixtures.FinanceTests()
        payload={'issuer':{'ticker':'TEST','name':'Test issuer'},'calendar':fixture.calendar(2024),
                 'reports':[{'id':'report-2024','document_id':'private-admin-original','published_at':'2024-04-01T00:00:00Z','indexed_at':'2024-04-02T00:00:00Z'}],
                 'facts':[fixture.fact('revenue','0')]}
        with patch.object(server.document_service,'get_document',return_value={'status':'ready'}), patch.object(server.document_service,'get_original',return_value=('filing.pdf',b'original filing bytes')):
            self.assertEqual(self.call('POST','/api/admin/finance/facts',payload,token='admin')[0],201)
        status,data=self.call('GET','/api/research/company/TEST?period=Q')
        self.assertEqual(status,200)
        fact=data['metrics']['revenue']
        self.assertEqual(fact['value'],'0')
        status,source=self.call('GET','/api/research/facts/'+fact['source_ids'][0]+'/evidence')
        self.assertEqual(status,200)
        self.assertNotIn('private-admin-original',json.dumps(source))
        self.assertEqual(self.call('GET','/api/admin/documents/private-admin-original/download')[0],403)
        self.assertNotIn('reviewer',source)
        self.assertEqual(len(source['source_hash']),64)

    def test_malformed_periods_and_unimplemented_tickers_are_explicit(self):
        self.assertEqual(self.call('GET','/api/research/company/TEST?period=BAD')[0],400)
        status,data=self.call('GET','/api/research/company/TEST?period=TTM')
        self.assertEqual(status,200)
        self.assertEqual(data['status'],'UNAVAILABLE')
