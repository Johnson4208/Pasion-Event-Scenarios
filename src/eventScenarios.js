// The live service supplies evidence, not calibrated probabilities. Keep this
// distinction when loading historical snapshots or incomplete API responses.
export const HORIZONS = {
  short: [['1 day','1 day'],['3 days','3 days'],['7 days','1 week'],['30 days','1 month'],['90 days','3 months']],
  long: [['180 days','6 months'],['365 days','1 year'],['730 days','2 years']],
};

export function queryKey(query) {
  return JSON.stringify([query.category, query.factor, (query.focus?.trim() || 'World').toLowerCase(), query.horizon, query.basis || 'END_STATE']);
}

export function reviewedProbability(result, scenarioId) {
  const model = result?.bayesian_forecast;
  const ids = result?.dynamic_scenarios?.ranked_scenarios?.filter(s => s.horizon_eligible !== false).map(s => s.id);
  if (result?.calibrated_probability !== true || model?.status !== 'CALIBRATED_MODEL_ELIGIBLE' ||
      typeof model.model_version !== 'string' || !model.model_version.trim() ||
      !Number.isInteger(model.holdout_sample_count) || model.holdout_sample_count < 100 ||
      model.horizon !== result.horizon || !Array.isArray(ids) || ids.length < 2 || new Set(ids).size !== ids.length ||
      Object.keys(model.posterior || {}).length !== ids.length || ids.some(id => !Object.hasOwn(model.posterior || {},id))) return null;
  const probabilities = Object.values(model.posterior || {});
  if (probabilities.length < 2 || probabilities.some(p => typeof p !== 'number' || !Number.isFinite(p) || p < 0 || p > 1) ||
      Math.abs(probabilities.reduce((sum,p) => sum+p,0)-1) > 1e-7) return null;
  const value = model.posterior[scenarioId];
  return typeof value === 'number' ? value : null;
}

// One invalid or missing outcome withholds the whole comparison. Never
// normalize a partly covered set or match changing scenarios by row position.
export function referenceForecast(result) {
  const model = result?.scenario_forecast;
  if (model?.schema_version !== 1 || model.status !== 'REFERENCE_ESTIMATE_AVAILABLE' ||
      model.method !== 'HISTORICAL_REFERENCE_CLASS_V1' || queryKey(model.context || {}) !== queryKey(result) ||
      !['END_STATE','OCCURRENCE'].includes(model.context.basis) || model.validation?.status !== 'PASSED_HOLDOUT_CHECK' ||
      !Number.isInteger(model.training_sample_count) || model.training_sample_count < 100 || model.training_sample_count > 100000 ||
      !Number.isInteger(model.holdout_sample_count) || model.holdout_sample_count < 100 || model.holdout_sample_count > 100000 ||
      ['model_version','family_id','definition_version','question','sampling_policy','dataset_sha256'].some(k => typeof model[k] !== 'string' || !model[k].trim())) return null;
  if (['brier_score','log_loss','maximum_rate_error'].some(k => typeof model.validation[k] !== 'number' || !Number.isFinite(model.validation[k]) || model.validation[k] < 0)) return null;
  const asOf = Date.parse(model.as_of), reviewed = Date.parse(model.reviewed_at), expires = Date.parse(model.expires_at);
  const trainingEnd = Date.parse(model.training_resolved_through), holdoutStart = Date.parse(model.holdout_origin_from), holdoutEnd = Date.parse(model.holdout_resolved_through);
  if (![asOf,reviewed,expires,trainingEnd,holdoutStart,holdoutEnd].every(Number.isFinite) ||
      !(trainingEnd < holdoutStart && holdoutStart < holdoutEnd && holdoutEnd <= reviewed && reviewed <= asOf && asOf < expires)) return null;
  if (!Array.isArray(model.scenarios) || model.scenarios.length < 2 || model.scenarios.length > 100 ||
      model.scenarios.some(s => !s || ['id','title','resolution_rule'].some(k => typeof s[k] !== 'string' || !s[k].trim()))) return null;
  const ids = model.scenarios.map(s => s.id);
  if (new Set(ids).size !== ids.length) return null;
  for (const map of [model.probabilities,model.intervals,model.training_counts,model.holdout_counts]) {
    if (!map || Object.keys(map).length !== ids.length || ids.some(id => !Object.hasOwn(map,id))) return null;
  }
  const endState = model.context.basis === 'END_STATE';
  if (model.mutually_exclusive !== endState || model.exhaustive !== endState || model.interval_level !== .95 || model.news_adjusted !== false) return null;
  const denominator = model.training_sample_count+(endState ? ids.length/2 : 1);
  for (const id of ids) {
    const p = model.probabilities[id], interval = model.intervals[id];
    if (typeof p !== 'number' || !Number.isFinite(p) || p < 0 || p > 1 ||
        !Array.isArray(interval) || interval.length !== 2 || interval.some(v => typeof v !== 'number' || !Number.isFinite(v)) ||
        !(0 <= interval[0] && interval[0] <= p && p <= interval[1] && interval[1] <= 1)) return null;
    for (const [counts,n] of [[model.training_counts,model.training_sample_count],[model.holdout_counts,model.holdout_sample_count]]) {
      if (!Number.isInteger(counts[id]) || counts[id] < 5 || counts[id] > n || (!endState && n-counts[id] < 5)) return null;
    }
    if (Math.abs(p-(model.training_counts[id]+.5)/denominator) > 1e-8) return null;
    const observed = model.holdout_counts[id]/model.holdout_sample_count;
    const tolerance = Math.min(.10,1.96*Math.sqrt(p*(1-p)*(1/model.training_sample_count+1/model.holdout_sample_count)));
    if (Math.abs(p-observed) > tolerance+1e-12) return null;
  }
  if (endState && (Math.abs(ids.reduce((sum,id) => sum+model.probabilities[id],0)-1) > 1e-7 ||
      ids.reduce((sum,id) => sum+model.training_counts[id],0) !== model.training_sample_count ||
      ids.reduce((sum,id) => sum+model.holdout_counts[id],0) !== model.holdout_sample_count)) return null;
  return model;
}

