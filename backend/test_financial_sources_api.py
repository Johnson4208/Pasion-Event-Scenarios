import unittest
from unittest.mock import patch
import test_finance_api
import server

class SourceApiTests(test_finance_api.FinanceApiTests):
 def test_source_configuration_permissions_and_contact_privacy(self):
  with patch.dict('os.environ',{'PASION_SEC_USER_AGENT':''}):
   self.assertEqual(self.call('GET','/api/research/financial-sources',token='missing')[0],401)
   self.assertEqual(self.call('POST','/api/admin/financial-sources',{'email':'contact@example.com'})[0],403)
   self.authorize()
   status,data=self.call('POST','/api/admin/financial-sources',{'email':'contact@example.com'},token='admin')
   self.assertEqual(status,200);self.assertTrue(data['sec_configured'])
   status,data=self.call('GET','/api/research/financial-sources')
   self.assertEqual(status,200);self.assertFalse(data['can_configure']);self.assertNotIn('contact@example.com',str(data))
   self.assertEqual(self.call('POST','/api/admin/financial-sources',{'email':'bad'},token='admin')[0],400)
 def test_sec_uses_application_storage_root(self):
  with patch.object(server.sec_filings,'research',return_value={'version':1}) as read:
   self.assertEqual(self.call('GET','/api/research/sec/MSFT?refresh=1')[0],200)
   read.assert_called_once_with('MSFT',True,root=server.ROOT)
 def test_automatic_financials_require_session_and_route_market(self):
  self.assertEqual(self.call('GET','/api/research/financials/FPT?market=VN',token='missing')[0],401)
  with patch.object(server.public_financials,'research',return_value={'version':1,'ticker':'FPT','market':'VN'}) as read:
   self.assertEqual(self.call('GET','/api/research/financials/FPT?market=VN&refresh=1')[0],200)
   read.assert_called_once_with(server.ROOT,'FPT','VN',True)
  self.assertEqual(self.call('GET','/api/research/financials/FPT?market=BAD')[0],422)
  with patch.object(server.public_financials,'research',side_effect=server.public_financials.Unavailable('NO_PUBLIC_FINANCIALS')):
   status,data=self.call('GET','/api/research/financials/UNKNOWN?market=VN')
   self.assertEqual(status,422);self.assertEqual(data['reason_code'],'NO_PUBLIC_FINANCIALS')

if __name__=='__main__':unittest.main()
