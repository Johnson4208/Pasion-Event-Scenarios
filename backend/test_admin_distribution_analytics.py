import unittest,sqlite3,json,sys,os
sys.path.insert(0,os.path.dirname(__file__))
import admin_distribution_analytics as analytics

class AdminTradingMonitorTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:')
  self.db.execute('PRAGMA foreign_keys=ON')
  self.db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY)')
  for email in ['a@example.org','b@example.org']:self.db.execute('INSERT INTO accounts VALUES (?)',(email,))
 def tearDown(self): self.db.close()
 def test_no_broker_volume_inferred(self):
  out=analytics.overview(self.db)
  self.assertIsNone(out['broker_confirmed']['executed_notional'])
  self.assertEqual(out['distribution']['candidate_count'],0)
 def test_manual_transaction_breakdown_by_currency(self):
  import portfolio_ledger
  portfolio_ledger.initialize(self.db)
  for i,(owner,cur,amount) in enumerate([('a@example.org','VND','500000'),('b@example.org','USD','100'),('a@example.org','VND','250000')]):
   p={'type':'BUY','ticker':'FPT','currency':cur,'quantity':'10','amount':amount}
   self.db.execute('INSERT INTO portfolio_transactions VALUES(?,?,?,?)',(str(i),owner,str(i),json.dumps(p)))
  out=analytics.overview(self.db)
  self.assertEqual(out['manual_activity']['trade_records'],3)
  totals={x['currency']:x['notional'] for x in out['manual_activity']['by_currency']}
  self.assertEqual(totals,{'USD':'100','VND':'750000'})
  self.assertIsNone(out['broker_confirmed']['top_executed_accounts'])
  self.assertEqual(out['manual_activity']['top_accounts'][0]['basis'],'MANUAL_UNRECONCILED_NOT_EXECUTED')
if __name__=='__main__':unittest.main()
