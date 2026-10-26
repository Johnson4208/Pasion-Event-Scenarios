import unittest
from finance.quality import screen
class QualityTests(unittest.TestCase):
 def metric(self,key,value):return {'definition_id':key,'value':value,'status':'READY','id':key,'source_ids':[key],'currency':'USD','scope':'consolidated','ownership':'parent_and_subsidiaries','accounting_basis':'GAAP','restatement_basis':'original','period_start':'2025-01-01','period_end':'2025-12-31','period_type':'FY','known_at':'2026-01-01T00:00:00Z'}
 def test_missing_no_penalty_and_beneish_incomplete(self):
  r=screen({},{});self.assertEqual(r['coverage']['eligible'],0);self.assertEqual(r['flags'],[]);self.assertIsNone(r['fraud_probability']);self.assertIsNone(r['beneish']['value'])
 def test_zero_income_not_divided_and_decline_not_fraud(self):
  r=screen({'net_income':self.metric('net_income','0'),'cfo':self.metric('cfo','10'),'net_margin':self.metric('net_margin','5')},{'net_margin':self.metric('net_margin','10')})
  conversion=next(d for d in r['diagnostics'] if d['definition_id']=='cfo_conversion');self.assertIsNone(conversion['value']);self.assertEqual(r['flags'],[])
 def test_missing_ownership_withholds_quality_diagnostic(self):
  metric=self.metric('cfo','20');income=self.metric('net_income','10')
  del metric['ownership'];del income['ownership']
  result=screen({'cfo':metric,'net_income':income},{})
  diagnostic=next(d for d in result['diagnostics'] if d['definition_id']=='cfo_conversion')
  self.assertEqual(diagnostic['status'],'UNAVAILABLE')
  self.assertEqual(diagnostic['reason_codes'],['MISSING_OR_INCOMPATIBLE_ACCOUNTING_CONTEXT'])
 def test_negative_cash_flags_source_relationship_only(self):
  r=screen({'net_income':self.metric('net_income','10'),'cfo':self.metric('cfo','-5')},{})
  self.assertEqual(r['flags'][0]['code'],'POSITIVE_INCOME_NEGATIVE_OPERATING_CASH');self.assertEqual(r['flags'][0]['source_ids'],['cfo','net_income'])
