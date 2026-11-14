import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import financial_sources
import sec_filings

class SourceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.env=patch.dict('os.environ',{'PASION_SEC_USER_AGENT':''});self.env.start();self.addCleanup(self.env.stop)
  sec_filings.CACHE.clear();sec_filings.ATTEMPTS.clear()
 def result(self):
  return {'version':1,'ticker':'MSFT','source_status':'SEC_MACHINE_XBRL_NOT_HUMAN_REVIEWED','financials':{'status':'READY'},'period_end':'2025-06-30'}
 def configure(self):financial_sources.configure(self.root,'research@example.com')
 def test_configuration_private_and_environment_precedence(self):
  self.configure()
  self.assertEqual(financial_sources.settings(self.root),('Pasion Research research@example.com','local'))
  self.assertNotIn('research@example.com',json.dumps(financial_sources.catalog(self.root,True)))
  with patch.dict('os.environ',{'PASION_SEC_USER_AGENT':'Other contact@example.org'}):
   self.assertEqual(financial_sources.settings(self.root)[1],'environment')
   with self.assertRaises(ValueError):self.configure()
 def test_invalid_contacts_and_corrupt_config(self):
  for value in ['',None,'abc','foo@example.com\r\nHeader: evil','a'*170+'@example.com']:
   with self.assertRaises(ValueError):financial_sources.configure(self.root,value)
  path=financial_sources.directory(self.root)/'config.json';path.parent.mkdir(exist_ok=True);path.write_text('[]')
  self.assertFalse(financial_sources.catalog(self.root)['sec_configured'])
 def test_disk_cache_survives_restart_and_records_retrieval(self):
  self.configure()
  with patch.object(sec_filings,'build',return_value=self.result()) as build:
   first=sec_filings.research('MSFT',root=self.root)
   self.assertEqual(first['cache_status'],'LIVE');self.assertIn('retrieved_at',first)
   sec_filings.CACHE.clear()
   second=sec_filings.research('MSFT',root=self.root)
   self.assertEqual(second['cache_status'],'FRESH');self.assertEqual(build.call_count,1)
 def test_stale_copy_labeled_on_outage(self):
  self.configure();stamp=time.time()-sec_filings.TTL-1
  financial_sources.atomic_json(financial_sources.directory(self.root)/'sec-MSFT.json',{'cache_version':2,'timestamp':stamp,'result':self.result()})
  with patch.object(sec_filings,'build',side_effect=sec_filings.FilingUnavailable('SEC_NETWORK_UNAVAILABLE')):
   result=sec_filings.research('MSFT',root=self.root)
  self.assertEqual(result['cache_status'],'STALE');self.assertEqual(result['refresh_error'],'SEC_NETWORK_UNAVAILABLE')
 def test_refresh_throttle_and_wrong_ticker_cache(self):
  self.configure()
  with patch.object(sec_filings,'build',return_value=self.result()) as build:
   sec_filings.research('MSFT',root=self.root)
   result=sec_filings.research('MSFT',refresh=True,root=self.root)
   self.assertEqual(result['refresh_error'],'SEC_REFRESH_COOLDOWN');self.assertEqual(build.call_count,1)
  with self.assertRaises(sec_filings.FilingUnavailable):sec_filings.research('../MSFT',root=self.root)
 def test_corrupt_cache_falls_back_to_network(self):
  self.configure();path=financial_sources.directory(self.root)/'sec-MSFT.json';path.write_text('{bad')
  with patch.object(sec_filings,'build',return_value=self.result()) as build:
   self.assertEqual(sec_filings.research('MSFT',root=self.root)['cache_status'],'LIVE');build.assert_called_once()

if __name__=='__main__':unittest.main()
