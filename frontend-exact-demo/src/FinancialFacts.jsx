import React, {useEffect, useState} from 'react';
import {usePreferences} from './Preferences';
import {downloadCSV} from './analytics';
import {fetchVersioned,metricText} from './researchApi';
import './financial-facts.scss';

const labels = {revenue:'Revenue',net_income:'Net income',net_income_common:'Common shareholder income',ebit:'EBIT',ebitda:'Standard EBITDA',cfo:'Operating cash flow',net_margin:'Net margin',ebitda_margin:'EBITDA margin',cfo_margin:'Cash flow margin',roa:'ROA',roe:'ROE',assets:'Total assets',equity:'Equity',common_equity:'Common equity',debt:'Debt',cash:'Cash',current_assets:'Current assets',current_liabilities:'Current liabilities',working_capital:'Working capital',current_ratio:'Current ratio',debt_equity:'Debt / equity',debt_ebitda:'Debt / annual EBITDA',eps:'EPS',dividends:'Dividends',shares_outstanding:'Shares outstanding'};

function useResearch(url) {
  const [state, setState] = useState({url:null, data:null, error:null});
  useEffect(() => {
    let active=true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    setState({url,data:null,error:null});
    fetchVersioned(url,{signal:controller.signal}).then(data => {if(active)setState({url,data,error:null});})
      .catch(() => {if(active)setState({url,data:null,error:'Research service unavailable'});})
      .finally(() => clearTimeout(timeout));
    return () => {active=false;controller.abort();clearTimeout(timeout);};
  },[url]);
  return state.url === url ? state : {data:null,error:null};
}

export function FinancialMode({value,onChange}) {
  const {t}=usePreferences();
  return <label className="financial-mode">{t('Financial data')} <select aria-label={t('Financial data mode')} value={value} onChange={e=>onChange(e.target.value)}><option value="reviewed">{t('Reviewed filings')}</option><option value="sample">{t('Illustrative sample')}</option></select></label>;
}

function Period({value,onChange}) {
  const {t}=usePreferences();
  return <label>{t('Reporting period')} <select aria-label={t('Reporting period')} value={value} onChange={e=>onChange(e.target.value)}>{['Q','YTD','FY','TTM'].map(v=><option key={v}>{v}</option>)}</select></label>;
}

export function factValue(fact) {
  return metricText(fact);
}

function SourceDetails({metric,onClose}) {
  const {t}=usePreferences();
  const [sources,setSources]=useState(null);
  useEffect(() => {
    let active=true;
    const controller=new AbortController();
    Promise.all(metric.source_ids.map(id=>fetch('/api/research/facts/'+encodeURIComponent(id)+'/evidence',{signal:controller.signal}).then(r=>{if(!r.ok)throw new Error();return r.json();})))
      .then(data=>{if(active)setSources(data);}).catch(()=>{if(active)setSources([]);});
    return ()=>{active=false;controller.abort();};
  },[metric]);
  return <section className="financial-source" aria-label={t('Metric source details')}><header><h4>{t('Metric source details')}</h4><button type="button" onClick={onClose}>{t('Close')}</button></header><p>{t(labels[metric.definition_id]||metric.definition_id)} · {metric.status} · {metric.origin}</p><p>{metric.period_start} – {metric.period_end} · {metric.currency} · {metric.scope} · {metric.accounting_basis}</p><p>{metric.basis_flags?.join(' · ')} {metric.annualization_policy||''}</p><p>{t('Known at')}: {metric.known_at||'—'}</p>{sources === null ? <p>{t('Loading evidence')}</p> : sources.length ? sources.map(s=><dl key={s.id}>{['report_id','definition_id','value','unit','currency','period_start','period_end','scope','accounting_basis','restatement_basis','revision','published_at','indexed_at','accepted_at','known_at','as_of','calculation_version','contract_version','exact_scale','rounding_policy','object_type'].map(k=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{s[k]??'—'}</dd></div>)}{['page','table','tag'].map(k=><div key={k}><dt>{k}</dt><dd>{s.evidence[k]}</dd></div>)}{s.source_url&&<div><dt>{t('Official filing')}</dt><dd><a href={s.source_url} target="_blank" rel="noopener noreferrer">{t('Open source filing')} ↗</a>{s.source_line_label&&<p>{s.source_line_label}</p>}</dd></div>}{s.source_excerpt&&<div><dt>{t('Exact reviewed source')}</dt><dd><blockquote>{s.source_excerpt.excerpt}</blockquote><p>{s.source_excerpt.row_context} · {s.source_excerpt.column_context}</p><p>{s.source_excerpt.page_kind} · {s.source_excerpt.section_id} · {s.source_excerpt.source_hash}</p></dd></div>}</dl>) : <p>{t('No accepted source evidence available')}</p>}</section>;
}

