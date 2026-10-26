import unittest
from decimal import Decimal
from finance.forecast import operating_year,REQUIRED
class ForecastTests(unittest.TestCase):
 def drivers(self):return dict(zip(REQUIRED,['.1','.2','.25','.03','.05','.1','.01','.005','.02']))
 def test_cash_bridges_reconcile_and_base_unchanged(self):
  d=self.drivers();row=operating_year('1000','100',d,'2027-12-31','USD')
  self.assertEqual(row['revenue'],'1100.0');self.assertEqual(row['delta_nwc'],'10.00')
  self.assertEqual(sum(Decimal(v) for v in row['waterfall']['fcff'].values()),Decimal(row['fcff']))
  self.assertEqual(sum(Decimal(v) for v in row['waterfall']['fcfe'].values()),Decimal(row['fcfe']))
  self.assertEqual(d,self.drivers())
 def test_missing_capex_or_working_capital_blocks(self):
  for key in ('capex_pct','nwc_pct'):
   d=self.drivers();del d[key]
   with self.assertRaises(ValueError):operating_year('1000','100',d,'2027-12-31','USD')
