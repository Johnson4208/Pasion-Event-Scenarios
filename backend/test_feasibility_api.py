import http.client
import json
import unittest
from datetime import datetime,timedelta,timezone
import test_server as fixtures


class TradeApiTests(unittest.TestCase):
    setUp=fixtures.ChangePasswordTests.setUp
    tearDown=fixtures.ChangePasswordTests.tearDown
    authorize=fixtures.AdminTests.authorize

    def call(self,path,data,token='active'):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        connection.request('POST',path,json.dumps(data),{'Content-Type':'application/json','Cookie':'solvai_session='+token})
        response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result

    def test_permissions_and_owner_cannot_be_spoofed(self):
        draft={'ticker':'TEST','entry':'100','stop':'95','target':'110','risk':'1','capital':'999999'}
        self.assertEqual(self.call('/api/trades/feasibility',draft,'missing')[0],401)
        self.assertEqual(self.call('/api/admin/trades/instruments',{})[0],403)
        self.assertEqual(self.call('/api/admin/portfolio/review',{})[0],403)
        self.assertEqual(self.call('/api/trades/feasibility',draft)[1]['quantity'],None)

    def test_manual_baseline_needs_review_and_admins_do_not_read_member_account(self):
        self.authorize();stamp=datetime.now(timezone.utc)
        baseline={'owner':'fake@example.com','currency':'USD','equity':'10000','cash':'1000','reserved_cash':'0','sellable':{},'as_of':stamp.isoformat(),'expires_at':(stamp+timedelta(hours=1)).isoformat(),'status':'REVIEWED'}
        self.assertEqual(self.call('/api/portfolio/baseline',baseline)[1]['status'],'MANUAL_UNVERIFIED')
        self.assertEqual(self.call('/api/admin/portfolio/review',{'owner':self.email},'admin')[0],200)
        rules={'ticker':'TEST','venue':'TEST','currency':'USD','lot':'10','tick':'1','fee_flat':'0','fee_per_share':'0','fee_rate':'0','sell_tax_rate':'0','slippage_bps':'0','calendar':'explicit-provider-session','source':'API test fixture','reviewed':True,
          'quote':{'price':'100','as_of':stamp.isoformat(),'session_open':(stamp-timedelta(hours=1)).isoformat(),'session_close':(stamp+timedelta(hours=1)).isoformat(),'max_age_seconds':'60'}}
        self.assertEqual(self.call('/api/admin/trades/instruments',rules,'admin')[0],200)
        draft={'ticker':'TEST','entry':'100','stop':'95','target':'110','risk':'1'}
        self.assertEqual(self.call('/api/trades/feasibility',draft)[1]['quantity'],10)
        self.assertEqual(self.call('/api/trades/feasibility',{**draft,'owner':self.email},'admin')[1]['quantity'],None)
