import http.client
import json
import unittest
from unittest.mock import patch
import test_server as fixtures
import server


class MarketApiTests(unittest.TestCase):
    setUp = fixtures.ChangePasswordTests.setUp
    tearDown = fixtures.ChangePasswordTests.tearDown

    def request(self, query='', token='active'):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        connection.request('GET', '/api/market/summary' + query, headers={'Cookie': 'solvai_session=' + token})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_summary_requires_authentication(self):
        self.assertEqual(self.request(token='missing')[0], 401)

    def test_demo_contract_and_invalid_mode(self):
        status, result = self.request('?mode=demo')
        self.assertEqual(status, 200)
        self.assertEqual(result['mode'], 'demo')
        self.assertEqual(result['quotes'][0]['origin'], 'SAMPLE')
        self.assertEqual(self.request('?mode=live')[0], 400)

    def test_provider_unconfigured_returns_no_sample_quotes(self):
        with patch.dict(server.os.environ, {}, clear=True):
            status, result = self.request('?mode=provider')
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['quotes'], [])
