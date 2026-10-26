import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import feasibility as f


class FeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.clock=datetime.now(timezone.utc)
        self.account={'status':'REVIEWED','currency':'USD','equity':'100000','cash':'1000','reserved_cash':'0','sellable':{'TEST':'20'},'as_of':(self.clock-timedelta(seconds=30)).isoformat(),'expires_at':(self.clock+timedelta(hours=1)).isoformat(),'version':'account-v1'}
        self.rules={'currency':'USD','venue':'TEST','lot':'10','tick':'1','fee_flat':'0','fee_per_share':'0','fee_rate':'0','sell_tax_rate':'0','slippage_bps':'0','version':'instrument-v1','quote':{'price':'101','as_of':(self.clock-timedelta(seconds=10)).isoformat(),'session_open':(self.clock-timedelta(hours=1)).isoformat(),'session_close':(self.clock+timedelta(hours=1)).isoformat(),'max_age_seconds':'60'}}
        self.draft={'ticker':'TEST','direction':'Long','entry':'101','stop':'100','target':'103','risk':'1'}

    def check(self,**overrides):return f.calculate(dict(self.draft,**overrides),self.account,self.rules,self.clock)

    def test_cash_1000_entry101_lot10_yields_zero(self):
        self.assertEqual(self.check()['quantity'],0)
        self.assertEqual(self.check()['status'],'WITHHELD')

    def test_reserves_fees_and_equity_are_distinct(self):
        self.account.update(cash='3000',reserved_cash='1000')
        self.rules.update(fee_flat='5',fee_per_share='1',lot='1')
        result=self.check()
        self.assertEqual(result['quantity'],19)
        self.assertGreaterEqual(Decimal(result['cash_after']),0)
        self.assertLessEqual(Decimal(result['maxLoss']),Decimal(result['riskBudget']))
        self.assertEqual(result['available_cash'],'2000')
        self.assertTrue(all(s['probability'] is None for s in result['scenarios']))

    def test_short_tick_freshness_and_kelly_gates(self):
        self.assertEqual(self.check(direction='Short',stop='103',target='99')['reason_codes'],['VERIFIED_BORROW_AND_MARGIN_REQUIRED'])
        self.assertEqual(self.check(entry='101.5')['reason_codes'],['PRICE_TICK_MISMATCH'])
        self.assertEqual(self.check(sizing_mode='kelly')['reason_codes'],['VALIDATED_TRADE_EDGE_REQUIRED'])
        self.rules['quote']['as_of']=(self.clock-timedelta(seconds=61)).isoformat()
        self.assertEqual(self.check()['reason_codes'],['QUOTE_EXPIRED'])

    def test_sell_limited_to_own_sellable_shares(self):
        self.account['cash']='0'
        result=self.check(side='SELL',requested_quantity='1000')
        self.assertEqual(result['quantity'],20)

    def test_sources_share_identical_sizing_and_no_claimed_client_capital(self):
        self.account['cash']='5000'
        values=[self.check(context=context,capital='999999999',cash='999999999')['quantity'] for context in ('PLANNER','VSA','DISTRIBUTION')]
        self.assertEqual(len(set(values)),1)
        self.assertEqual(self.check()['order_status'],'DRAFT_ONLY')
        self.assertIsNone(f.calculate(self.draft,None,self.rules)['quantity'])

    def test_outcome_denominators_include_unresolved_paths(self):
        values=f.outcome_rates(40,20,40)
        self.assertAlmostEqual(values['conditional_target_hit'],40/60)
        self.assertEqual(values['unconditional_target_hit'],.4)