// Research estimates have a different, explicit contract from reviewed
// catalogs. Validate the complete measurable end-state family before display.
export function seriesForecast(result) {
  const model = result?.scenario_forecast;
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const text = value => typeof value === 'string' && !!value.trim() && value.length <= 4000;
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const instant = value => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : NaN;
  const period = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value ? Date.parse(value) : NaN;
  if (!object(model) || model.schema_version !== 2 || model.method !== 'RETROSPECTIVE_SERIES_REFERENCE_V1' ||
      model.status !== 'RESEARCH_ESTIMATE_AVAILABLE' || !object(model.context) || model.context.basis !== 'END_STATE' ||
      queryKey(model.context) !== queryKey(result) || model.news_adjusted !== false || model.calibrated_probability !== false ||
      model.mutually_exclusive !== true || model.exhaustive !== true || model.interval_level !== .95 ||
      ['family_id','definition_version','model_version','question','sampling_policy','change_unit'].some(key => !text(model[key])) ||
      typeof model.dataset_sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(model.dataset_sha256)) return null;
  if (!Number.isInteger(model.training_sample_count) || model.training_sample_count < 20 || model.training_sample_count > 100000 ||
      !Number.isInteger(model.holdout_sample_count) || model.holdout_sample_count < 10 || model.holdout_sample_count > 100000 ||
      model.validation?.status !== 'RETROSPECTIVE_HOLDOUT_ONLY' || !['LIMITED','RETROSPECTIVE_ONLY'].includes(model.validation.quality) ||
      ['brier_score','log_loss','maximum_rate_error'].some(key => !finite(model.validation[key]) || model.validation[key] < 0) ||
      model.validation.maximum_rate_error > 1) return null;
  const asOf=instant(model.as_of), origin=instant(model.forecast_origin_at), maturity=instant(model.maturity_at), expiry=instant(model.expires_at);
  const days=Number(model.context.horizon?.split(' ')[0]);
  const trainingEnd=period(model.training_period_end), holdoutStart=period(model.holdout_period_start), holdoutEnd=period(model.holdout_period_end);
  if (![asOf,origin,maturity,expiry,trainingEnd,holdoutStart,holdoutEnd].every(Number.isFinite) ||
      !Object.values(HORIZONS).flat().some(([value]) => value === model.context.horizon) ||
      !(trainingEnd < holdoutStart && holdoutStart <= holdoutEnd && holdoutEnd <= origin && origin <= asOf && asOf < expiry) ||
      expiry-asOf > 86400000 || maturity-origin !== days*86400000) return null;
  if (!object(model.baseline) || !finite(model.baseline.value) || !text(model.baseline.unit) ||
      !Number.isFinite(period(model.baseline.observation_at)) || period(model.baseline.observation_at) > origin ||
      !object(model.source) || model.source.provider !== 'FRED' || !text(model.source.metric) ||
      !text(model.source.snapshot_id) || !Number.isFinite(instant(model.source.retrieved_at)) || instant(model.source.retrieved_at) > asOf ||
      !Array.isArray(model.source.source_urls) || !model.source.source_urls.length || model.source.source_urls.some(url => !sourceUrl(url))) return null;
  const sourceContexts = {VIXCLS:{category:'Markets',factor:'Equity volatility',profile:'us-volatility',cuts:[-.25,-.1,.1,.25],unit:'RELATIVE_CHANGE'},MORTGAGE30US:{category:'Real Estate',factor:'Mortgage rates',profile:'us-mortgages',cuts:[-.25,.25],unit:'PERCENTAGE_POINTS'}};
  const expected=sourceContexts[model.source.metric];
  if (!expected || model.context.category !== expected.category || model.context.factor !== expected.factor ||
      !['united states','us','usa','u.s.','u.s','america'].includes(model.context.focus?.toLowerCase()) ||
      model.source.profile_id !== expected.profile || model.change_unit !== expected.unit ||
      model.source.metric === 'VIXCLS' && model.baseline.value <= 0 || model.source.metric === 'MORTGAGE30US' && (model.baseline.value < 0 || days < 7)) return null;
  const age=Math.floor(origin/86400000)-period(model.baseline.observation_at)/86400000;
  if (!Number.isInteger(model.baseline_age_days) || model.baseline_age_days !== age ||
      !Number.isInteger(model.effective_duration_days) || model.effective_duration_days !== days+age ||
      age < 0 || age > (model.source.metric === 'VIXCLS' ? 7 : 21)) return null;
  if (!Array.isArray(model.scenarios) || model.scenarios.length < 2 || model.scenarios.length > 100 ||
      model.scenarios.some(row => !object(row) || ['id','title','resolution_rule'].some(key => !text(row[key])))) return null;
  const ids=model.scenarios.map(row => row.id), cuts=model.threshold_cuts;
  if (new Set(ids).size !== ids.length || !Array.isArray(cuts) || cuts.length !== ids.length-1 ||
      cuts.some((value,index) => !finite(value) || index > 0 && value <= cuts[index-1]) ||
      JSON.stringify(cuts) !== JSON.stringify(expected.cuts)) return null;
  if (model.scenarios.some((row,index) => row.lower_bound !== (index ? cuts[index-1] : null) ||
      row.upper_bound !== (index === ids.length-1 ? null : cuts[index]))) return null;
  for (const map of [model.probabilities,model.intervals,model.training_counts,model.holdout_counts]) {
    if (!object(map) || Object.keys(map).length !== ids.length || ids.some(id => !Object.hasOwn(map,id))) return null;
  }
  const denominator=model.training_sample_count+ids.length/2;
  for (const id of ids) {
    const probability=model.probabilities[id], interval=model.intervals[id];
    if (!finite(probability) || probability < 0 || probability > 1 || !Array.isArray(interval) || interval.length !== 2 ||
        interval.some(value => !finite(value)) || !(0 <= interval[0] && interval[0] <= probability && probability <= interval[1] && interval[1] <= 1)) return null;
    for (const [counts,n] of [[model.training_counts,model.training_sample_count],[model.holdout_counts,model.holdout_sample_count]]) {
      if (!Number.isInteger(counts[id]) || counts[id] < 0 || counts[id] > n) return null;
    }
    if (Math.abs(probability-(model.training_counts[id]+.5)/denominator) > 1e-8) return null;
  }
  if (Math.abs(ids.reduce((sum,id) => sum+model.probabilities[id],0)-1) > 1e-7 ||
      ids.reduce((sum,id) => sum+model.training_counts[id],0) !== model.training_sample_count ||
      ids.reduce((sum,id) => sum+model.holdout_counts[id],0) !== model.holdout_sample_count) return null;
  return model;
}

