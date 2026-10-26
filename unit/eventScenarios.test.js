import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {queryKey, reviewedProbability, referenceForecast, seriesForecast, comparisonRows, evidenceScore, sourceUrl, studySnapshot, readStudies} from '../src/eventScenarios.js';

test('query identity distinguishes filters while normalizing surrounding spaces and global focus', () => {
  const query = {category:'Economy',factor:'GDP growth',focus:' Vietnam ',horizon:'30 days'};
  assert.equal(queryKey(query),queryKey({...query,focus:'vietnam'}));
  assert.notEqual(queryKey(query),queryKey({...query,focus:'Japan'}));
  assert.notEqual(queryKey(query),queryKey({...query,horizon:'730 days'}));
  assert.notEqual(queryKey(query),queryKey({...query,basis:'OCCURRENCE'}));
  assert.equal(queryKey({...query,focus:''}),queryKey({...query,focus:'World'}));
});

test('experimental numbers and incomplete eligibility never become displayed probabilities', () => {
  const result = {horizon:'30 days',calibrated_probability:true,dynamic_scenarios:{ranked_scenarios:[{id:'a'},{id:'b'}]},bayesian_forecast:{status:'CALIBRATED_MODEL_ELIGIBLE',
    model_version:'reviewed-v1',holdout_sample_count:200,horizon:'30 days',posterior:{a:.7,b:.3}}};
  assert.equal(reviewedProbability(result,'a'),.7);
  for (const invalid of [
    {...result,calibrated_probability:false},
    {...result,bayesian_forecast:{...result.bayesian_forecast,horizon:'1 day'}},
    {...result,bayesian_forecast:{...result.bayesian_forecast,holdout_sample_count:undefined}},
    {...result,bayesian_forecast:{...result.bayesian_forecast,holdout_sample_count:'200'}},
    {...result,bayesian_forecast:{...result.bayesian_forecast,posterior:{a:NaN,b:.3}}},
    {...result,bayesian_forecast:{...result.bayesian_forecast,posterior:{a:.8,b:.4}}},
    {...result,dynamic_scenarios:{ranked_scenarios:[{id:'a'},{id:'c'}]}},
    {...result,dynamic_scenarios:{ranked_scenarios:[{id:'a'}]}},
    {experimental_probability:{probability_estimate:.9}},
  ]) assert.equal(reviewedProbability(invalid,'a'),null);
  assert.equal(evidenceScore({evidence_score:0}),0);
  for (const value of [NaN,Infinity,101,-101,'72']) assert.equal(evidenceScore({evidence_score:value}),null);
});

const referenceFixture = () => JSON.parse(readFileSync(new URL('../tests/fixtures/event-reference-forecast.json',import.meta.url),'utf8'));
function referenceReport() {
  const scenario_forecast = referenceFixture();
  return {...scenario_forecast.context,scenario_forecast};
}

test('every reference outcome is validated together and close alternatives remain visible without a forced winner', () => {
  const report = referenceReport(), model = referenceForecast(report);
  assert.ok(model);
  const rows = comparisonRows(model);
  assert.equal(rows.length,3);
  assert.ok(rows.every(r => r.close));
  assert.ok(rows.every(r => r.probability > .30 && r.probability < .35));
  const reordered = {...model,scenarios:[...model.scenarios].reverse()};
  assert.deepEqual(Object.fromEntries(comparisonRows(reordered).map(r => [r.id,r.probability])),model.probabilities);
  assert.deepEqual(comparisonRows(model,'probability').map(r => r.probability),rows.map(r => r.probability).sort((a,b) => b-a));
});

