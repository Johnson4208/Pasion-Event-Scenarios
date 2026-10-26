import React, {useEffect, useState} from 'react';
import {usePreferences} from './Preferences';
import './macro-evidence.scss';

function useEvidence(url) {
 const [state,setState]=useState({url:null});
 useEffect(()=>{const controller=new AbortController();let active=true;
  setState({url});fetch(url,{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error();const data=await r.json();if(data.version!==1)throw Error();return data;}).then(data=>{if(active)setState({url,data});}).catch(()=>{if(active)setState({url,error:true});});
  return ()=>{active=false;controller.abort();};
 },[url]);return state.url===url?state:{};
}

function ObservationChart({history,name}) {
 const ready=history.filter(r=>r.value!==null);if(ready.length<2)return <p>At least two released observations are required for a chart.</p>;
 const values=ready.map(r=>Number(r.value)),low=Math.min(...values),high=Math.max(...values);
 const dates=history.map(r=>Date.parse(r.period_end)),start=Math.min(...dates),end=Math.max(...dates);
 let path='',previous=false;
 history.forEach(r=>{if(r.value===null){previous=false;return;}const x=10+(Date.parse(r.period_end)-start)/(end-start||1)*480,y=130-(Number(r.value)-low)/(high-low||1)*110;path+=`${previous?'L':'M'}${x},${y} `;previous=true;});
 return <><svg viewBox="0 0 500 150" role="img" aria-label={`${name} released observations`}><path d={path} fill="none" stroke="#2468f2" strokeWidth="2"/></svg><small>{ready[0].period_end} — {ready.at(-1).period_end} · {low} to {high}</small></>;
}

export default function MacroEvidence({scope,title}) {
 const {t}=usePreferences();const [date,setDate]=useState(''),[origin,setOrigin]=useState('');
 const state=useEvidence(`/api/research/macro?scope=${encodeURIComponent(scope)}${origin?`&origin=${encodeURIComponent(origin)}`:''}`);
 return <div className="macro-evidence"><section className="home-card"><h2>{title} · {t('Reviewed macro evidence')}</h2>
 <form onSubmit={e=>{e.preventDefault();setOrigin(date?new Date(date).toISOString():'');}}><label>{t('Research origin (local time)')} <input type="datetime-local" value={date} onChange={e=>setDate(e.target.value)}/></label><button>{t('Apply origin')}</button><button type="button" onClick={()=>{setDate('');setOrigin('');}}>{t('Latest')}</button></form>
 {!state.data?<p role="status">{t(state.error?'Macro evidence service unavailable.':'Loading reviewed observations…')}</p>:<><p role="status">{state.data.status} · {t('Covered factors')}: {state.data.coverage.covered.join(', ')||'0 / 5'}</p><p>{t('Missing factors')}: {state.data.coverage.missing.join(', ')||'None'} · {state.data.origin}</p><p>{t('Each scope needs its own reviewed series. Regional aggregates are not inferred from country observations.')}</p>{!state.data.series.length&&<p>{t('No reviewed series registered for this scope. No regime fit is available.')}</p>}<p>{t('Regime fit')}: {state.data.regime?.fit||'UNAVAILABLE'} · {state.data.regime?.label||'Reviewed factor rules required'}</p></>}
 </section><div className="macro-evidence-grid">{state.data?.series.map(s=><article className="home-card" key={s.id}><h3>{s.name}</h3><p>{s.kind} · {s.unit} · {s.frequency} · {s.status}</p><strong>{s.status==='READY'?s.latest.value:'—'}</strong>{s.reason&&<p>{s.reason}</p>}<ObservationChart history={s.history} name={s.name}/><p>{s.heuristic_fit||'No eligible rule'} · {s.fit_label}</p>{s.rule&&<p>{s.rule.meaning} · {s.rule.low}–{s.rule.high} {s.unit}</p>}<details><summary>{t('Source and release vintages')}</summary><p><a href={s.source_url} target="_blank" rel="noreferrer">{s.provider}</a> · {s.calendar} · {s.timezone}</p><table><thead><tr><th>Period</th><th>Value / unit</th><th>Released / known</th><th>Revision / expiry</th></tr></thead><tbody>{s.history.map(r=><tr key={r.id||r.period_end}><td>{r.period_end}</td><td>{r.value??'Missing'} {s.unit}</td><td>{r.release_at}<br/>{r.known_at}</td><td>{r.revision}<br/>{r.expires_at}</td></tr>)}</tbody></table></details></article>)}</div></div>;
}

export function CommodityStress({ticker}) {
 const {t}=usePreferences();const state=useEvidence(`/api/research/commodity-exposures?ticker=${encodeURIComponent(ticker)}`);
 const [result,setResult]=useState(null),[busy,setBusy]=useState(false);useEffect(()=>setResult(null),[ticker]);
 return <section className="home-card macro-evidence"><h3>{t('Commodity exposure & scenario stress')}</h3><p>{t('Segment evidence and contract repricing determine sensitivity. All shock inputs are explicit scenario assumptions.')}</p>
 {!state.data?<p>{t(state.error?'Exposure evidence unavailable.':'Loading exposure evidence…')}</p>:!state.data.exposures.length?<p>{t('No reviewed issuer exposure mapping. Commodity sensitivity is unavailable.')}</p>:state.data.exposures.map(x=><form key={x.id} onSubmit={async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.currentTarget));setBusy(true);setResult(null);try{const r=await fetch('/api/research/commodity-stress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,exposure_id:x.id,currency:x.currency,volume_unit:x.volume_unit})});if(!r.ok)throw Error();const data=await r.json();if(data.version!==1)throw Error();setResult({ticker,data});}catch{setResult({ticker,error:true});}finally{setBusy(false);}}}>
 <h4>{x.segment} · {x.commodity} · {x.grade} · {x.location}</h4><p>{x.period_start}–{x.period_end} · {x.currency}/{x.volume_unit}</p><p>Output {x.output_volume} × repricing {x.output_repricing_fraction}; input {x.input_volume} × repricing {x.input_repricing_fraction}</p><p>Contract reset: {x.contract_reset} · Inventory lag: {x.inventory_lag} · Hedge scope: {x.hedge_scope}</p><p>Known: {x.known_at} · Expires: {x.expires_at}</p><p>Accepted fact evidence: {x.fact_ids.join(', ')}</p>
 {['output_price_delta','input_price_delta','pass_through','hedge_pnl','incremental_costs'].map(key=><label key={key}>{t(key.replaceAll('_',' '))} ({key.includes('price')?`${x.currency}/${x.volume_unit}`:x.currency}) <input name={key} type="number" step="any" required min={key==='incremental_costs'?0:undefined}/></label>)}<button disabled={busy}>{t('Calculate proposed EBIT scenario')}</button></form>)}
 {result?.ticker===ticker&&<div role="status">{result.error?'Scenario service unavailable':<><strong>{result.data.status} · Δ EBIT {result.data.delta_ebit??'—'} {result.data.currency}</strong>{result.data.reason&&<p>{result.data.reason}</p>}{result.data.bridge&&<><p>{Object.entries(result.data.bridge).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p><p>{t('Proposed scenario only. Review operating forecast drivers before applying it to valuation.')}</p><button type="button" onClick={()=>{const blob=new Blob([JSON.stringify(result.data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`${ticker}-commodity-scenario.json`;a.click();URL.revokeObjectURL(url);}}>{t('Export scenario and source lineage')}</button></>}</>}</div>}
 </section>;
}
