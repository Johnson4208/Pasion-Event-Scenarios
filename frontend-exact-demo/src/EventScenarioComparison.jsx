import React, {useState} from 'react';
import {comparisonRows} from './eventScenarios.js';

export default function EventScenarioComparison({model, recording, t, language, formatDate}) {
  const [sort, setSort] = useState('definition');
  const number = value => new Intl.NumberFormat(language,{minimumFractionDigits:1,maximumFractionDigits:1}).format(value);
  const percent = value => number(value*100)+'%';
  const rows = comparisonRows(model,sort);
  const endState = model.context.basis === 'END_STATE';
  const research = model.method === 'RETROSPECTIVE_SERIES_REFERENCE_V1';
  const closeCount = rows.filter(r => r.close).length;
  return <section className="ev-comparison" aria-label={t('All scenario probabilities')}>
    <header><div><span className="ev-kicker">{t(research ? 'RESEARCH PROBABILITY ESTIMATES' : 'COMPARE EVERY OUTCOME')}</span><h3>{model.question}</h3>
      <p>{t(endState ? 'End-of-period outcomes form one complete, mutually exclusive group.' : 'These events may occur together during the period. Their probabilities do not need to add up to 100%.')}</p></div>
      <label>{t('Display order')}<select aria-label={t('Display order')} value={sort} onChange={e => setSort(e.target.value)}>
        <option value="definition">{t('Scenario definition order')}</option><option value="probability">{t('Highest estimate first')}</option>
      </select></label></header>
    <div className="ev-comparison-summary"><span>{t('{count} outcomes shown together',{count:rows.length})}</span>
      {endState && <span>{t('Total before rounding')}: {percent(rows.reduce((sum,r) => sum+r.probability,0))}</span>}
      {closeCount > 1 && <strong>{t('{count} outcomes are within 3 percentage points of the highest estimate.',{count:closeCount})}</strong>}
    </div>
    {research && <div className="ev-forecast-context">
      <div><span>{t('Current reference observation')}</span><strong>{new Intl.NumberFormat(language,{maximumFractionDigits:3}).format(model.baseline.value)} {model.baseline.unit}</strong><small>{formatDate(model.baseline.observation_at)}</small></div>
      <div><span>{t('Forecast origin')}</span><strong>{formatDate(model.forecast_origin_at)}</strong></div>
      <div><span>{t('End of the selected period')}</span><strong>{formatDate(model.maturity_at)}</strong></div>
      <p data-quality={model.validation.quality}>{t(model.validation.quality === 'LIMITED' ? 'The historical check has limitations. Read the uncertainty ranges and validation details before comparing estimates.' :
        'Retrospective evidence only. Future calibration has not been established.')}</p>
    {recording?.status === 'PENDING' && <p>{t('This forecast was recorded before its end date. Its outcome will be checked after the period ends.')}</p>}
      {recording?.status === 'RECORDING_UNAVAILABLE' && <p>{t('This estimate is available, but recording it for future outcome checks failed. Retry the calculation to record it.')}</p>}
    </div>}
    <p className="ev-comparison-method">{t(research ? 'These research estimates count completed historical changes using the same outcome rules. The 95% ranges describe uncertainty in those historical rates. Current news does not numerically adjust the estimates, and future calibration is not established.' :
      'Historical reference-class estimates. News scores do not change these probabilities. The 95% ranges describe uncertainty in historical rates, not a guarantee about future events.')}</p>
    <div className="ev-comparison-head" aria-hidden="true"><span>{t('Scenario and resolution rule')}</span><span>{t('Probability estimate')}</span><span>{t('95% range')}</span><span>{t('Gap to highest')}</span></div>
    <div className="ev-comparison-rows">{rows.map(row => <article key={row.id} className="ev-comparison-row" data-outcome={row.id}>
      <div className="ev-outcome-description"><h4>{row.title}</h4><p>{row.resolution_rule}</p>{row.close && closeCount > 1 && <span className="ev-close-label">{t('Close estimates')}</span>}</div>
      <div className="ev-outcome-probability"><span className="ev-mobile-label">{t('Probability estimate')}</span><strong>{percent(row.probability)}</strong>
        <div className="ev-probability-scale" aria-hidden="true"><i style={{width:row.probability*100+'%'}}/></div></div>
      <div className="ev-outcome-range"><span className="ev-mobile-label">{t('95% range')}</span><span>{percent(row.interval[0])}–{percent(row.interval[1])}</span></div>
      <div className="ev-outcome-gap"><span className="ev-mobile-label">{t('Gap to highest')}</span><span>{row.gap > 0 && row.gap < .001 ? '<'+number(.1) : number(row.gap*100)} {t('pp')}</span></div>
    </article>)}</div>
    <footer><p>{t('Figures are rounded independently; displayed values may not total exactly 100%. A higher point estimate does not establish a decisive lead.')}</p>
      <details><summary>{t('Model, history and validation')}</summary><dl>
        <div><dt>{t('Model version')}</dt><dd>{model.model_version}</dd></div>
        <div><dt>{t('Outcome definition version')}</dt><dd>{model.definition_version}</dd></div>
        <div><dt>{t(research ? 'Historical training periods' : 'Historical training groups')}</dt><dd>{model.training_sample_count}</dd></div>
        <div><dt>{t(research ? 'Later evaluation periods' : 'Later holdout groups')}</dt><dd>{model.holdout_sample_count}</dd></div>
        <div><dt>{t(research ? 'Training period ends' : 'Training outcomes known through')}</dt><dd>{formatDate(research ? model.training_period_end : model.training_resolved_through)}</dd></div>
        <div><dt>{t(research ? 'Evaluation period begins' : 'Holdout begins')}</dt><dd>{formatDate(research ? model.holdout_period_start : model.holdout_origin_from)}</dd></div>
        <div><dt>{t(research ? 'Evaluation period ends' : 'Holdout outcomes known through')}</dt><dd>{formatDate(research ? model.holdout_period_end : model.holdout_resolved_through)}</dd></div>
        {research && Array.isArray(model.validation.quality_flags) && model.validation.quality_flags.map(flag => ({SMALL_TRAINING_SAMPLE:'Fewer than 100 historical training periods',SMALL_HOLDOUT_SAMPLE:'Fewer than 100 later evaluation periods',RARE_OR_UNOBSERVED_OUTCOMES:'Some outcomes have few or no observed cases',HOLDOUT_RATE_DRIFT:'Outcome rates changed in the later evaluation period'}[flag])).filter(Boolean).map(label => <div key={label}><dt>{t('Validation limitation')}</dt><dd>{t(label)}</dd></div>)}
        {research && <div><dt>{t('Validation status')}</dt><dd>{t('Historical check only; future calibration not established')}</dd></div>}
        <div><dt>{t('Brier score')}</dt><dd>{new Intl.NumberFormat(language,{minimumFractionDigits:3,maximumFractionDigits:3}).format(model.validation.brier_score)}</dd></div>
        {research && <><div><dt>{t('Log loss')}</dt><dd>{number(model.validation.log_loss)}</dd></div><div><dt>{t('Largest historical rate difference')}</dt><dd>{number(model.validation.maximum_rate_error*100)} {t('pp')}</dd></div></>}
        <div><dt>{t('Sampling assumptions')}</dt><dd>{model.sampling_policy}</dd></div>
        {!research && <div><dt>{t('Reviewed')}</dt><dd>{formatDate(model.reviewed_at)}</dd></div>}
        {research && <><div><dt>{t('Historical data collected')}</dt><dd>{formatDate(model.source.retrieved_at)}</dd></div>
          <div><dt>{t('Measured series')}</dt><dd>{model.source.provider} · {model.source.metric}</dd></div>
          <div><dt>{t('Historical source')}</dt><dd>{model.source.source_urls.map(url => <a href={url} key={url} target="_blank" rel="noopener noreferrer">{model.source.provider} ↗</a>)}</dd></div></>}
        <div><dt>{t('Model expires')}</dt><dd>{formatDate(model.expires_at)}</dd></div>
      </dl><p>{t('Passing a historical holdout check does not prove that future probabilities are calibrated. Prospective outcome monitoring is still required.')}</p></details>
    </footer>
  </section>;
}
