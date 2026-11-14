import unittest
import http.client
from pathlib import Path
from unittest.mock import patch
import test_finance_api
import server

class SourceApiTests(test_finance_api.FinanceApiTests):
 def test_public_report_archive_requires_session_and_never_accepts_arbitrary_url(self):
  self.assertEqual(self.call('GET','/api/research/reports/FPT?market=VN',token='missing')[0],401)
  with patch.object(server.financial_reports,'catalog',return_value={'version':1,'ticker':'FPT','market':'VN','reports':[]}) as read:
   self.assertEqual(self.call('GET','/api/research/reports/FPT?market=VN&year=2025')[0],200)
   read.assert_called_once_with(server.ROOT,'FPT','VN','2025',False)
  self.assertEqual(self.call('GET','/api/research/reports/FPT?market=BAD')[0],422)
  identity='a'*24
  with patch.object(server.financial_reports,'download',side_effect=server.financial_reports.ReportError('REPORT_NOT_FOUND')):
   self.assertEqual(self.call('GET','/api/research/reports/FPT/'+identity+'?market=VN')[0],422)
 def test_download_returns_original_pdf_as_private_attachment(self):
  path=Path(server.ROOT)/'test-original.pdf';path.write_bytes(b'%PDF-1.7\nOriginal filing')
  identity='b'*24
  with patch.object(server.financial_reports,'download',return_value=(path,{'year':2025,'id':identity})):
   connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
   connection.request('GET','/api/research/reports/FPT/'+identity+'?market=VN',headers={'Cookie':'solvai_session=active'})
   response=connection.getresponse()
   self.assertEqual(response.status,200);self.assertEqual(response.getheader('Content-Type'),'application/pdf')
   self.assertIn('attachment',response.getheader('Content-Disposition'))
   self.assertEqual(response.read(),b'%PDF-1.7\nOriginal filing');connection.close()
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
