import unittest
from decimal import Decimal
from finance.portfolio import twr,stress,drawdown
from test_portfolio_ledger import PortfolioTests
import portfolio_ledger as p
class ReturnTests(unittest.TestCase):
 def test_twr_requires_reconciled_external_flows(self):
  self.assertIsNone(twr([])['value'])
  periods=[{'start':'2026-01-01','end':'2026-02-01','opening_value':'100','closing_before_external_flow':'110','reconciled':True,'external_flows_complete':True},{'start':'2026-02-01','end':'2026-03-01','opening_value':'210','closing_before_external_flow':'189','reconciled':True,'external_flows_complete':True}]
  self.assertEqual(Decimal(twr(periods)['value']),Decimal('-.01'))
  periods[0]['external_flows_complete']=False;self.assertIsNone(twr(periods)['value'])
 def test_stress_and_drawdown(self):
  self.assertEqual(Decimal(stress('100','50')['post_stress_value']),Decimal('130'))
  self.assertEqual(Decimal(drawdown([100,120,90])['value']),Decimal('-.25'))
class JournalTests(PortfolioTests):
 def test_journal_replay_owner_and_no_balance_mutation(self):
  p.save(self.db,'one',self.state);event={'request_id':'r1','type':'BUY','ticker':'TEST','quantity':'1','amount':'10','currency':'USD','occurred_at':self.clock.isoformat(),'source_note':'Manual statement entry'}
  first=p.transaction(self.db,'one',event);second=p.transaction(self.db,'one',event);self.assertEqual(first['id'],second['id'])
  snapshot=p.snapshot(self.db,self.root,'one');self.assertEqual(snapshot['state']['cash'],'100');self.assertEqual(len(snapshot['transactions']),1);self.assertEqual(snapshot['lots'][0]['quantity'],'10')
  with self.assertRaises(ValueError):p.transaction(self.db,'two',event)
  self.assertIsNone(snapshot['performance']['twr'])
