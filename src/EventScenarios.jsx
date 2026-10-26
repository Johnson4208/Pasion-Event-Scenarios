import React,{useEffect,useRef,useState} from 'react';
import {usePreferences} from './Preferences';
import './event-scenarios.scss';
import EventScenarioComparison from './EventScenarioComparison';
import EventSourceStatus from './EventSourceStatus';
import {referenceForecast,seriesForecast,experimentalEstimate,researchShareAvailable,queryKey,sourceUrl,readStudies as readValidStudies,studySnapshot,HORIZONS} from './eventScenarios.js';


const categories={
 'Banking & Credit':['Credit conditions','Bank lending','Central bank policy'],
 Business:['M&A activity','Earnings outlook','Hiring plans'],
 Consumer:['Consumer demand','Household spending','Consumer confidence'],
 Economy:['Inflation','GDP growth','Labor market'],
 Energy:['Oil supply','Natural gas','Energy prices'],
 Geopolitics:['Conflict risk','Sanctions','Trade disruption'],
 Health:['Drug approvals','Healthcare costs','Public health'],
 Markets:['Equity volatility','Market liquidity','Risk appetite'],
 'Politics & Policy':['Fiscal policy','Regulation','Trade policy'],
 'Real Estate':['Property prices','Mortgage rates','Commercial demand'],
 Science:['Research funding','Clinical progress','Technology adoption'],
 Technology:['AI adoption','Semiconductor supply','Cybersecurity'],
};

