from test_finance_core import FinanceTests
import finance_core as f

class ProfitabilityTests(FinanceTests):
 def test_standard_ebitda_ttm_bridge_535(self):
  prior=[self.fact('ebit','400',start='2023-01-01',end='2023-12-31',kind='FY',report_id='report-2023'),self.fact('da_expense','100',start='2023-01-01',end='2023-12-31',kind='FY',report_id='report-2023',da_eligible=True),self.fact('ebit','200',start='2023-01-01',end='2023-06-30',kind='YTD',report_id='report-2023'),self.fact('da_expense','40',start='2023-01-01',end='2023-06-30',kind='YTD',report_id='report-2023',da_eligible=True)]
  self.ingest(prior,year=2023)
  self.ingest([self.fact('ebit','225',end='2024-06-30',kind='YTD'),self.fact('da_expense','50',end='2024-06-30',kind='YTD',da_eligible=True)])
  self.assertEqual(f.company(self.root,'TEST','TTM','2024-06-30')['metrics']['ebitda']['value'],'535')
 def test_standard_ebitda_excludes_reported_proxy_and_balance_da(self):
  self.ingest([self.fact('ebit','100'),self.fact('da_expense','20',da_eligible=True),self.fact('reported_ebitda','999'),self.fact('proxy_ebitda','888'),self.fact('accumulated_depreciation','500',start='2024-03-31',kind='INSTANT')])
  metrics=f.company(self.root,'TEST','Q','2024-03-31')['metrics']
  self.assertEqual(metrics['ebitda']['value'],'120');self.assertEqual(metrics['proxy_ebitda']['origin'],'PROXY');self.assertIn('STANDARD_EBIT_PLUS_ELIGIBLE_PERIOD_DA',metrics['ebitda']['basis_flags'])
 def test_opening_common_equity_required_and_returns_period_preserved(self):
  self.ingest([self.fact('net_income_common','10'),self.fact('common_equity','100',start='2024-03-31',kind='INSTANT')])
  self.assertIsNone(f.company(self.root,'TEST','Q','2024-03-31')['metrics']['roe']['value'])
 def test_matching_period_margin_and_no_quarter_annualization(self):
  self.ingest([self.fact('revenue','100'),self.fact('cfo','50',end='2024-06-30',kind='YTD'),self.fact('ebit','100'),self.fact('da_expense','20',da_eligible=True),self.fact('debt','240',start='2024-03-31',kind='INSTANT')])
  metrics=f.company(self.root,'TEST','Q','2024-03-31')['metrics']
  self.assertIsNone(metrics['cfo_margin']['value']);self.assertIsNone(metrics['debt_ebitda']['value'])