test('one missing outcome, wrong context, bad range, expired model or dishonest holdout withholds all reference estimates', () => {
  const edits = [
    m => {delete m.probabilities[m.scenarios[1].id];},
    m => {m.scenarios.pop();},
    m => {m.context.focus='Japan';},
    m => {m.context.basis='OCCURRENCE';},
    m => {m.expires_at=m.as_of;},
    m => {m.holdout_sample_count=99;},
    m => {m.probabilities[m.scenarios[0].id]=.99;},
    m => {m.intervals[m.scenarios[0].id]=[.9,1];},
    m => {m.intervals[m.scenarios[0].id]=[NaN,1];},
    m => {m.training_resolved_through=m.holdout_origin_from;},
    m => {m.validation.brier_score=NaN;},
    m => {m.holdout_counts[m.scenarios[0].id]=1;},
  ];
  for (const edit of edits) {
    const report=referenceReport();
    edit(report.scenario_forecast);
    assert.equal(referenceForecast(report),null);
  }
});

test('legacy snapshots retain their original query without exposing experimental probability as a score', () => {
  const study = {id:'old',category:'Economy',factor:'GDP growth',focus:'Vietnam',horizon:'30 days',createdAt:'2026-10-22T00:00:00Z',
    research:{status:'EVIDENCE_AVAILABLE',dynamic_scenarios:{ranked_scenarios:[{id:'a',experimental_probability:{probability_estimate:.72}}]}}};
  const snapshot = studySnapshot(study);
  assert.equal(snapshot.focus,'Vietnam');
  assert.equal(snapshot.legacy_snapshot,true);
  assert.equal(evidenceScore(snapshot.dynamic_scenarios.ranked_scenarios[0]),null);
  assert.equal(reviewedProbability(snapshot,'a'),null);
  assert.equal(studySnapshot({}),null);
});

test('source links cannot execute scripts or carry embedded credentials', () => {
  assert.equal(sourceUrl('https://example.org/news'),'https://example.org/news');
  for (const url of ['javascript:alert(1)','data:text/html,test','https://user:password@example.org','http://example.org',null]) assert.equal(sourceUrl(url),null);
});

test('malformed archive entries are ignored without discarding valid reports', () => {
  const original = globalThis.localStorage;
  try {
    globalThis.localStorage = {getItem:() => JSON.stringify([null,{}, {id:'ok',factor:'Inflation',horizon:'30 days'}])};
    assert.equal(readStudies('archive').length,1);
    globalThis.localStorage = {getItem:() => '{broken'};
    assert.deepEqual(readStudies('archive'),[]);
  } finally {globalThis.localStorage = original;}
});

