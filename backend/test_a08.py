import unittest
from datetime import datetime,timezone,timedelta
from market.technical import indicators,rvol,events,volume_state
class A08Tests(unittest.TestCase):
 def bars(self,n=22):
  start=datetime(2026,1,1,tzinfo=timezone.utc)
  return [{'open':10,'high':11,'low':9,'close':10,'volume':100,'as_of':(start+timedelta(days=i)).isoformat(),'known_at':(start+timedelta(days=i)).isoformat(),'complete':True,'session_number':i} for i in range(n)]
 def test_prior_only_rvol_and_zero_range_policy(self):
  bars=self.bars();bars[-1]['volume']=400
  self.assertEqual(rvol(bars,21)['value'],4)
  bars[-1].update(open=10,high=10,low=10,close=10)
  self.assertEqual(indicators(bars)['CLV']['value'],.5)
  self.assertEqual(volume_state(-1),'INVALID');self.assertEqual(volume_state(0),'NO_TRADES')
 def test_bands_and_sma200_coverage(self):
  output=indicators(self.bars());self.assertEqual(output['Bollinger_upper20']['value'],10)
  self.assertIsNone(output['SMA200']['value']);self.assertIsNone(output['support60']['value'])
 def test_failed_breakout_only_after_failure_bar(self):
  bars=self.bars();bars[20].update(open=10,close=12,high=13);bars[21].update(open=11,high=12,close=10)
  before=events('TEST',bars[:21]);after=events('TEST',bars)
  self.assertFalse(any(e['rule']=='FAILED_UP_BREAKOUT_OBSERVED' for e in before))
  failure=next(e for e in after if e['rule']=='FAILED_UP_BREAKOUT_OBSERVED');self.assertEqual(failure['bar_time'],bars[21]['as_of'])
