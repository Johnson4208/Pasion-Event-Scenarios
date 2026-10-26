import http.client
import json
import time
from unittest.mock import patch

import security
import server
from test_server import ChangePasswordTests, AdminTests


class SecurityTests(ChangePasswordTests):
    authorize = AdminTests.authorize

    def call(self, method, path, token='active'):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        connection.request(method, path, headers={'Cookie': 'solvai_session=' + token})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_future_admin_routes_and_exports_fail_closed(self):
        for path in ['/api/admin/distribution/shadow', '/api/admin/distribution/export?token=private',
                     '/api/admin/finance/ingest', '/api/finance/ingestion',
                     '/api/admin/documents/private/download']:
            for method in ['GET', 'POST', 'DELETE', 'PUT', 'PATCH']:
                self.assertEqual(self.call(method, path, 'missing')[0], 401)
                status, body = self.call(method, path)
                self.assertEqual(status, 403)
                self.assertEqual(body['error']['code'], 'ACCESS_DENIED')
        with server.database() as db:
            events = db.execute('SELECT actor, action, status FROM audit_events').fetchall()
        self.assertTrue(events)
        self.assertNotIn('private', json.dumps(events))
        self.assertNotIn('solvai_session', json.dumps(events))

    def test_permissions_follow_server_role_and_revocation(self):
        self.assertEqual(self.call('GET', '/api/permissions', 'missing')[0], 401)
        status, body = self.call('GET', '/api/permissions')
        self.assertEqual(status, 200)
        self.assertFalse(body['permissions']['finance.ingest'])
        self.assertFalse(body['permissions']['distribution.admin'])
        self.authorize()
        self.assertTrue(self.call('GET', '/api/permissions', 'admin')[1]['permissions']['distribution.admin'])
        with server.database() as db:
            db.execute('UPDATE accounts SET disabled=1 WHERE email=?', (server.ADMIN_EMAIL,))
        self.assertEqual(self.call('POST', '/api/admin/distribution/shadow', 'admin')[0], 401)

    def test_analytics_requires_session_and_does_not_claim_engine_exists(self):
        for path in ['/api/research/company/TEST', '/api/portfolio/snapshot', '/api/trades/feasibility']:
            self.assertEqual(self.call('GET', path, 'missing')[0], 401)
            status, body = self.call('GET', path)
            if path.startswith('/api/research/company/') or path=='/api/portfolio/snapshot':
                self.assertEqual(status,200)
                self.assertEqual(body['status'],'UNAVAILABLE')
            else:
                self.assertEqual(status,404)

    def test_owner_persistence_isolated_and_deleted_with_account(self):
        self.authorize()
        member = server.SESSIONS['active']
        admin = server.SESSIONS['admin']
        with server.database() as db:
            security.put_owned(db, member, 'research', 'draft', {'value': 0})
            self.assertEqual(security.get_owned(db, member, 'research', 'draft'), {'value': 0})
            self.assertIsNone(security.get_owned(db, admin, 'research', 'draft'))
            db.execute('DELETE FROM accounts WHERE email=?', (self.email,))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM owned_data').fetchone()[0], 0)

    def test_production_does_not_seed_demo_credentials(self):
        with server.database() as db:
            db.execute('DELETE FROM accounts WHERE email=?', (server.EMAIL.casefold(),))
            db.execute("DELETE FROM settings WHERE key='demo-initialized'")
        with patch.object(server, 'PRODUCTION', True):
            with server.database() as db:
                self.assertIsNone(db.execute('SELECT 1 FROM accounts WHERE email=?', (server.EMAIL.casefold(),)).fetchone())
            connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
            connection.request('POST', '/api/login', json.dumps({'email': self.email, 'password': 'Original123!'}), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('; Secure', response.getheader('Set-Cookie'))
            response.read()
            connection.close()