export default function EventScenarios({storageKey='pasion-event-scenarios'}){
 const {t,language}=usePreferences();
 const formatDate=value=>Number.isFinite(Date.parse(value))?new Date(value).toLocaleString(language):'Date unavailable';
 const [category,setCategory]=useState('Geopolitics'),[factor,setFactor]=useState('Conflict risk'),[focus,setFocus]=useState('Vietnam');
 const [term,setTerm]=useState('short'),[horizon,setHorizon]=useState('30 days');
 const [result,setResult]=useState(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const [evidenceOpen,setEvidenceOpen]=useState(null),[previousResult,setPreviousResult]=useState(null);
 const key=storageKey+'-event-research';
 const [archive,setArchive]=useState(()=>({key,studies:readValidStudies(key)}));
 const studies=archive.key===key?archive.studies:[];
 const setStudies=update=>setArchive(old=>({key,studies:update(old.key===key?old.studies:[])}));
 const request=useRef(null);
 const [basis,setBasis]=useState('END_STATE');
 const [metric,setMetric]=useState('estimate');
 const [failedCoverage,setFailedCoverage]=useState(null);
 const queryContext={category,factor,focus:focus.trim()||'World',horizon,basis};
 const identity=queryKey(queryContext);
 const activeIdentity=useRef(identity);activeIdentity.current=identity;
 useEffect(()=>{setArchive({key,studies:readValidStudies(key)});setResult(null);setPreviousResult(null);setLoading(false);return()=>{request.current?.abort();request.current=null;};},[key]);
 useEffect(()=>()=>{request.current?.abort();request.current=null;},[]);
 useEffect(()=>{setError('');setFailedCoverage(null);setPreviousResult(null);},[identity]);
 const [savedOnly,setSavedOnly]=useState(false);
 useEffect(()=>{if(archive.key===key)try{localStorage.setItem(key,JSON.stringify(archive.studies))}catch{setError('Browser storage is unavailable or full. This report is kept only in this tab.');}},[key,archive]);
 useEffect(()=>{
  if(!evidenceOpen)return;
  const onKey=e=>{if(e.key==='Escape')setEvidenceOpen(null)};
  window.addEventListener('keydown',onKey);
  const old=document.body.style.overflow;document.body.style.overflow='hidden';
  return()=>{window.removeEventListener('keydown',onKey);document.body.style.overflow=old};
 },[evidenceOpen]);
 const showExpanded=loading||result!==null;
 const forecast=referenceForecast(result)||seriesForecast(result);
 const historical=!!forecast;
 const scenarioDistribution=result?.dynamic_scenarios?.scenario_distribution;
 const hasEligibleNews=(result?.items||[]).some(item=>['DIRECT_SCOPE','GLOBAL_SCOPE'].includes(item.geographic_relation));
 const researchAvailable=researchShareAvailable(result);
 const ranked=result?.dynamic_scenarios?.ranked_scenarios||[];
 const oldRanked=previousResult?.dynamic_scenarios?.ranked_scenarios||[];
 const experimentalAvailable=hasEligibleNews&&ranked.some(sc=>experimentalEstimate(sc));
 const ready=!!result&&!loading;
 const statusLabel=historical?'Historical probability estimates':experimentalAvailable?'Experimental · assumption-based':'Probability unavailable';
 const noEligible=!!result&&!loading&&!historical&&!experimentalAvailable;
 function changeTerm(value){setTerm(value);setHorizon(value==='short'?'30 days':'180 days');setResult(null);setError('');}
 function changeCategory(value){setCategory(value);setFactor(categories[value][0]);setResult(null);}
 async function runAnalysis(){
  if(loading)return;
  request.current?.abort();
  const controller=new AbortController();request.current=controller;
  const submitted={...queryContext},submittedIdentity=identity;
  const current=()=>request.current===controller&&activeIdentity.current===submittedIdentity;
  setLoading(true);setError('');setFailedCoverage(null);setEvidenceOpen(null);
  const timeout=setTimeout(()=>controller.abort(),45000);
  async function read(url,options={}){
   const response=await fetch(url,{credentials:'same-origin',signal:controller.signal,...options});
   const data=await response.json();
   if(!response.ok){const error=Error(response.status===401?'Please sign in again.':data.reason_code||data.message||'Sources currently unavailable');error.coverage=data.coverage;throw error;}
   if(data.version!==1||queryKey(data)!==submittedIdentity)throw Error('Response does not match the selected research question.');
   return data;
  }
  try{
   // Preparation restores the existing historical-series engine. A news outage
   // must not hide an independently available historical outcome model.
   const [news,model]=await Promise.allSettled([
    read('/api/research/events/live?'+new URLSearchParams(submitted)),
    read('/api/research/events/forecast',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(submitted)})
   ]);
   if(!current())return;
   if(news.status==='rejected'&&model.status==='rejected')throw news.reason;
   const data=news.status==='fulfilled'?news.value:model.value;
   const prepared=model.status==='fulfilled'&&(referenceForecast(model.value)||seriesForecast(model.value));
   const usePrepared=model.status==='fulfilled'&&(prepared||!(referenceForecast(data)||seriesForecast(data)));
   const combined=usePrepared?{...data,scenario_forecast:model.value.scenario_forecast,forecast_recording:model.value.forecast_recording}:data;
   combined.items=Array.isArray(combined.items)?combined.items.filter(x=>x&&typeof x==='object'):[];
   combined.dynamic_scenarios={...combined.dynamic_scenarios,ranked_scenarios:Array.isArray(combined.dynamic_scenarios?.ranked_scenarios)?combined.dynamic_scenarios.ranked_scenarios.filter(x=>x&&typeof x.id==='string'):[]};
   setPreviousResult(result&&queryKey(result)===submittedIdentity?result:null);
   setResult(combined);
   if(news.status==='rejected'){setError('News collection failed. Historical estimates, if available, remain visible.');setFailedCoverage(news.reason.coverage||{status:'UNAVAILABLE'});}
   else if(model.status==='rejected')setError('Historical preparation failed. The sourced news analysis remains available.');
  }catch(e){if(current()){setError(e.name==='AbortError'?'Analysis timed out. Please retry.':e?.message||'Unable to retrieve data');setFailedCoverage(e.coverage||null);}}
  finally{clearTimeout(timeout);if(current())setLoading(false);}
 }
 function saveResearch(){
  if(!ready)return;
  setStudies(s=>[{id:crypto.randomUUID(),category,factor,focus:queryContext.focus,horizon,basis,createdAt:result.generated_at,saved:true,note:'',
   research:result,snapshot:result},...s]);
 }
 function openStudy(study){
  const snapshot=studySnapshot(study);
  if(!snapshot||!categories[study.category]?.includes(study.factor))return;
  const long=HORIZONS.long.some(([value])=>value===study.horizon);
  if(![...HORIZONS.short,...HORIZONS.long].some(([value])=>value===study.horizon))return;
  setCategory(study.category);setFactor(study.factor);setFocus(study.focus||'World');setHorizon(study.horizon);
  setTerm(long?'long':'short');setBasis(study.basis||'END_STATE');setPreviousResult(null);setResult(snapshot);
 }
 function updateStudy(id,field,value){setStudies(s=>s.map(x=>x.id===id?{...x,[field]:value}:x));}
 const evidenceItems=(evidenceOpen?.id?evidenceOpen.sources:result?.items)||[];
 return <div className="analytics-page event-scenarios-page events-refined">
  <section className="home-card events-intro-card">
   <div><span className="events-eyebrow">PASION / EVENT INTELLIGENCE</span><h2>Dynamic Scenario Forecasting</h2>
    <p>Track plausible economic paths with sourced evidence, separate forecast horizons and clear model eligibility.</p></div>
   <aside className="events-research-status"><strong>DATA INTEGRITY</strong><span>{loading?'Updating evidence…':ready?'Published-source research · unverified':'Awaiting a sourced analysis'}</span></aside>
  </section>
  <section className="home-card events-question-card">
   <div className="events-section-kicker">RESEARCH CONFIGURATION</div>
   <div className="events-question-grid">
    <label>Category<select disabled={loading} value={category} onChange={e=>changeCategory(e.target.value)}>{Object.keys(categories).map(x=><option value={x} key={x}>{t(x)}</option>)}</select></label>
    <label>Factor<select disabled={loading} value={factor} onChange={e=>{setFactor(e.target.value);setResult(null)}}>{categories[category].map(x=><option value={x} key={x}>{t(x)}</option>)}</select></label>
    <label>Region / entity<input disabled={loading} value={focus} onChange={e=>{setFocus(e.target.value);setResult(null)}} maxLength={120} list="event-region-hints"/><datalist id="event-region-hints">{['World','Asia','Southeast Asia','Vietnam','United States','Europe','Middle East'].map(x=><option value={x} key={x}/>)}</datalist></label>
    <div className="events-term-controls"><span>Forecast horizon</span><div role="group" aria-label="Forecast horizon type" className="events-term-tabs"><button type="button" disabled={loading} aria-pressed={term==='short'} className={term==='short'?'active':''} onClick={()=>changeTerm('short')}>Short-term</button><button type="button" disabled={loading} aria-pressed={term==='long'} className={term==='long'?'active':''} onClick={()=>changeTerm('long')}>Long-term</button></div><select disabled={loading} aria-label="Forecast duration" value={horizon} onChange={e=>{setHorizon(e.target.value);setResult(null)}}>{HORIZONS[term].map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></div>
    <label>Probability question<select disabled={loading} value={basis} onChange={e=>{setBasis(e.target.value);setResult(null)}}><option value="END_STATE">At the end of the period</option><option value="OCCURRENCE">Occurs during the period</option></select></label>
    <button type="button" className="events-run-button" disabled={loading} onClick={runAnalysis}>{loading?'Analyzing…':'Analyze'} <span aria-hidden="true">→</span></button>
   </div>
  </section>
  {error&&<section role="alert" className="home-card events-error">Source research unavailable: {error}</section>}
  <section className={'home-card events-result-card events-ranking-shell'+(!showExpanded?' events-ranking-compact':'')} aria-label="Scenario ranking" aria-busy={loading}>
   <div className="events-ranking-heading"><div><span className="events-section-kicker">SCENARIO OUTLOOK / {term==='short'?'SHORT-TERM':'LONG-TERM'}</span><h2>Ranked scenario pathways</h2>
    <p>{factor} · {focus||'World'} · {HORIZONS[term].find(x=>x[0]===horizon)?.[1]}{result?.generated_at?' · Report as of '+formatDate(result.generated_at):''}</p></div>
    {showExpanded&&<div className="events-ranking-actions"><span className="events-model-flag">{statusLabel}</span>
      <button type="button" onClick={()=>setEvidenceOpen({id:null,sources:result?.items||[]})} disabled={!result?.items?.length}>Evidence <span aria-hidden="true">↗</span></button>
      <button type="button" disabled={!ready} onClick={saveResearch}>Save research</button>
    </div>}</div>
   {!showExpanded&&<div className="events-initial-summary" role="status"><div className="events-initial-value"><strong>—</strong><span>Not calculated</span></div><p>Choose your research settings and select <strong>Analyze</strong> to reveal the scenario ranking.</p></div>}
   {showExpanded&&<>
   {forecast&&<EventScenarioComparison model={forecast} recording={result.forecast_recording} t={t} language={language} formatDate={formatDate}/>}
   {!forecast&&result?.scenario_forecast&&<div className="events-model-diagnostic" role="status"><strong>Historical probability model unavailable</strong><p>{result.scenario_forecast.reason_code||'The returned model did not pass validation.'} · Historical observations for this exact question and horizon are required. News estimates below use explicit assumptions instead.</p></div>}
   {noEligible&&<div className="events-empty-diagnostic" role="status"><strong>{scenarioDistribution?.status==='WITHHELD_CONCENTRATED_EVIDENCE'?'Evidence leans strongly one way — probability not validated':'Not enough evidence to calculate'}</strong><p>Review the source roles below. Missing estimates are shown as —, never as a zero probability.</p></div>}
   {!!ranked.length&&<>
   <div className="events-metric-controls"><h3>News evidence pathways</h3><label>Display metric<select aria-label="Display metric" value={metric} onChange={e=>setMetric(e.target.value)}><option value="estimate">Experimental estimate</option><option value="evidence">Evidence balance</option><option value="share">Relative news share</option></select></label></div>
   <p className="events-ranked-note">{metric==='estimate'?'Experimental, assumption-based estimates use a 50% prior for each overlapping pathway. They are not validated event probabilities, do not add to 100%, and are not calibrated to the selected duration. The range shows sensitivity to 25%–75% priors, not a confidence interval.':metric==='evidence'?'Evidence balance = 100 × (supporting weight − opposing weight) / eligible evidence weight. It is not a probability.':'Relative allocation of net supporting news across overlapping pathways. Shares are not event probabilities; concentrated evidence is not normalized into artificial certainty.'} Pathways are ranked by evidence balance, not ranked by probability.</p>
   <div className="events-ranked-list">{ranked.map(sc=>{
      const estimate=hasEligibleNews?experimentalEstimate(sc):null;
      const balance=typeof sc.support_index==='number'&&Number.isFinite(sc.support_index)&&Math.abs(sc.support_index)<=1?sc.support_index*100:null;
      const share=researchAvailable&&sc.scenario_share_status==='NORMALIZED_EXPERIMENTAL_UNCALIBRATED'?sc.scenario_share_percent:null;
      const value=metric==='estimate'?(estimate?estimate.probability_estimate*100:null):metric==='evidence'?balance:share;
      const label=value===null?'—':value.toFixed(1)+(metric==='evidence'?' pts':'%'+(metric==='estimate'?'*':''));
      const old=oldRanked.find(x=>x.id===sc.id);
      const delta=typeof old?.support_index==='number'&&balance!==null?Math.round(balance-100*old.support_index):null;
      const reason=sc.horizon_eligible===false?'Outside selected horizon':!hasEligibleNews?'No in-scope evidence':estimate?'Assumption-based estimate':'Insufficient directional evidence';
      return <article key={sc.id} className="events-ranked-item">
       <span className="events-rank-number">{String(sc.rank).padStart(2,'0')}</span>
       <div className="events-rank-main"><div className="events-rank-heading"><div><strong>{sc.title}</strong><p>{sc.definition}</p></div><span className="events-rank-value" title={value===null?reason:metric==='estimate'?'Experimental estimate, not a validated probability':metric==='evidence'?'Signed evidence balance':'Relative news share'}>{label}</span></div>
        <div className="events-ranked-track" role="img" aria-label={value===null?reason:metric+' '+label}><i style={{width:value===null?'0%':Math.min(100,Math.abs(value))+'%',background:metric==='evidence'&&value<0?'#b45353':undefined}}/></div>
        {metric==='estimate'&&estimate&&<p className="events-estimate-range">Prior sensitivity: {(estimate.prior_sensitivity_range[0]*100).toFixed(1)}–{(estimate.prior_sensitivity_range[1]*100).toFixed(1)}% · {estimate.evidence_cluster_count} distinct stories · independence unverified</p>}
        <div className="events-rank-foot"><span>{reason} · {sc.supporting_source_count||0} supports · {sc.opposing_source_count||0} challenges · {sc.context_source_count||0} context{delta===null?'':' · evidence revised '+(delta>0?'+':'')+delta+' pts'}</span>
         <button type="button" onClick={()=>setEvidenceOpen({id:sc.id,title:sc.title,sources:Array.isArray(sc.sources)?sc.sources:[]})}>Evidence <span aria-hidden="true">↗</span></button></div>
       </div>
      </article>;
    })}</div>
   {metric==='share'&&researchAvailable&&<div className="events-distribution-total" role="status"><span>Total news share</span><strong>{scenarioDistribution.total_percent.toFixed(1)}%</strong></div>}
   </>}
   </>}
   {loading&&<div className="events-loading-overlay" role="status" aria-live="polite"><div className="events-loading-spinner" aria-hidden="true"/><strong>Analyzing new evidence</strong><span>Retrieving sources and comparing scenario pathways…</span></div>}
  </section>
  {(result||failedCoverage)&&<EventSourceStatus result={result} query={queryContext} failedCoverage={failedCoverage} showArchive={false} t={t} formatDate={formatDate}/>}
  <section className="home-card events-forecast-lab"><header className="events-lab-heading"><div><span className="events-section-kicker">RESEARCH ARCHIVE</span><h3>Saved investigations</h3><p>Local saved reports, separate from the independent public-news agent.</p></div><div className="events-history-tabs"><button aria-pressed={!savedOnly} onClick={()=>setSavedOnly(false)}>All</button><button aria-pressed={savedOnly} onClick={()=>setSavedOnly(true)}>Saved ({studies.filter(x=>x.saved).length})</button></div></header>
   <div className="events-history-list">{studies.filter(x=>!savedOnly||x.saved).map(s=><article className="events-history-item" key={s.id}><header><div><strong>{s.factor} · {s.focus}</strong><p>{s.horizon} · {s.createdAt?new Date(s.createdAt).toLocaleString():'Date unavailable'}</p></div><div className="events-history-actions"><button disabled={loading} onClick={()=>openStudy(s)}>Open report</button><button onClick={()=>updateStudy(s.id,'saved',!s.saved)}>{s.saved?'★':'☆'}</button><button onClick={()=>setStudies(x=>x.filter(item=>item.id!==s.id))}>×</button></div></header></article>)}</div>
  </section>
  {evidenceOpen&&<div className="events-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setEvidenceOpen(null)}}><div role="dialog" aria-modal="true" aria-labelledby="events-evidence-title" className="events-evidence-modal">
    <div className="events-modal-heading"><div><span className="events-section-kicker">RESEARCH EVIDENCE</span><h2 id="events-evidence-title">{evidenceOpen.title||'Published articles and source weights'}</h2><p>Original-source verification may be incomplete. Entries describe published evidence, not a confirmed outcome.</p></div><button type="button" className="events-modal-close" aria-label="Close evidence" onClick={()=>setEvidenceOpen(null)}>×</button></div>
    <div className="events-modal-toolbar"><span>{evidenceItems.length} linked articles</span><span>Source trace / relevance / publish time</span></div>
    <div className="events-evidence-scroll">{evidenceItems.length?evidenceItems.map((x,i)=><article key={x.id||x.url||i} className="events-evidence-row"><span className="events-evidence-number">{String(i+1).padStart(2,'0')}</span><div><a target="_blank" rel="noopener noreferrer" href={sourceUrl(x.url)||undefined}>{x.title||'Original article'} ↗</a><p>{x.source||'Source unavailable'} · {x.published_at?new Date(x.published_at).toLocaleString():'Date unverified'}</p><small>{x.evidence_role||'CONTEXT'} · {x.match_reason||x.topic_match_reason||'Interpretation unavailable'} · {x.geographic_relation||'Scope unverified'} · {x.source_verification||'Unverified publication'} · {x.description||'No full-text excerpt available'}{x.relevance!=null?' · Relevance '+x.relevance:''}{x.weight!=null?' · Evidence weight '+x.weight:''}{x.contribution!=null?' · Signed contribution '+x.contribution:''}</small></div></article>):<div className="events-empty-evidence">No individually linked articles for this scenario.</div>}</div>
   </div></div>}
 </div>;
}
