"""Offline synthetic customers. Run: python testing/simulate_distribution.py."""
import argparse,collections,json,sys,tempfile,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from distribution.recommendations import decide

def main():
 p=argparse.ArgumentParser();p.add_argument('--customers',type=int,default=1000);p.add_argument('--workers',type=int,default=16);p.add_argument('--output',default='artifacts/distribution-lab.json');a=p.parse_args()
 if not 1<=a.customers<=100000 or not 1<=a.workers<=64:p.error('customers 1..100000, workers 1..64')
 policy=dict(version='synthetic-lab-v1',window_seconds=3600,max_per_symbol=100,max_per_sector=300,customer_cooldown_seconds=600,utility_tolerance=2)
 candidates=[dict(symbol=s,sector=sector,utility=u,suitable=True,data_status='READY',horizon='30 sessions',utility_definition='synthetic utility',utility_version='v1') for s,sector,u in [('SIM_A','technology',90),('SIM_B','technology',89.5),('SIM_C','industry',89),('SIM_D','consumer',88.5),('SIM_E','health',88),('SIM_LOW','other',30)]]
 with tempfile.TemporaryDirectory(prefix='pasion-distribution-lab-') as tmp:
  path=Path(tmp)/'synthetic.sqlite3'
  decide(path,'init','synthetic-init',[],policy,1000)
  start=time.perf_counter()
  with ThreadPoolExecutor(max_workers=a.workers) as pool:
   results=list(pool.map(lambda i:decide(path,'request-'+str(i),'synthetic-'+str(i),candidates,policy,1000),range(a.customers)))
  counts=dict(collections.Counter(r['symbol'] for r in results if r['symbol']))
  assert max(counts.values(),default=0)<=policy['max_per_symbol']
  assert 'SIM_LOW' not in counts
  report=dict(mode='SYNTHETIC_OFFLINE_ONLY',customers=a.customers,workers=a.workers,policy=policy,
   baseline_without_limiter={'SIM_A':a.customers},with_limiter=counts,
   withheld=sum(r['symbol'] is None for r in results),elapsed_seconds=round(time.perf_counter()-start,3),
   limitations=['Synthetic utility and suitability; no financial performance validation.','Exposure counts are issued recommendations, not trades, capital or liquidity.','No production recommendation routes call this module yet.'])
 out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
