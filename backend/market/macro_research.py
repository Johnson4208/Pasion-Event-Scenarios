"""A12 optional offline research primitives, never executable hedges or stock advice."""
import math
from common.time import instant

def hedge_ratio(exposure_changes,hedge_changes):
    if len(exposure_changes)!=len(hedge_changes) or len(exposure_changes)<60:return {'status':'UNAVAILABLE','ratio':None,'reason':'60_ALIGNED_REVIEWED_CHANGES_REQUIRED'}
    x=list(map(float,exposure_changes));y=list(map(float,hedge_changes))
    if not all(math.isfinite(v) for v in x+y):raise ValueError()
    xm=sum(x)/len(x);ym=sum(y)/len(y);variance=sum((v-ym)**2 for v in y)
    if variance<=0:return {'status':'UNAVAILABLE','ratio':None,'reason':'ZERO_HEDGE_VARIANCE'}
    return {'status':'RESEARCH_ONLY','ratio':sum((a-xm)*(b-ym) for a,b in zip(x,y))/variance,'quantity':None,
        'policy':'MINIMUM_VARIANCE_RATIO_NOT_CONTRACT_COUNT_OR_EXECUTION'}

def _fit(xs,ys,penalty=1.0):
    n=len(xs[0]);matrix=[[sum(x[i]*x[j] for x in xs)+(penalty if i==j and i else 0) for j in range(n)]+[sum(x[i]*y for x,y in zip(xs,ys))] for i in range(n)]
    for i in range(n):
        pivot=max(range(i,n),key=lambda k:abs(matrix[k][i]));matrix[i],matrix[pivot]=matrix[pivot],matrix[i]
        if abs(matrix[i][i])<1e-12:raise ValueError('Singular research design')
        divisor=matrix[i][i];matrix[i]=[v/divisor for v in matrix[i]]
        for j in range(n):
            if j!=i:
                multiple=matrix[j][i];matrix[j]=[a-multiple*b for a,b in zip(matrix[j],matrix[i])]
    return [r[-1] for r in matrix]

def lag_study(rows,target_kind):
    if target_kind not in ('BUSINESS_EBIT_CHANGE','STOCK_RETURN'):raise ValueError()
    if len(rows)<125:return {'status':'UNAVAILABLE','reason':'INSUFFICIENT_OUT_OF_SAMPLE_HISTORY','prediction':None}
    for i,r in enumerate(rows):
        if instant(r['known_at'])>instant(r['origin']) or instant(r['target_known_at'])<=instant(r['origin']) or not r.get('source_ids'):raise ValueError('Invalid point-in-time research row')
        if i and instant(r['origin'])<=instant(rows[i-1]['origin']):raise ValueError()
        if not all(math.isfinite(float(r[k])) for k in ('market','sector','commodity_shock','target')):raise ValueError()
    samples=[([1.,float(rows[i]['market']),float(rows[i]['sector']),float(rows[i-1]['commodity_shock'])],float(rows[i]['target']),i) for i in range(1,len(rows))]
    split=int(len(samples)*.7);cutoff=rows[samples[split][2]]['origin']
    train=[s for s in samples[:split] if instant(rows[s[2]]['target_known_at'])<instant(cutoff)];test=samples[split:]
    if len(train)<80 or len(test)<30:return {'status':'UNAVAILABLE','reason':'INSUFFICIENT_PURGED_TRAIN_TEST','prediction':None}
    mean=[sum(x[j] for x,y,i in train)/len(train) for j in range(1,4)]
    scale=[max(1e-8,(sum((x[j+1]-mean[j])**2 for x,y,i in train)/len(train))**.5) for j in range(3)]
    normalize=lambda x:[1.]+[(x[j+1]-mean[j])/scale[j] for j in range(3)]
    xs=[normalize(x) for x,y,i in train];ys=[y for x,y,i in train]
    model=_fit(xs,ys);baseline=_fit([x[:3] for x in xs],ys)
    mse=sum((sum(a*b for a,b in zip(model,normalize(x)))-y)**2 for x,y,i in test)/len(test)
    baseline_mse=sum((sum(a*b for a,b in zip(baseline,normalize(x)[:3]))-y)**2 for x,y,i in test)/len(test)
    return {'status':'RESEARCH_ONLY','target_kind':target_kind,'model':'RIDGE_MARKET_SECTOR_ONE_LAG_COMMODITY','penalty':1.,'test_mse':mse,'baseline_mse':baseline_mse,
        'out_of_sample_skill':1-mse/baseline_mse if baseline_mse>0 else None,'training_count':len(train),'test_count':len(test),
        'prediction':None,'policy':'SINGLE_HOLDOUT_RESEARCH_NOT_DEPLOYMENT_VALIDATION_NO_CAUSAL_CLAIM'}
