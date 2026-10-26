import unittest
from market.outcomes import first_touch,summarize
from test_feasibility import FeasibilityTests
import feasibility
class OutcomeTests(unittest.TestCase):
 def test_liquidity_lot_cap_and_gap_risk(self):
  fixture=FeasibilityTests();fixture.setUp();fixture.account['cash']='100000';fixture.rules['liquidity_max_quantity']='17'
  result=fixture.check();self.assertEqual(result['quantity'],10);self.assertEqual(result['liquidity_status'],'REVIEWED_CAP')
  fixture.rules.pop('liquidity_max_quantity');normal=fixture.check();stress=fixture.check(risk_basis='GAP_STRESS',gap_slippage_pct='20')
  self.assertLess(stress['quantity'],normal['quantity'])
 def bar(self,open=100,high=101,low=99,close=100):return {'open':open,'high':high,'low':low,'close':close,'complete':True}
 def test_collision_stop_first_and_gap_at_open(self):
  bars=[self.bar(),self.bar(),self.bar(high=111,low=89)]
  r=first_touch(bars,0,2,90,110);self.assertEqual(r['outcome'],'STOP');self.assertEqual(r['exit'],'90')
  bars[2]=self.bar(open=80,high=85,low=75,close=80);r=first_touch(bars,0,2,90,110);self.assertEqual(r['outcome'],'STOP_GAP');self.assertEqual(r['net_pnl'],'-20')
 def test_unresolved_closes_at_horizon_and_counts_all_paths(self):
  r=first_touch([self.bar(),self.bar(),self.bar(close=103,high=104)],0,2,90,110)
  self.assertEqual(r['outcome'],'UNRESOLVED');self.assertEqual(r['net_pnl'],'3')
  paths=[dict(r,outcome='TARGET')]*40+[dict(r,outcome='STOP')]*20+[r]*40
  s=summarize(paths);self.assertAlmostEqual(s['conditional_target_hit'],40/60);self.assertEqual(s['unconditional_target_hit'],.4)
 def test_unmatured_and_next_open_gap_not_assumed_fill(self):
  self.assertEqual(first_touch([self.bar()],0,1,90,110)['status'],'UNAVAILABLE')
  self.assertEqual(first_touch([self.bar(),self.bar(open=80)],0,1,90,110)['status'],'WITHHELD')
