"""Offline tests for SEC companyfacts adapter. No web requests or account writes."""
import unittest
from unittest.mock import patch
from datetime import date
import sec_filings

class SecAdapterTests(unittest.TestCase):
 def test_missing_agent_uses_aapl_reference_only(self):
  with patch.dict('os.environ',{'PASION_SEC_USER_AGENT':''}):
   result=sec_filings.research('AAPL')
   self.assertEqual(result['ticker'],'AAPL')
   self.assertEqual(result['financials']['metrics']['revenue']['value'],'416161000000')
   self.assertEqual(result['source_status'],'CURATED_2025_SEC_REFERENCE_NOT_AUTO_SCAN')
   self.assertTrue(result['review_required_for_valuation'])
   with self.assertRaises(sec_filings.FilingUnavailable):sec_filings.research('MSFT')
 def test_quarter_validation_with_explicit_fiscal_calendar(self):
  filing={'start':'2024-09-29','end':'2025-09-27','fy':2025}
  observations=[
   {'form':'10-Q','fp':'Q1','end':'2024-12-28','fy':2025,'filed':'2025-01-31'},
   {'form':'10-Q','fp':'Q2','end':'2025-03-29','fy':2025,'filed':'2025-05-01'},
   {'form':'10-Q','fp':'Q3','end':'2025-06-28','fy':2025,'filed':'2025-08-01'}]
  gaap={'Revenues':{'units':{'USD':observations}}}
  self.assertEqual(sec_filings.fiscal_quarters(gaap,filing),['2024-12-28','2025-03-29','2025-06-28','2025-09-27'])
  with self.assertRaises(sec_filings.FilingUnavailable):sec_filings.fiscal_quarters({'Revenues':{'units':{'USD':observations[:2]}}},filing)
 def test_ambiguous_sec_tags_fail_closed(self):
  filing={'start':'2024-09-29','end':'2025-09-27','accn':'0000320193-25-000079'}
  gaap={'NetIncomeLoss':{'units':{'USD':[
   {'start':filing['start'],'end':filing['end'],'accn':filing['accn'],'form':'10-K','val':100},
   {'start':filing['start'],'end':filing['end'],'accn':filing['accn'],'form':'10-K','val':200}]}}}
  with self.assertRaises(sec_filings.FilingUnavailable):sec_filings.find_value(gaap,'net_income',filing)
if __name__=='__main__':unittest.main()