export function comparisonRows(model, sort='definition') {
  if (!model) return [];
  const highest = Math.max(...Object.values(model.probabilities));
  const rows = model.scenarios.map(s => ({...s, probability:model.probabilities[s.id],
    interval:model.intervals[s.id], gap:highest-model.probabilities[s.id],
    close:highest-model.probabilities[s.id] <= .03+1e-12}));
  if (sort === 'probability') rows.sort((a,b) => b.probability-a.probability || a.id.localeCompare(b.id));
  return rows;
}

export function readStudies(key) {
  try {
    const data = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(data) ? data.filter(s => s && typeof s === 'object' && typeof s.id === 'string' &&
      typeof s.factor === 'string' && typeof s.horizon === 'string') : [];
  } catch { return []; }
}

export function studySnapshot(study) {
  const value = study.snapshot || study.research;
  if (!value || typeof value !== 'object') return null;
  const rows = Array.isArray(value.dynamic_scenarios?.ranked_scenarios) ? value.dynamic_scenarios.ranked_scenarios : [];
  return {...value, items:Array.isArray(value.items) ? value.items.filter(x => x && typeof x === 'object') : [],
    dynamic_scenarios:{...value.dynamic_scenarios,ranked_scenarios:rows.filter(x => x && typeof x.id === 'string')
      .map(x => ({...x,sources:Array.isArray(x.sources) ? x.sources.filter(s => s && typeof s === 'object') : []}))},
    category: study.category, factor: study.factor, focus: study.focus || 'World',
    horizon: study.horizon, generated_at: value.generated_at || study.createdAt,
    basis: study.basis || value.basis || 'END_STATE',
    legacy_snapshot: !study.snapshot};
}

