import unittest
from datetime import datetime,timedelta,timezone
from market.macro_research import hedge_ratio,lag_study
from test_macro_evidence import MacroTests
import macro_evidence as m
class ResearchTests(unittest.TestCase):
 def test_regularized_lag_compares_untouched_later_baseline(self):
  start=datetime(2025,1,1,tzinfo=timezone.utc);rows=[]
  for i in range(180):
   rows.append({'origin':(start+timedelta(days=i)).isoformat(),'known_at':(start+timedelta(days=i)).isoformat(),'target_known_at':(start+timedelta(days=i+1)).isoformat(),'market':(i%5)/10,'sector':(i%3)/10,'commodity_shock':(i%7)-3,'target':(((i-1)%7)-3)*.3,'source_ids':['fixture']})
  result=lag_study(rows,'BUSINESS_EBIT_CHANGE');self.assertEqual(result['status'],'RESEARCH_ONLY');self.assertGreater(result['out_of_sample_skill'],0);self.assertIsNone(result['prediction'])
  rows[10]['known_at']=rows[100]['origin']
  with self.assertRaises(ValueError):lag_study(rows,'BUSINESS_EBIT_CHANGE')
 def test_hedge_ratio_is_research_not_quantity(self):
  r=hedge_ratio([i*2 for i in range(60)],list(range(60)));self.assertAlmostEqual(r['ratio'],2);self.assertIsNone(r['quantity'])
  self.assertIsNone(hedge_ratio([1]*60,[0]*60)['ratio'])
 def test_lag_study_insufficient_data_no_prediction(self):self.assertIsNone(lag_study([],'STOCK_RETURN')['prediction'])
class CurrencyStressTests(MacroTests):
 def test_fx_requires_known_directed_vintage(self):
  mapping=m.exposure(self.root,self.mapping(),self.now)['exposure']
  fx={**self.data,'id':'USD_JPY','kind':'fx','unit':'USD/JPY','observations':[dict(self.data['observations'][0],value='0.01')]}
  m.ingest(self.root,fx,self.now)
  data={'exposure_id':mapping['id'],'currency':'JPY','volume_unit':'tonne','output_price_delta':'1000','input_price_delta':'1000','pass_through':'100','hedge_pnl':'-20','incremental_costs':'30','fx_series_id':'USD_JPY'}
  result=m.stress(self.root,data,self.now);self.assertEqual(result['delta_ebit'],'-250.000');self.assertEqual(result['fx_evidence']['unit'],'USD/JPY')
  self.assertEqual(result['driver_proposal']['status'],'UNVERIFIED_SCENARIO_NOT_BASELINE_UPDATE')