export default function FinancialFacts({ticker,compact=false}) {
  const {t}=usePreferences();
  const [period,setPeriod]=useState('TTM'),[end,setEnd]=useState(''),[source,setSource]=useState(null);
  useEffect(()=>{setEnd('');setSource(null);},[ticker]);
  const {data,error}=useResearch('/api/research/company/'+encodeURIComponent(ticker)+'?period='+period+(end?'&end='+end:''));
  return <section className="financial-facts" aria-label={t('Reviewed company financials')}><header><div><h3>{t('Reviewed company financials')} · {ticker}</h3><p>{t('Accepted filings only · missing values remain unavailable')}</p></div><Period value={period} onChange={v=>{setPeriod(v);setSource(null);}}/>{data?.available_ends?.length>0&&<label>{t('Period end')} <select aria-label={t('Financial period end')} value={end||data.period_end||''} onChange={e=>{setEnd(e.target.value);setSource(null);}}>{data.available_ends.map(v=><option key={v}>{v}</option>)}</select></label>}</header>
    {error&&<p role="status">{t(error)}</p>}{!data&&!error&&<p role="status">{t('Loading reviewed facts')}</p>}{data&&<>{data.quality&&<details><summary>{t('Financial relationship quality')} · {data.quality.coverage.eligible}/{data.quality.coverage.total}</summary><p>{t('Research screening only; no fraud probability or universal margin threshold.')}</p>{data.quality.diagnostics.map(d=><article key={d.definition_id}><strong>{d.definition_id}: {d.value??'Unavailable'} {d.unit} · {d.status}</strong><p>{d.reason_codes.join(' · ')}</p><p>{d.inputs.map(i=>`${i.definition_id}: ${i.value??'Missing'} ${i.currency||''} · ${i.period_start}–${i.period_end}`).join(' / ')}</p><p>Sources: {d.source_ids.join(', ')||'Missing'}</p></article>)}{data.quality.flags.map(f=><p key={f.code}>{f.code} · {f.interpretation}</p>)}<p>Beneish: {data.quality.beneish.status} · {data.quality.beneish.reason_codes.join(', ')}</p><p>Peers: {data.quality.peers.status} · {data.quality.peers.reason_codes.join(', ')}</p><p>Health heuristic: {data.quality.health_heuristic.status} · {data.quality.health_heuristic.label}</p></details>}<p role="status">{data.status} · {data.company.name} · {data.period_end||t('No reviewed filings')} · {t('Ratios require matching currency, scope, accounting basis and periods.')}</p><dl className="company-metrics financial-metrics">{Object.entries(labels).filter(([key])=>!compact||['revenue','net_income','ebitda','cfo','net_margin','roe'].includes(key)).map(([key,label])=>{const fact=data.metrics[key];return <div key={key}><dt>{t(label)}</dt><dd>{factValue(fact)}</dd><small>{fact?.status||'UNAVAILABLE'} · {fact?.origin||'—'}</small><small>{fact?.reason_codes?.map(r=>r.replaceAll('_',' ')).join(', ')}</small>{fact?.source_ids?.length>0&&<button type="button" onClick={()=>setSource(fact)}>{t('View metric evidence')} · {t(label)}</button>}</div>})}</dl>
    {!compact&&<><h4>{t('Financial relationships')}</h4><ul>{data.summary.map(row=><li key={row.metric}>{t(row.label)}: {factValue(row.result)} · {row.result.status}</li>)}</ul><h4>{t('Financial series')}</h4><div className="analytics-table-scroll"><table><thead><tr><th>{t('Metric')}</th><th>{t('Period')}</th><th>{t('Value')}</th><th>{t('Status')}</th></tr></thead><tbody>{Object.entries(data.series).flatMap(([metric,rows])=>rows.map((row,index)=><tr key={metric+index}><th>{t(labels[metric])}</th><td>{row.period_start||'—'} – {row.period_end||data.available_ends[index]}</td><td>{factValue(row)}</td><td>{row.status}</td></tr>))}</tbody></table></div></>}
    </>}{source&&<SourceDetails key={source.definition_id+source.known_at} metric={source} onClose={()=>setSource(null)}/>}</section>;
}

export function CanonicalComparison({tickers}) {
  const {t}=usePreferences();
  const [period,setPeriod]=useState('TTM'),[end,setEnd]=useState('');
  const {data,error}=useResearch('/api/research/compare?tickers='+tickers.join(',')+'&period='+period+(end?'&end='+end:''));
  return <section className="financial-facts"><header><h3>{t('Reviewed financial comparison')}</h3><Period value={period} onChange={setPeriod}/><label>{t('Shared period end')} <input type="date" aria-label={t('Shared period end')} value={end} onChange={e=>setEnd(e.target.value)}/></label></header><p>{t('Values are comparable only when unit, currency, scope, accounting basis and exact reporting dates match.')}</p>{error&&<p>{t(error)}</p>}{data&&<><div className="analytics-table-scroll"><table className="comparison-table"><thead><tr><th>{t('Metric')}</th>{data.companies.map(c=><th key={c.ticker}>{c.ticker}</th>)}<th>{t('Comparability')}</th></tr></thead><tbody>{data.rows.map(row=><tr key={row.definition_id}><th>{t(labels[row.definition_id])}</th>{row.cells.map((c,i)=><td key={i}>{factValue(c)}<small>{c.status} · {c.period_start} – {c.period_end} · {c.scope} · {c.accounting_basis}</small></td>)}<td>{t(row.comparable?'Comparable':'Not comparable')}</td></tr>)}</tbody></table></div><button className="dashboard-button" onClick={()=>downloadCSV('pasion-reviewed-comparison.csv',[['Metric',...data.companies.map(c=>c.ticker),'Comparable'],...data.rows.map(r=>[r.definition_id,...r.cells.map(c=>factValue(c)),r.comparable])])}>{t('Export reviewed comparison')}</button></>}</section>;
}
