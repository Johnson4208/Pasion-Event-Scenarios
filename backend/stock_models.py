"""F05 frozen logistic models; calibration and future-cohort validation stay server-side."""
import hashlib
import json
import math
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import finance_core
from finance.contracts import envelope

HORIZONS={5:'1 week',21:'1 month',63:'3 months',252:'12 months'}
POLICY='f05-logistic-v1:returns1,returns5,sma20gap,vol20;fixed-iterations;Platt-OOS'
MIN_TRAIN=80
MIN_CALIBRATION=40
MIN_TEST=80


def now():
    return datetime.now(timezone.utc)


def database(root):
    db=sqlite3.connect(root/'stock_models.sqlite3')
    db.row_factory=sqlite3.Row
    db.executescript('CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY,ticker TEXT,horizon INTEGER,frozen_at TEXT,expires_at TEXT,payload TEXT); CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY,model_id TEXT,known_at TEXT,payload TEXT);')
    return db


def number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def bars_valid(bars,origin):
    if not isinstance(bars,list) or not 21<=len(bars)<=10000:
        raise ValueError('Point-in-time OHLCV history required.')
    previous=None
    for bar in bars:
        stamp=finance_core.instant(bar['as_of']); known=finance_core.instant(bar['known_at'])
        if stamp>origin or known>origin or known<stamp or bar['complete'] is not True:
            raise ValueError('Only known completed sessions are permitted.')
        if previous and (stamp<=previous[0] or bar['session_number']!=previous[1]+1):
            raise ValueError('Explicit contiguous exchange sessions are required.')
        if not isinstance(bar['session_number'],int) or isinstance(bar['session_number'],bool):
            raise ValueError('Invalid session identity.')
        if not all(number(bar[k]) and bar[k]>0 for k in ('open','high','low','close')) or not number(bar['volume']) or bar['volume']<0:
            raise ValueError('Invalid OHLCV.')
        if not bar['low']<=min(bar['open'],bar['close'])<=max(bar['open'],bar['close'])<=bar['high']:
            raise ValueError('Invalid bar ranges.')
        previous=(stamp,bar['session_number'])
    return bars


def features(bars,index):
    if index<20:
        raise ValueError('Insufficient feature history.')
    origin=finance_core.instant(bars[index]['known_at'])
    history=bars[index-20:index+1]
    if any(finance_core.instant(b['known_at'])>origin for b in history):
        raise ValueError('Revised information was not known at the prediction origin.')
    close=bars[index]['close']
    returns=[history[i]['close']/history[i-1]['close']-1 for i in range(1,len(history))]
    mean=sum(returns)/len(returns)
    vector=[close/bars[index-1]['close']-1,close/bars[index-5]['close']-1,
            close/(sum(b['close'] for b in history[-20:])/20)-1,
            math.sqrt(sum((r-mean)**2 for r in returns)/len(returns))]
    if not all(math.isfinite(v) for v in vector):
        raise ValueError('Invalid feature values.')
    return vector


def sigmoid(value):
    return 1/(1+math.exp(-max(-40,min(40,value))))


def fit(xs,ys):
    means=[sum(x[j] for x in xs)/len(xs) for j in range(len(xs[0]))]
    scales=[max(1e-8,math.sqrt(sum((x[j]-means[j])**2 for x in xs)/len(xs))) for j in range(len(means))]
    normalized=[[1]+[(x[j]-means[j])/scales[j] for j in range(len(means))] for x in xs]
    weights=[0.0]*len(normalized[0])
    for _ in range(300):
        errors=[sigmoid(sum(w*v for w,v in zip(weights,x)))-y for x,y in zip(normalized,ys)]
        weights=[w-.05*(sum(error*x[j] for error,x in zip(errors,normalized))/len(xs)+(.01*w if j else 0)) for j,w in enumerate(weights)]
    return {'weights':weights,'means':means,'scales':scales}


def predict(model,x):
    vector=[1]+[(x[j]-model['means'][j])/model['scales'][j] for j in range(len(x))]
    return sigmoid(sum(w*v for w,v in zip(model['weights'],vector)))


def calibrated(package,x):
    raw=predict(package['model'],x)
    return predict(package['calibrator'],[math.log(max(1e-8,raw)/max(1e-8,1-raw))])

