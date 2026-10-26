import unittest,tempfile
from pathlib import Path
from datetime import datetime,timezone
from common.time import InformationClocks,MarketSession,ForecastHorizon,eligible_at_origin,derived_known_at
from finance.periods import AccountingPeriod,BalanceAsOf,validate_calendar,quarter_start
import finance_core as f

class ClockPeriodTests(unittest.TestCase):
 def test_clock_origin_and_timezone_semantics(self):
  clocks=InformationClocks('2026-07-01T00:00:00Z','2026-07-28T00:00:00Z','2026-07-28T02:00:00+03:00')
  self.assertFalse(eligible_at_origin(clocks.known_at,'2026-07-01T12:00:00Z'))
  self.assertTrue(eligible_at_origin(clocks.known_at,'2026-07-28T00:00:00Z'))
  self.assertEqual(derived_known_at(['2026-07-28T02:00:00+03:00','2026-07-28T00:00:00Z']),'2026-07-28T00:00:00Z')
 def test_session_completion_is_separate_from_fiscal_duration(self):
  session=MarketSession('XNAS','America/New_York','2026-07-01','2026-07-01T09:30:00-04:00','2026-07-01T16:00:00-04:00',True)
  self.assertFalse(session.bar_eligible('2026-07-01T15:00:00-04:00','2026-07-01T15:00:00-04:00','2026-07-01T15:00:00-04:00'))
  self.assertTrue(session.bar_eligible('2026-07-01T16:00:00-04:00','2026-07-01T20:01:00Z','2026-07-01T20:02:00Z'))
  with self.assertRaises(ValueError):ForecastHorizon('DAYS',30)
  self.assertEqual(ForecastHorizon('COMPLETED_SESSIONS',30).count,30)
 def test_noncalendar_quarter_ytd_and_standalone(self):
  calendar={'year':'FY25','start':'2024-07-01','end':'2025-06-30','quarter_ends':['2024-09-30','2024-12-31','2025-03-31','2025-06-30']}
  validate_calendar(calendar);self.assertEqual(quarter_start(calendar,1),'2024-10-01')
  AccountingPeriod('TEST','FY25','YTD','2024-07-01','2024-12-31');BalanceAsOf('TEST','2024-12-31')
  def fact(value,start,end,kind):return {'id':kind+end,'definition_id':'revenue','value':value,'scale':'1','period_start':start,'period_end':end,'period_type':kind,'currency':'USD','unit':'currency','scope':'consolidated','accounting_basis':'GAAP','restatement_basis':'original','revision':'1','report_id':'r','reviewed':True,'evidence':{'page':1,'table':'Income','tag':'Revenue'}}
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);now=datetime(2025,1,30,tzinfo=timezone.utc)
   payload={'issuer':{'ticker':'TEST','name':'Test'},'calendar':calendar,'reports':[{'id':'r','document_id':'d','published_at':'2025-01-01T00:00:00Z','indexed_at':'2025-01-28T00:00:00Z'}],'facts':[fact('100','2024-07-01','2024-09-30','Q'),fact('240','2024-07-01','2024-12-31','YTD')]}
   f.ingest(root,payload,'reviewer',now)
   self.assertEqual(f.company(root,'TEST','Q','2024-12-31')['metrics']['revenue']['value'],'140')
   self.assertIsNone(f.company(root,'TEST','TTM','2024-12-31')['metrics']['revenue']['value'])
   self.assertIsNone(f.company(root,'TEST','Q','2024-12-31','2025-01-01T00:00:00Z')['metrics']['revenue']['value'])
   payload['reports'][0]['id']='r2';standalone=fact('140','2024-10-01','2024-12-31','Q');standalone.update(id='standalone',report_id='r2');payload['facts']=[standalone]
   f.ingest(root,payload,'reviewer',now)
   self.assertEqual(f.company(root,'TEST','Q','2024-12-31')['metrics']['revenue']['value'],'140')
