import unittest
from finance.contracts import envelope,compatible
class ContractTests(unittest.TestCase):
 def fact(self,**kw):return {'id':'source','definition_id':'revenue','value':'0','unit':'currency','currency':'USD','status':'READY','origin':'ACTUAL','period_start':'2025-01-01','period_end':'2025-12-31','period_type':'FY','accounting_basis':'GAAP','scope':'consolidated','restatement_basis':'original','known_at':'2026-01-01T00:00:00Z','source_ids':['source'],'calculation_version':'v1',**kw}
 def test_zero_missing_and_invalid(self):
  self.assertEqual(envelope(self.fact())['value'],'0')
  for value in ('NaN','Infinity',float('inf'),True):
   with self.assertRaises((ValueError,ArithmeticError)):envelope(self.fact(value=value))
  self.assertIsNone(envelope(self.fact(value=None,status='UNAVAILABLE'))['value'])
  with self.assertRaises(ValueError):envelope(self.fact(value=None))
 def test_compatibility_definition_and_context(self):
  a=self.fact()
  for change in ({'currency':'EUR'},{'scope':'parent'},{'period_type':'YTD'},{'definition_id':'cfo'}):self.assertFalse(compatible(a,self.fact(**change)))
  self.assertTrue(compatible(a,self.fact()))
 def test_max_known_at_and_stable_lineage(self):
  a=envelope(self.fact());b=envelope(self.fact(id='b',known_at='2026-01-01T02:00:00+03:00',source_ids=['b']))
  r=envelope(self.fact(id='derived',origin='DERIVED'),[a,b])
  self.assertEqual(r['known_at'],a['known_at']);self.assertEqual(r['input_ids'],['source','b']);self.assertEqual(r['source_ids'],['source','b'])
  self.assertEqual(envelope(self.fact()),envelope(self.fact()))