export function evidenceScore(scenario) {
  return typeof scenario?.evidence_score === 'number' && Number.isFinite(scenario.evidence_score) &&
    scenario.evidence_score >= -100 && scenario.evidence_score <= 100 ? scenario.evidence_score : null;
}

export function sourceUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

// A sensitivity illustration is neither a historical frequency nor a calibrated
// forecast. Old snapshots used a direction-distance bug; never display v1 odds.
export function experimentalEstimate(scenario) {
  const model = scenario?.experimental_probability;
  const valid = p => typeof p === 'number' && Number.isFinite(p) && p >= 0 && p <= 1;
  if (scenario?.horizon_eligible === false || model?.model_version !== 'event-probability-experimental-v2' ||
      model.status !== 'EXPERIMENTAL_UNCALIBRATED' || model.calibrated !== false ||
      model.scenario_id !== scenario.id || model.assumed_prior !== .5 ||
      !Number.isInteger(model.evidence_cluster_count) || model.evidence_cluster_count < 1 ||
      !valid(model.probability_estimate) || !Array.isArray(model.prior_sensitivity_range) ||
      model.prior_sensitivity_range.length !== 2 || !model.prior_sensitivity_range.every(valid) ||
      model.prior_sensitivity_range[0] > model.probability_estimate ||
      model.prior_sensitivity_range[1] < model.probability_estimate) return null;
  return model;
}

export function researchShareAvailable(result) {
  const rows = result?.dynamic_scenarios?.ranked_scenarios;
  const distribution = result?.dynamic_scenarios?.scenario_distribution;
  if (distribution?.status !== 'NORMALIZED_EXPERIMENTAL_UNCALIBRATED' ||
      !Array.isArray(rows) || rows.length !== 10 || new Set(rows.map(r=>r.id)).size !== rows.length ||
      !result.items?.some(item=>['DIRECT_SCOPE','GLOBAL_SCOPE'].includes(item.geographic_relation))) return false;
  const values = rows.map(r=>r.scenario_share_percent);
  return values.every(v=>typeof v === 'number' && Number.isFinite(v) && v >= 0 && v < 90) &&
    values.filter(v=>v>0).length >= 2 && Math.abs(values.reduce((a,b)=>a+b,0)-100) <= .05 &&
    typeof distribution.total_percent === 'number' && Math.abs(distribution.total_percent-100) <= .05;
}
