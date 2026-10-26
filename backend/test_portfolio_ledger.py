import sqlite3
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import portfolio_ledger as p
import feasibility


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.db=sqlite3.connect(':memory:');self.db.execute('PRAGMA foreign_keys=ON');self.db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY)')
        self.db.executemany('INSERT INTO accounts VALUES (?)',[('one',),('two',)])
        self.clock=datetime.now(timezone.utc)
        self.state={'expected_revision':0,'currency':'USD','cash':'100','reserved_cash':'0','as_of':self.clock.isoformat(),'source':'MANUAL_CONFIRMED','lots':[{'id':'lot1','ticker':'TEST','quantity':'10','unit_cost':'5','currency':'USD','sector':'Technology'}],'watchlist':['WATCH'],'targets':[]}

    def tearDown(self):self.db.close();self.temp.cleanup()

    def quote(self,currency='USD'):
        feasibility.instrument(self.db,{'ticker':'TEST','venue':'Test','currency':currency,'lot':'1','tick':'1','fee_flat':'0','fee_per_share':'0','fee_rate':'0','sell_tax_rate':'0','slippage_bps':'0','calendar':'Test','source':'Synthetic fixture','reviewed':True,'quote':{'price':'10','as_of':self.clock.isoformat(),'session_open':(self.clock-timedelta(hours=1)).isoformat(),'session_close':(self.clock+timedelta(hours=1)).isoformat(),'max_age_seconds':'600'}})

    def test_missing_price_never_changes_denominator_or_manufactures_cash(self):
        p.save(self.db,'one',self.state)
        result=p.snapshot(self.db,self.root,'one')
        self.assertIsNone(result['total_value']);self.assertIsNone(result['concentration'])
        self.assertEqual(result['state']['cash'],'100')
        self.assertEqual(result['sector_exposure']['Technology']['unknown_lots'],1)
        self.assertIsNone(result['sector_exposure']['Technology']['weight'])
        self.assertEqual(len(result['lots']),1)

    def test_zero_cash_and_complete_marks_keep_lot_cost_and_gate_performance(self):
        self.state['cash']='0';p.save(self.db,'one',self.state);self.quote()
        result=p.snapshot(self.db,self.root,'one')
        self.assertEqual(result['total_value'],'100')
        self.assertEqual(result['unrealized_pnl'],'50')
        self.assertIsNone(result['performance']['twr'])
        self.assertNotIn('WATCH',[lot['ticker'] for lot in result['lots']])

    def test_owner_isolation_and_revision_conflicts(self):
        p.save(self.db,'one',self.state)
        self.assertEqual(p.snapshot(self.db,self.root,'two')['revision'],0)
        with self.assertRaises(RuntimeError):p.save(self.db,'one',self.state)
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_events').fetchone()[0],1)

    def test_missing_fx_and_historical_cost_fx_withhold_pnl(self):
        self.state['lots'][0]['currency']='EUR';p.save(self.db,'one',self.state);self.quote('EUR')
        self.assertIsNone(p.snapshot(self.db,self.root,'one')['total_value'])
        p.register_fx(self.db,{'from':'EUR','to':'USD','rate':'2','as_of':self.clock.isoformat(),'expires_at':(self.clock+timedelta(hours=1)).isoformat(),'source':'Test FX','reviewed':True})
        result=p.snapshot(self.db,self.root,'one')
        self.assertEqual(result['total_value'],'300')
        self.assertIsNone(result['unrealized_pnl'])

    def test_edit_invalidates_reviewed_feasibility_and_account_delete_cascades(self):
        feasibility.baseline(self.db,'one',{'currency':'USD','equity':'1000','cash':'100','reserved_cash':'0','sellable':{},'as_of':self.clock.isoformat(),'expires_at':(self.clock+timedelta(hours=1)).isoformat()})
        feasibility.review_account(self.db,'one');p.save(self.db,'one',self.state)
        import json
        self.assertEqual(json.loads(self.db.execute('SELECT payload FROM trading_accounts').fetchone()[0])['status'],'MANUAL_UNVERIFIED')
        with self.assertRaises(ArithmeticError):feasibility.review_account(self.db,'one')
        self.db.execute('DELETE FROM accounts WHERE email=?',('one',))
        self.assertEqual(self.db.execute('SELECT count(*) FROM portfolio_states').fetchone()[0],0)

    def test_risk_contributions_reconcile_and_missing_series_is_not_reweighted(self):
        returns={'ONE':[.01,-.01]*30,'TWO':[.005,-.002]*30}
        result=p.contributions({'ONE':.4,'TWO':.3},returns)
        self.assertAlmostEqual(sum(result['components'].values()),result['daily_volatility'])
        self.assertEqual(p.contributions({'ONE':.4,'TWO':.3},{'ONE':returns['ONE']})['status'],'UNAVAILABLE')
