import tempfile,unittest,sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from distribution.recommendations import decide

POLICY=dict(version='lab-v1',window_seconds=3600,max_per_symbol=3,max_per_sector=6,customer_cooldown_seconds=600,utility_tolerance=2)
def candidates():
 return [dict(symbol=s,sector=sector,utility=u,suitable=True,data_status='READY',horizon='30 sessions',utility_definition='net utility',utility_version='v1') for s,sector,u in [('AAA','tech',90),('BBB','tech',89),('CCC','industry',88),('BAD','other',40)]]
class DistributionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'lab.sqlite3'
 def call(self,i,now=1000,customer=None,c=None):return decide(self.path,str(i),customer or 'customer-'+str(i),c or candidates(),POLICY,now)
 def test_concurrent_caps_and_no_inferior_substitute(self):
  self.call('initialize',c=[dict(candidates()[0],suitable=False)])
  with ThreadPoolExecutor(max_workers=8) as pool:r=list(pool.map(self.call,range(50)))
  self.assertEqual(sum(x['status']=='SELECTED' for x in r),9)
  for symbol in ('AAA','BBB','CCC'):self.assertEqual(sum(x['symbol']==symbol for x in r),3)
  self.assertFalse(any(x['symbol']=='BAD' for x in r))
 def test_retry_cooldown_and_window_expiry(self):
  first=self.call(1,customer='same');self.assertEqual(first['symbol'],'AAA')
  self.assertTrue(self.call(1,now=1001,customer='same')['replayed'])
  self.assertEqual(self.call(2,now=1001,customer='same')['symbol'],'BBB')
  with self.assertRaises(ValueError):self.call(1,customer='different')
  self.assertEqual(self.call(3,now=5000,customer='same')['symbol'],'AAA')
 def test_rejects_bad_inputs_and_incomparable_utilities(self):
  for change in ({'utility':float('nan')},{'horizon':'different'}):
   c=candidates();c[0].update(change)
   with self.assertRaises(ValueError):self.call(1,c=c)
  c=[dict(x,suitable=False) for x in candidates()]
  self.assertIsNone(self.call(2,c=c)['symbol'])
 def test_sector_cap_applies_across_symbols(self):
  p=dict(POLICY,max_per_symbol=100,max_per_sector=2)
  r=[decide(self.path,str(i),'user'+str(i),candidates(),p,1000) for i in range(10)]
  self.assertEqual(sum(x['symbol'] in ('AAA','BBB') for x in r),2)
  self.assertEqual(sum(x['symbol']=='CCC' for x in r),2)