def artifact_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def reliability(ps,ys,baseline_probability):
    if not ps or len(ps)!=len(ys):return {'brier':None,'baseline_brier':None,'skill':None,'status':'UNAVAILABLE'}
    score=sum((p-y)**2 for p,y in zip(ps,ys))/len(ps)
    baseline=sum((baseline_probability-y)**2 for y in ys)/len(ys)
    skill=1-score/baseline if baseline>0 else None
    return {'brier':score,'baseline_brier':baseline,'skill':skill,'status':'READY' if skill is not None and skill>0 and len(set(ys))==2 else 'UNCERTAIN'}


def freeze(root,ticker,horizon,bars,source,clock=None):
    clock=clock or now()
    if horizon not in HORIZONS or not isinstance(source,str) or not source.strip():
        raise ValueError('Registered horizon and provider source required.')
    bars_valid(bars,clock)
    candidates=[i for i in range(20,len(bars)-horizon) if finance_core.instant(bars[i]['known_at'])<finance_core.instant(bars[i+horizon]['as_of'])]
    split=int(len(candidates)*.65)
    calibration=candidates[split:]
    if len(calibration)<MIN_CALIBRATION:
        raise ValueError('Insufficient out-of-sample calibration.')
    cutoff=calibration[0]
    training=[i for i in candidates[:split] if i+horizon<cutoff and finance_core.instant(bars[i+horizon]['known_at'])<=finance_core.instant(bars[cutoff]['known_at'])]
    if len(training)<MIN_TRAIN:
        raise ValueError('Insufficient purged training sample.')
    label=lambda i:int(bars[i+horizon]['close']/bars[i]['close']-1>0)
    if len({label(i) for i in training})<2 or len({label(i) for i in calibration})<2:
        raise ValueError('Both return classes required in training and calibration.')
    model=fit([features(bars,i) for i in training],[label(i) for i in training])
    raw=[predict(model,features(bars,i)) for i in calibration]
    calibrator=fit([[math.log(max(1e-8,p)/max(1e-8,1-p))] for p in raw],[label(i) for i in calibration])
    # Expanding walk-forward diagnostics, never used to tune or replace the frozen champion.
    folds=[]
    for cut in (len(candidates)//2,len(candidates)*3//4):
        test=candidates[cut:cut+20]
        train=[i for i in candidates[:cut] if i+horizon<test[0] and finance_core.instant(bars[i+horizon]['known_at'])<=finance_core.instant(bars[test[0]]['known_at'])] if test else []
        if len(train)>=MIN_TRAIN:
            fold_model=fit([features(bars,i) for i in train],[label(i) for i in train])
            score=sum((predict(fold_model,features(bars,i))-label(i))**2 for i in test)/len(test)
            folds.append({'train_end':bars[train[-1]+horizon]['as_of'],'test_start':bars[test[0]]['as_of'],'sample_count':len(test),'brier':score,'purge_sessions':horizon})
    package={'version':1,'model_id':secrets.token_hex(16),'ticker':ticker,'horizon_sessions':horizon,'feature_policy':POLICY,
             'source':source[:120],'frozen_at':clock.isoformat(),'expires_at':(clock+timedelta(days=730)).isoformat(),
             'model':model,'calibrator':calibrator,'calibration_version':'Platt-v1','baseline':sum(label(i) for i in training)/len(training),
             'training_count':len(training),'calibration_count':len(calibration),'training_end':bars[training[-1]+horizon]['as_of'],
             'calibration_start':bars[calibration[0]]['as_of'],'calibration_end':bars[calibration[-1]+horizon]['known_at'],
             'snapshot_hash':hashlib.sha256(json.dumps(bars,sort_keys=True).encode()).hexdigest(),'training_bars':bars,'walk_forward':folds}
    package.update(model_artifact_hash=artifact_hash(model),calibrator_artifact_hash=artifact_hash(calibrator),
        feature_names=['return_1','return_5','sma20_gap','volatility_20'],
        feature_history_sessions=21,feature_policy_version='f05-features-v1',
        calibration_policy='PAST_HELD_OUT_OOS_PLATT_NO_FUTURE_REFIT',validation_policy_version='a09-v1')
    db=database(root)
    try:
        with db:
            db.execute('INSERT INTO models VALUES (?,?,?,?,?,?)',(package['model_id'],ticker,horizon,package['frozen_at'],package['expires_at'],json.dumps(package)))
    finally:
        db.close()
    return {k:package[k] for k in ('model_id','horizon_sessions','frozen_at','expires_at','snapshot_hash','walk_forward')} | {'status':'UNCERTAIN','reason':'FUTURE_COHORT_VALIDATION_REQUIRED'}


def evaluate(root,model_id,bars,clock=None):
    clock=clock or now(); bars_valid(bars,clock)
    db=database(root)
    try:
        row=db.execute('SELECT payload FROM models WHERE id=?',(model_id,)).fetchone()
        if not row:
            raise ValueError('Frozen model not found.')
        package=json.loads(row[0]); original=package['training_bars']; h=package['horizon_sessions']
        if bars[:len(original)]!=original:
            raise ValueError('Training/calibration snapshot changed; revised history requires a new candidate.')
        frozen=finance_core.instant(package['frozen_at'])
        indices=[i for i in range(len(original),len(bars)-h) if finance_core.instant(bars[i]['as_of'])>frozen and finance_core.instant(bars[i]['known_at'])<finance_core.instant(bars[i+h]['as_of'])]
        ps=[calibrated(package,features(bars,i)) for i in indices]
        ys=[int(bars[i+h]['close']/bars[i]['close']-1>0) for i in indices]
        score=sum((p-y)**2 for p,y in zip(ps,ys))/len(ps) if ps else None
        baseline=sum((package['baseline']-y)**2 for y in ys)/len(ys) if ys else None
        skill=1-score/baseline if baseline and score is not None else None
        curve=[]
        for bucket in range(10):
            pairs=[(p,y) for p,y in zip(ps,ys) if min(9,int(p*10))==bucket]
            if pairs:
                curve.append({'bin':bucket,'count':len(pairs),'mean_probability':sum(p for p,y in pairs)/len(pairs),'observed_rate':sum(y for p,y in pairs)/len(pairs)})
        ece=sum(c['count']*abs(c['mean_probability']-c['observed_rate']) for c in curve)/len(ps) if ps else None
        midpoint=len(ps)//2
        stability=[reliability(ps[:midpoint],ys[:midpoint],package['baseline']),reliability(ps[midpoint:],ys[midpoint:],package['baseline'])]
        stable=all(window['status']=='READY' for window in stability)
        ready=len(ps)>=MIN_TEST and skill is not None and skill>0 and ece is not None and ece<=.1 and len(set(ys))==2 and stable
        origin=finance_core.instant(bars[-1]['known_at'])
        probability=calibrated(package,features(bars,len(bars)-1)) if ready else None
        report={'version':1,'model_id':model_id,'horizon_sessions':h,'status':'READY' if ready else 'UNCERTAIN',
                'reason':'VALIDATION_PASSED' if ready else 'INSUFFICIENT_SAMPLE_OR_RELIABILITY','p_up':probability,'p_down':1-probability if probability is not None else None,
                'brier':score,'baseline_brier':baseline,'brier_skill':skill,'sample_count':len(ps),'calibration_curve':curve,'calibration_error':ece,
                'validation_start':bars[indices[0]]['as_of'] if indices else None,'validation_end':bars[indices[-1]+h]['known_at'] if indices else None,
                'last_valid_origin':origin.isoformat(),'bar_as_of':bars[-1]['as_of'],'prediction_expires_at':(finance_core.instant(bars[-1]['as_of'])+timedelta(hours=24)).isoformat(),
                'model_expires_at':package['expires_at'],'feature_policy':POLICY,'source':package['source'],'snapshot_hash':package['snapshot_hash'],
                'frozen_at':package['frozen_at'],'calibration_version':package['calibration_version'],
                'features':dict(zip(('return_1','return_5','sma20_gap','volatility_20'),features(bars,len(bars)-1))),
                'volume_state':'NO_TRADES' if bars[-1]['volume']==0 else 'OBSERVED',
                'label_definition':'close[t+h]/close[t]-1 > 0; down means nonpositive return',
                'overlap_policy':'Horizon purge at training/calibration boundaries; future test labels may overlap and are not independent trials.'}
        report.update(evaluation_id=secrets.token_hex(16),validation_policy_version='a09-v1',stability_windows=stability,
            stability_status='READY' if stable else 'UNCERTAIN',feature_policy_version=package.get('feature_policy_version','f05-features-v1'),
            model_artifact_hash=package.get('model_artifact_hash',artifact_hash(package['model'])),
            calibrator_artifact_hash=package.get('calibrator_artifact_hash',artifact_hash(package['calibrator'])),
            prediction_feature_hash=artifact_hash(features(bars,len(bars)-1)),
            prediction_snapshot_hash=artifact_hash(bars),calibration_count=package['calibration_count'],training_count=package['training_count'],
            walk_forward=package['walk_forward'],coverage={'future_origins':len(indices),'minimum_required':MIN_TEST,'feature_history_sessions':21},
            independent_test_sample_count=len(indices[::h]),
            independence_caveat='Overlapping future labels are dependent; sample_count is not independent trial count.',
            operating_forecast_policy='MARKET_RETURN_CLASSIFIER_NOT_A_COMPANY_CASHFLOW_FORECAST')
        with db:
            db.execute('INSERT INTO evaluations VALUES (?,?,?,?)',(report['evaluation_id'],model_id,clock.isoformat(),json.dumps(report)))
        return report
    finally:
        db.close()


def analysis(root,ticker,clock=None):
    clock=clock or now(); responses=[]
    db=database(root)
    try:
        for h,label in HORIZONS.items():
            row=db.execute('SELECT m.payload AS model,e.known_at,e.payload AS evaluation FROM models m LEFT JOIN evaluations e ON e.model_id=m.id WHERE m.ticker=? AND m.horizon=? ORDER BY m.rowid DESC,e.rowid DESC LIMIT 1',(ticker,h)).fetchone()
            result={'horizon_sessions':h,'label':label,'status':'UNAVAILABLE','p_up':None,'p_down':None,'direction':'UNAVAILABLE','reason':'NO_FROZEN_VALIDATED_MODEL','features':{}}
            if row and row['evaluation']:
                candidate=json.loads(row['evaluation'])
                if finance_core.instant(row['known_at'])>clock or finance_core.instant(candidate['last_valid_origin'])>clock:
                    result.update(status='UNAVAILABLE',reason='FUTURE_INFORMATION_WITHHELD')
                else:
                    result.update(candidate)
                    if candidate.get('validation_policy_version')!='a09-v1':
                        result.update(status='UNCERTAIN',reason='REVALIDATION_UNDER_CURRENT_POLICY_REQUIRED')
                    if finance_core.instant(candidate['model_expires_at'])<=clock or finance_core.instant(candidate['prediction_expires_at'])<=clock:
                        result.update(status='UNAVAILABLE',reason='MODEL_OR_PREDICTION_EXPIRED',features={})
                if result['status']!='READY':
                    result.update(p_up=None,p_down=None,direction='UNCERTAIN' if result['status']=='UNCERTAIN' else 'UNAVAILABLE')
                else:
                    result['direction']='UP' if result['p_up']>=.58 else 'DOWN' if result['p_up']<=.42 else 'UNCERTAIN'
            result['result_contract']=envelope({'definition_id':'market_return_p_up','value':result['p_up'],'unit':'probability',
                'status':result['status'],'origin':'FORECAST','known_at':row['known_at'] if row and row['known_at'] else None,
                'as_of':result.get('last_valid_origin'),'source_ids':[result['model_id']] if result.get('model_id') else [],
                'model_version':result.get('model_id'),'calculation_version':POLICY,'reason_codes':[result['reason']] if result.get('reason') else [],
                'eligibility':{'horizon_sessions':h,'probability_type':'CALIBRATED_MARKET_RETURN_ONLY'}},object_type='ModelOutput')
            responses.append(result)
    finally:
        db.close()
    return {'version':1,'ticker':ticker,'evaluated_at':clock.isoformat(),'horizons':responses,'probability_type':'calibrated_market_return_probability','confidence':None}
