import sqlite3
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch
import valuation as v


class ValuationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY)')
        self.db.executemany('INSERT INTO accounts VALUES (?)',[('one@example.com',),('two@example.com',)])
        self.today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
        end=date(self.today.year-1,12,31)
        self.base={'version':1,'company':{'ticker':'TEST','name':'Test'},'period':'FY','period_end':end.isoformat(),'metrics':{}}
        amounts={'revenue':100,'ebit':20,'ebitda':26,'operating_nwc':10,'diluted_shares':10,'net_income_common':12,'debt':10,'cash':5,'restricted_cash':0,'lease_debt':0,'eps':1.2,'dividend_per_share':.5}
        for k,amount in amounts.items():
            self.base['metrics'][k]={'definition_id':k,'value':str(amount),'unit':'currency/share' if k in ('eps','dividend_per_share') else 'shares' if k=='diluted_shares' else 'currency','currency':'USD','scope':'consolidated','accounting_basis':'GAAP','restatement_basis':'original','period_end':end.isoformat(),'period_start':date(end.year,1,1).isoformat(),'status':'READY','source_ids':[k],'known_at':datetime.now(timezone.utc).isoformat()}
        self.values={'sector_policy':'industrial','revenue_growth':'.05','ebit_margin':'.2','tax_rate':'.2','da_pct':'.06','capex_pct':'.08','nwc_pct':'.1','interest_pct':'.01','nci_income_pct':'0','net_borrowing_pct':'0','risk_free_rate':'.03','beta':'1','equity_risk_premium':'.06','debt_cost':'.05','debt_weight':'.2','terminal_growth':'.02','terminal_stability':'1','nci_value':'0','nonoperating_value':'0','pe_multiple':'15','dividend_growth':'.02','recurring_dividend':'1','next_dividend_date':(self.today+timedelta(days=365)).isoformat(),'adjusted_equity_value':'80'}

    def tearDown(self):
        self.db.close()

    def assumptions(self,verified=True,**overrides):
        values=dict(self.values,**overrides)
        rows=[{'definition':k,'value':value,'unit':v.UNITS[k],'currency':'USD','effective_from':'2020-01-01T00:00:00Z','source_ids':['evidence']} for k,value in values.items()]
        saved=v.register(self.db,'one@example.com','TEST','base',rows)
        if verified:
            with patch.object(v.finance,'evidence',return_value={'ticker':'TEST','status':'READY','currency':'USD'}):
                v.review(self.db,Path('.'),'one@example.com',[a['id'] for a in saved])
        return saved

    def run_model(self,owner='one@example.com',scenario='base'):
        with patch.object(v.finance,'company',return_value=self.base):
            result=v.calculate(self.db,Path('.'),owner,{'ticker':'TEST','period':'FY','scenario':scenario,'valuation_date':self.today.isoformat()})
        return {row['method']:row for row in result['methods']},result

    def test_unverified_assumptions_cannot_create_estimates(self):
        self.assumptions(False)
        methods,result=self.run_model()
        self.assertTrue(all(r['status']=='WITHHELD' and r['value'] is None for r in methods.values()))
        self.assertFalse(result['forecast'])

    def test_verified_operating_bridges_and_method_sensitivity(self):
        self.assumptions()
        methods,result=self.run_model()
        self.assertTrue(all(r['status']=='READY' for r in methods.values()))
        self.assertEqual(len(result['forecast']),5)
        row=result['forecast'][0]
        self.assertEqual(Decimal(row['fcff']),Decimal(row['ebit'])-Decimal(row['tax'])+Decimal(row['da'])-Decimal(row['capex'])-Decimal(row['delta_nwc']))
        self.assertEqual(Decimal(row['fcfe']),Decimal(row['net_income_common'])+Decimal(row['da'])-Decimal(row['capex'])-Decimal(row['delta_nwc'])+Decimal(row['net_borrowing']))
        self.assertEqual(len(methods['FCFF']['sensitivity']),11)
        self.assertEqual(methods['DDM']['details']['evidence_family'],'DIVIDEND')
        self.assertEqual(methods['Gordon']['details']['evidence_family'],'DIVIDEND')
        self.assertAlmostEqual(float(methods['DDM']['value']),float(methods['DDM']['sensitivity'][1]['value']),places=8)
        self.assertNotIn('consensus',result)

    def test_bank_does_not_inherit_industrial_dcf(self):
        self.assumptions(sector_policy='bank')
        methods,_=self.run_model()
        self.assertEqual(methods['FCFF']['status'],'WITHHELD')
        self.assertEqual(methods['FCFE']['status'],'WITHHELD')
        self.assertEqual(methods['P/E']['status'],'READY')

    def test_invalid_terminal_rate_and_earnings_gate_methods(self):
        self.assumptions(terminal_growth='.5',dividend_growth='.5')
        self.base['metrics']['eps']['value']='-1'
        methods,_=self.run_model()
        for name in ('FCFF','FCFE','DDM','Gordon','P/E'):
            self.assertEqual(methods[name]['status'],'WITHHELD')

    def test_missing_diluted_shares_and_zero_are_not_defaults(self):
        self.assumptions()
        self.base['metrics']['diluted_shares'].update(status='UNAVAILABLE',value=None)
        methods,_=self.run_model()
        self.assertEqual(methods['FCFF']['status'],'WITHHELD')
        self.assertEqual(methods['Asset-based']['status'],'WITHHELD')

    def test_assumptions_are_owner_scoped_and_scenarios_explicit(self):
        self.assumptions()
        methods,_=self.run_model('two@example.com')
        self.assertTrue(all(r['status']=='WITHHELD' for r in methods.values()))
        methods,_=self.run_model(scenario='upside')
        self.assertTrue(all(r['status']=='WITHHELD' for r in methods.values()))

    def test_review_requires_accepted_evidence(self):
        saved=self.assumptions(False)
        with patch.object(v.finance,'evidence',return_value=None):
            with self.assertRaises(ValueError):
                v.review(self.db,Path('.'),'one@example.com',[saved[0]['id']])
