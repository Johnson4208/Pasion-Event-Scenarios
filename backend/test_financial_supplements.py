import copy,json,unittest
from pathlib import Path
from decimal import Decimal
import public_financials as public
import report_supplements
class Supplements(unittest.TestCase):
 def snapshot(self):
  f=Path(__file__).parent/'fixtures'/'public_financials'
  d=lambda n:json.loads((f/('fpt-'+n+'.json')).read_text(encoding='utf-8'))
  return public.normalize('FPT',d('summary'),d('balance'),d('cash'),d('income'))
 def test_missing_direct_lines_and_ratios(self):
  m=self.snapshot()['financials']['metrics']
  for k,v in {'gross_revenue':'70207688944553','revenue_deductions':'94863843843','nci_profit':'1856211821233','sga':'14899986038258','ppe':'15359168484059','depreciation_cf':'2914178360732'}.items():self.assertEqual(m[k]['value'],v,k)
  self.assertEqual(Decimal(m['gross_revenue']['value'])-Decimal(m['revenue_deductions']['value']),Decimal(m['revenue']['value']))
  self.assertEqual(m['liabilities_equity']['value'],m['assets']['value'])
 def test_primary_pdf_cash_flow_and_shares(self):
  m=report_supplements.enrich(self.snapshot())['financials']['metrics']
  self.assertEqual(m['capex']['value'],'5097919349856')
  self.assertEqual(m['free_cash_flow']['value'],'5038124566055')
  self.assertEqual(m['shares_outstanding_fy']['value'],'1703507121')
  self.assertIn('#page=171',m['capex']['source_url'])
  self.assertFalse(m['capex']['human_reviewed'])
  self.assertEqual(m['ebitda_margin']['status'],'UNAVAILABLE')
 def test_does_not_apply_to_other_issuer_year_or_inconsistent_inputs(self):
  for key,value in [('ticker','HPG'),('period_end','2026'),('market','US')]:
   s=self.snapshot();s[key]=value;report_supplements.enrich(s);self.assertEqual(s['financials']['metrics']['capex']['status'],'UNAVAILABLE')
  s=self.snapshot();s['financials']['metrics']['revenue']['value']='1';report_supplements.enrich(s);self.assertEqual(s['financials']['metrics']['capex']['status'],'UNAVAILABLE')