const seriesFixture = () => JSON.parse(readFileSync(new URL('../tests/fixtures/event-series-forecast.json',import.meta.url),'utf8'));
function seriesReport() {const scenario_forecast=seriesFixture();return {...scenario_forecast.context,scenario_forecast};}
test('research estimates validate a complete normalized family and retain exact ties', () => {
  const report=seriesReport(), model=seriesForecast(report);
  assert.ok(model);
  assert.equal(comparisonRows(model).length,5);
  assert.equal(model.probabilities.fall,model.probabilities.rise);
  assert.equal(referenceForecast(report),null);
  assert.ok(Math.abs(Object.values(model.probabilities).reduce((sum,p) => sum+p,0)-1)<1e-10);
  const alias=structuredClone(report);alias.focus='US';alias.scenario_forecast.context.focus='US';
  assert.ok(seriesForecast(alias));
});
test('one invalid research outcome, provenance field, horizon, count or date withholds the entire group', () => {
  const edits=[
    m => {delete m.probabilities.fall;},m => {m.scenarios.pop();},m => {m.scenarios[1].id=m.scenarios[0].id;},
    m => {m.context.focus='Vietnam';},m => {m.context.basis='OCCURRENCE';},m => {m.training_sample_count=19;},m => {m.holdout_sample_count=9;},
    m => {m.probabilities.fall=.8;},m => {m.intervals.fall=[.9,1];},m => {m.training_counts.fall=20.5;},m => {m.training_counts.fall=21;},
    m => {m.holdout_counts.fall=5;},m => {m.source.provider='UNVERIFIED';},m => {m.source.profile_id='wrong';},m => {m.source.source_urls=['javascript:alert(1)'];},
    m => {m.source.retrieved_at='2030-01-01T00:00:00Z';},m => {m.source.retrieved_at='2026-10-23';},
    m => {m.baseline.observation_at='2026-02-30';},m => {m.baseline.value=0;},m => {m.baseline_age_days=0;},m => {m.effective_duration_days=30;},
    m => {m.forecast_origin_at='2026-10-23';},m => {m.maturity_at=m.forecast_origin_at;},m => {m.holdout_period_start=m.training_period_end;},
    m => {m.expires_at=m.as_of;},m => {m.validation.brier_score=NaN;},m => {m.validation.quality='CALIBRATED';},
    m => {m.change_unit='PERCENTAGE_POINTS';},m => {m.threshold_cuts=[-.2,-.1,.1,.25];},m => {m.news_adjusted=true;},m => {m.calibrated_probability=true;},
  ];
  for (const edit of edits) {const report=seriesReport();edit(report.scenario_forecast);assert.equal(seriesForecast(report),null);}
});
test('research-only snapshots with no articles preserve the whole distribution and source dates', () => {
  const model=seriesFixture(), value={...model.context,scenario_forecast:model,status:'FORECAST_AVAILABLE',evidence_status:'NOT_REQUESTED',items:[],dynamic_scenarios:{ranked_scenarios:[]}};
  const study={id:'model',...model.context,snapshot:value};
  const restored=studySnapshot(study);
  assert.deepEqual(restored.items,[]);
  assert.deepEqual(seriesForecast(restored),model);
  assert.equal(restored.evidence_status,'NOT_REQUESTED');
});

test('experimental display rejects legacy sign bug, malformed values and unsupported horizons', async () => {
  const {experimentalEstimate}=await import('../src/eventScenarios.js');
  const row={id:'mixed_recovery',horizon_eligible:true,experimental_probability:{
    model_version:'event-probability-experimental-v2',scenario_id:'mixed_recovery',
    status:'EXPERIMENTAL_UNCALIBRATED',calibrated:false,assumed_prior:.5,evidence_cluster_count:2,
    probability_estimate:.7,prior_sensitivity_range:[.4,.9]}};
  assert.equal(experimentalEstimate(row).probability_estimate,.7);
  for (const value of [null,undefined,NaN,Infinity,-.1,1.1,'0.7']) {
    assert.equal(experimentalEstimate({...row,experimental_probability:{...row.experimental_probability,probability_estimate:value}}),null);
  }
  assert.equal(experimentalEstimate({...row,horizon_eligible:false}),null);
  assert.equal(experimentalEstimate({...row,experimental_probability:{...row.experimental_probability,model_version:'event-probability-experimental-v1'}}),null);
  assert.equal(experimentalEstimate({...row,experimental_probability:{...row.experimental_probability,prior_sensitivity_range:[.8,.9]}}),null);
});
test('news share display fails closed for malformed or concentrated distributions',async()=>{
 const {researchShareAvailable}=await import('../src/eventScenarios.js');
 const result={items:[{geographic_relation:'DIRECT_SCOPE'}],dynamic_scenarios:{
  ranked_scenarios:Array.from({length:10},(_,i)=>({id:String(i),scenario_share_percent:i<2?50:0})),
  scenario_distribution:{status:'NORMALIZED_EXPERIMENTAL_UNCALIBRATED',total_percent:100}}};
 assert.equal(researchShareAvailable(result),true);
 result.dynamic_scenarios.ranked_scenarios[0].scenario_share_percent=100;
 result.dynamic_scenarios.ranked_scenarios[1].scenario_share_percent=0;
 assert.equal(researchShareAvailable(result),false);
 result.dynamic_scenarios.ranked_scenarios[0].scenario_share_percent=NaN;
 assert.equal(researchShareAvailable(result),false);
});
