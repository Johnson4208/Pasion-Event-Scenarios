import React,{useEffect,useState} from 'react';
import Dialog from './Dialog';
import {usePreferences} from './Preferences';
import './investment-research.scss';
import {factValue} from './FinancialFacts';

const valuationModels=[
 {name:'DCF',full:'Discounted Cash Flow',value:'78,400',change:'+26.2%',tone:'positive',badge:'Highest value',drivers:[['WACC','9.5%'],['Terminal growth','2.5%'],['Forecast period','5 years']]},
 {name:'P/E',full:'Price to Earnings',value:'71,200',change:'+14.7%',tone:'positive',drivers:[['TTM P/E','12.27×'],['Industry P/E','16.8×'],['EPS (TTM)','5,062 VND']]},
 {name:'DDM',full:'Dividend Discount',value:'65,400',change:'+5.3%',tone:'positive',drivers:[['Dividend yield','2.9%'],['Growth rate','6.0%'],['Cost of equity','9.5%']]},
 {name:'Gordon',full:'Gordon Growth Model',value:'69,800',change:'+12.4%',tone:'positive',drivers:[['Dividend (D1)','1,800 VND'],['Growth rate','6.0%'],['Cost of equity','9.5%']]},
 {name:'Asset-based',full:'Asset-based Valuation',value:'58,700',change:'−5.5%',tone:'negative',drivers:[['Book value/share','23,940 VND'],['Adjustments','+3.2%'],['P/B','2.65×']]},
];
const financialRows=[
 ['Revenue (TTM)','62.1T VND','48.7T VND','+27.4%','positive'],
 ['Net Profit (TTM)','9.8T VND','6.2T VND','+58.1%','positive'],
 ['Net Margin','15.8%','12.7%','+3.1pp','positive'],
 ['EBITDA Margin','21.4%','17.3%','+4.1pp','positive'],
 ['ROE','18.6%','14.2%','+4.4pp','positive'],
 ['ROA','12.7%','9.8%','+2.9pp','positive'],
 ['Debt / Equity','0.42','0.68','−38.2%','positive'],
 ['Current Ratio','1.56','1.28','+21.9%','positive'],
 ['Free Cash Flow (TTM)','7.31T VND','4.91T VND','+49.0%','positive'],
];
const summaryItems=[
 ['Profitability','Net margin 15.8% (vs. industry 12.7%)','Good','positive'],
 ['Growth','Revenue CAGR (3Y) 13.2%','Good','positive'],
 ['Valuation','Forward P/E 12.27× (vs. industry 16.8×)','Attractive','positive'],
 ['Dividends','Dividend yield 2.9%','Stable','neutral'],
 ['Financial Health','Debt / Equity 0.42 (vs. industry 0.68)','Healthy','positive'],
];
const navSections=[
 ['Overview','ir-summary'],['Valuation','ir-valuation'],['Financials','ir-financials'],
 ['Comparison','ir-comparison'],['News & Analysis','ir-health'],['Event Probability','ir-recommendation'],
];

function ValuationChart({models,current}){
 const values=models.map(model=>model.numeric),max=Math.max(1,...values.filter(Number.isFinite),Number.isFinite(current)?current:0)*1.2;
 const top=26,bottom=190,left=55,right=770,barW=34,gap=23,groupW=(right-left)/values.length;
 const y=value=>bottom-(value/max)*(bottom-top);
 return <svg className="ir-comparison-chart" viewBox="0 0 820 235" role="img" aria-label="Reviewed method estimates and verified quote, when available">
  {[0,.2,.4,.6,.8,1].map(ratio=><g key={ratio}><line x1={left} x2={right} y1={y(max*ratio)} y2={y(max*ratio)} className="ir-chart-grid"/><text x={left-9} y={y(max*ratio)+4} textAnchor="end" className="ir-chart-axis">{Number((max*ratio).toPrecision(3)).toLocaleString()}</text></g>)}
  {values.map((value,index)=>{const center=left+groupW*(index+.5);return <g key={models[index].name}>{Number.isFinite(value)&&value>=0&&<><rect x={center-gap/2-barW} y={y(value)} width={barW} height={bottom-y(value)} rx="5" className="ir-chart-bar-target"/><text x={center-gap/2-barW/2} y={y(value)-7} textAnchor="middle" className="ir-chart-value">{value.toLocaleString()}</text></>}{Number.isFinite(current)&&current>=0&&<rect x={center+gap/2} y={y(current)} width={barW} height={bottom-y(current)} rx="5" className="ir-chart-bar-current"/>}<text x={center} y={bottom+21} textAnchor="middle" className="ir-chart-model-label">{models[index].name}</text></g>})}
 </svg>;
}
function ValueModelCard({model,onDetails,t}){
 return <article className="ir-model-card">
  <header><span className="ir-model-icon" aria-hidden="true">{model.name==='DCF'?'D':model.name==='P/E'?'P/E':model.name==='DDM'?'◉':model.name==='Gordon'?'G':'▣'}</span><div><h4>{t(model.name)}</h4><p>{t(model.full)}</p></div><button type="button" onClick={()=>onDetails(model)}>{t('View details')} <span aria-hidden="true">→</span></button></header>
  <div className="ir-model-value"><strong>{model.value}</strong><span>{model.currency||''}</span>{model.badge&&<em>{t(model.badge)}</em>}</div>
  <span className={'ir-model-change '+model.tone}>{model.change}</span>
  <dl>{model.drivers.map(([label,value])=><div key={label}><dt>{t(label)}</dt><dd>{value}</dd></div>)}</dl>
 </article>;
}

export default function InvestmentResearch({storageKey='pasion',company}){
 const ticker=company?.ticker||'FPT';
 const {t}=usePreferences();
 const [facts,setFacts]=useState(null),[valuation,setValuation]=useState(null),[status,setStatus]=useState('Loading reviewed calculations');
 const [sec,setSec]=useState(null),[secStatus,setSecStatus]=useState(''),[secLoading,setSecLoading]=useState(false);
 useEffect(()=>{setSec(null);setSecStatus('');setFacts(null);setValuation(null);},[ticker]);
 useEffect(()=>{
  let active=true;const controller=new AbortController();
  setSecLoading(true);
  fetch('/api/research/sec/'+encodeURIComponent(ticker),{signal:controller.signal}).then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.reason_code||'SEC data unavailable');return d;}).then(d=>{if(active){setSec(d);setSecStatus('');}}).catch(e=>{if(active)setSecStatus(e.message);}).finally(()=>{if(active)setSecLoading(false);});
  return()=>{active=false;controller.abort();};
 },[ticker]);
 const canUseSec=(!facts||facts.status==='UNAVAILABLE')&&sec?.financials?.status==='READY';
 const displayedFacts=canUseSec?sec.financials:facts;
 const sourceLabel=canUseSec?sec.source_status:'ADMIN_REVIEWED_DATA';
 useEffect(()=>{
  let active=true;const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),12000);
  const read=async(response)=>{if(!response.ok)throw Error('Reviewed calculation service unavailable');const data=await response.json();if(data.version!==1)throw Error('Unsupported calculation contract');return data;};
  Promise.allSettled([fetch('/api/research/company/'+encodeURIComponent(ticker)+'?period=TTM',{signal:controller.signal}).then(read),fetch('/api/research/valuation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticker,scenario:'base',period:'TTM',valuation_date:new Date().toISOString().slice(0,10)}),signal:controller.signal}).then(read)]).then(results=>{
   if(!active)return;if(results[0].status==='fulfilled')setFacts(results[0].value);if(results[1].status==='fulfilled')setValuation(results[1].value);
   setStatus(results.every(r=>r.status==='fulfilled')?'Reviewed calculations; unavailable inputs remain withheld':'Reviewed calculation coverage incomplete; missing inputs are unavailable');
  }).finally(()=>clearTimeout(timeout));return()=>{active=false;clearTimeout(timeout);controller.abort();};
 },[ticker]);
 const metric=id=>factValue(displayedFacts?.metrics?.[id]);
 const currentPrice=valuation?.quote_gap?.status==='READY'?Number(valuation.quote_gap.price):null;
 const models=valuationModels.map(model=>{
  const row=valuation?.methods?.find(r=>r.method===({DCF:'FCFF','P/E':'P/E',DDM:'DDM',Gordon:'Gordon','Asset-based':'Asset-based'}[model.name]));
  const valid=row?.status==='READY'&&row.value!==null&&Number.isFinite(Number(row.value));
  const gap=valuation?.quote_gap?.status==='READY'?valuation.quote_gap.methods?.find(g=>g.method===row?.method&&g.status==='READY'):null;
  return {...model,value:valid?Number(row.value).toLocaleString():'Unavailable',numeric:valid?Number(row.value):null,currency:row?.currency?row.currency+'/share':'',badge:null,tone:gap&&Number(gap.value)<0?'negative':'neutral',change:gap?`${(Number(gap.value)*100).toFixed(1)}%`:(row?.status||'WITHHELD'),drivers:[['Status',row?.status||'WITHHELD'],['Reason',(row?.reason_codes||['REVIEWED_BASE_AND_ASSUMPTIONS_REQUIRED']).join(', ')],['Sources',(row?.source_ids||[]).join(', ')||'Unavailable'],['Calculation version',valuation?.calculation_version||'Unavailable']]};
 });
 const financialValues=['revenue','net_income','net_margin','ebitda_margin','roe','roa','debt_equity','current_ratio',null];
 const reviewedFinancialRows=financialRows.map((row,i)=>[row[0],financialValues[i]?metric(financialValues[i]):'Unavailable','Unavailable','Not comparable','neutral']);
 const reviewedSummary=summaryItems.map(([title],i)=>[title,[`Net margin: ${metric('net_margin')}`,displayedFacts?.quality?.diagnostics?.find(d=>d.definition_id==='revenue_growth')?.reason_codes?.join(', ')||'Comparable growth evidence unavailable','Eligible method results are shown individually','Reviewed dividend sustainability unavailable',`Debt / equity: ${metric('debt_equity')}`][i],'Review required','neutral']);
 const [activeSection,setActiveSection]=useState('Valuation');
 const [detail,setDetail]=useState(null);
 const savedKey=storageKey+'-research-saved-'+ticker;
 const [saved,setSaved]=useState(()=>{try{return localStorage.getItem(savedKey)==='true'}catch{return false}});
 useEffect(()=>{try{setSaved(localStorage.getItem(savedKey)==='true')}catch{setSaved(false)}},[savedKey]);
 function saveResearch(){setSaved(value=>{const next=!value;try{localStorage.setItem(savedKey,String(next))}catch{}return next})}
 function jumpTo([label,id]){setActiveSection(label);document.getElementById(id)?.scrollIntoView({behavior:'smooth',block:'start'})}
 return <div className="investment-research">
  <header className="ir-page-heading"><div><span className="eyebrow">{t('COMPANY VALUATION')}</span><h1>{t('Investment Research')}</h1><p>{t('Assess company value, financial strength, and the factors behind an investment decision.')}</p></div></header>
  <section className="ir-company-card" id="ir-summary" aria-label={t(ticker+' company snapshot')}>
   <div className="ir-company-overview">
    <div className="ir-company-identity"><span className="ir-company-logo" aria-hidden="true">{ticker.slice(0,3)}</span><div><h1>{company?.name||facts?.company?.name||ticker}</h1><div className="ir-company-tags"><b>{ticker}</b><b>{company?.country||'—'}</b><span aria-hidden="true">☆</span></div><p>{t(company?.sector||'Industry unavailable')} <i/> {t(company?.country||'Country unavailable')}</p></div></div>
    <div className="ir-quote"><strong>{Number.isFinite(currentPrice)?currentPrice.toLocaleString():'Unavailable'} <small>{valuation?.quote_gap?.status==='READY'?valuation.quote_gap.currency:''}</small></strong><span>{valuation?.quote_gap?.status||'UNAVAILABLE'}</span><em>{t('Verified quote required')}</em></div>
    <div className="ir-company-stat"><span>{t('Market Cap')}</span><strong>{metric('market_cap')}</strong></div>
    <div className="ir-company-stat"><span>{t('P/E (trailing)')}</span><strong>{metric('pe')}</strong></div>
    <div className="ir-company-stat"><span>{t('P/B')}</span><strong>{metric('pb')}</strong></div>
    <div className="ir-company-stat"><span>{t('Dividend Yield')}</span><strong>{metric('dividend_yield')}</strong></div>
    <button type="button" className={'ir-watch-button '+(saved?'is-saved':'')} aria-pressed={saved} onClick={saveResearch}><span aria-hidden="true">{saved?'✓':'☆'}</span>{t(saved?'Saved to research list':'Save research')}</button>
   </div>
   <nav className="ir-tabs" aria-label={t('Investment research sections')}>
    {navSections.map(item=><button type="button" key={item[0]} aria-pressed={activeSection===item[0]} className={activeSection===item[0]?'is-active':''} onClick={()=>jumpTo(item)}>{t(item[0])}</button>)}
   </nav>
   <div className="ir-disclosure"><span className="ir-disclosure-dot"/>{t(status)}{canUseSec&&<span> · FY {sec.period_end} · {sourceLabel} · NOT VERIFIED FOR VALUATION</span>}</div>
  </section>

  <section className="ir-top-grid" id="ir-valuation">
   <article className="ir-card ir-valuation-summary"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">◈</span><div><h2>{t('Valuation Summary')}</h2><p>{t('Each eligible method retains its own assumptions and evidence.')}</p></div></header>
    <div className="ir-valuation-highlight"><span>{t('Reviewed valuation')}</span><div className="ir-fair-value"><strong>{t('Method-specific')}</strong><small>{valuation?.status||'WITHHELD'}</small><b>{t('No consensus')}</b></div><p>{t('Verified quote')} <strong>{Number.isFinite(currentPrice)?`${currentPrice.toLocaleString()} ${valuation.quote_gap.currency}`:'Unavailable'}</strong></p><small className="ir-range-caption">{t('No average of correlated methods')}</small></div>
    <div className="ir-recommendation-box"><span>{t('Model signal')}</span><strong className="ir-buy-label">{t('Review required')}</strong><dl><div><dt>{t('Target Price Range')}</dt><dd>{t('Unavailable')}</dd></div><div><dt>{t('Validated holding period')}</dt><dd>{t('Unavailable')}</dd></div></dl></div>
   </article>
   <article className="ir-card ir-chart-card" id="ir-comparison"><header className="ir-section-heading"><div><h2>{t('Valuation Comparison')}</h2><p>{t('Eligible method results; missing values are not plotted')}</p></div><div className="ir-chart-legend"><span><i className="is-current"/>{t('Current Price')}</span><span><i className="is-target"/>{t('Target Price')}</span></div></header><ValuationChart models={models} current={currentPrice}/></article>
  </section>

  <section className="ir-model-section">
   <header className="ir-section-heading ir-section-title"><span className="ir-heading-icon" aria-hidden="true">◫</span><div><h2>{t('Valuation Models')}</h2><p>{t('Existing methods connected to reviewed valuation eligibility')}</p></div><span className="ir-model-count">{t('5 models')}</span></header>
   <div className="ir-model-grid">{models.map(model=><ValueModelCard key={model.name} model={model} onDetails={setDetail} t={t}/>)}</div>
  </section>

  <section className="ir-bottom-grid">
   <article className="ir-card ir-financial-card" id="ir-financials"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">▤</span><div><h2>{t('Key Financial Indicators')}</h2><p>{t('Reviewed TTM metrics; peer comparison requires compatible sources')}</p></div></header>
    <div className="ir-table-scroll"><table className="ir-financial-table"><thead><tr><th>{t('Metric')}</th><th>{t('Value')}</th><th>{t('Industry Avg.')}</th><th>{t('vs. Industry')}</th></tr></thead><tbody>{reviewedFinancialRows.map(([metric,value,average,delta,tone])=><tr key={metric}><th scope="row">{t(metric)}</th><td>{value}</td><td>{average}</td><td className={tone}>{delta}</td></tr>)}</tbody></table></div>
   </article>
   <article className="ir-card ir-health-card" id="ir-health"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">◉</span><div><h2>{t('Financial Health Assessment')}</h2><p>{t('Reason-coded diagnostics; no invented health score')}</p></div><span className="ir-health-state">● {t('Unavailable')} <b>→</b></span></header>
    <div className="ir-health-content"><div className="ir-health-gauge" role="img" aria-label={t('Health score unavailable')} style={{background:'var(--pref-soft)'}}><div><strong>{t('Unavailable')}</strong><span>{t('Overall Score')}</span></div></div><ul className="ir-health-checks">{(displayedFacts?.quality?.flags?.length?displayedFacts.quality.flags.map(flag=>flag.interpretation):['Reviewed health diagnostics incomplete']).map(text=><li key={text}><span>✓</span>{t(text)}</li>)}</ul></div>
    <aside className="ir-key-insight"><span aria-hidden="true">♧</span><div><strong>{t('Key Insight')}</strong><p>{t(displayedFacts?.quality?.health_heuristic?.reason_codes?.join(', ')||'Reviewed inputs and normalized health policy are required; no score is inferred from missing facts.')}</p></div></aside>
   </article>
   <article className="ir-card ir-summary-card"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">✥</span><div><h2>{t('Summary')}</h2><p>{t('Key metrics and research context')}</p></div></header>
    <div className="ir-summary-list">{reviewedSummary.map(([title,description,status,tone])=><div className="ir-summary-row" key={title}><span className="ir-summary-icon" aria-hidden="true">{title==='Profitability'?'◉':title==='Growth'?'↗':title==='Valuation'?'▣':title==='Dividends'?'♧':'⬡'}</span><div><strong>{t(title)}</strong><p>{t(description)}</p></div><span className={'ir-summary-status '+tone}>{t(status)}</span></div>)}</div>
   </article>
  </section>

  <section className="ir-final-recommendation" id="ir-recommendation"><span className="ir-heading-icon" aria-hidden="true">◈</span><div><h2>{t('Research conclusion')}</h2><p>{t('Review the eligible method results and source assumptions. No automatic BUY recommendation or combined fair value is generated.')}</p><small>{t('Target range and holding period unavailable without an eligible method policy.')}</small></div><button type="button" onClick={()=>setDetail({name:'Research report',full:ticker+' reviewed calculation status',drivers:[['Status',status],['Calculation version',valuation?.calculation_version||'Unavailable'],['Run',valuation?.run_id||'Unavailable'],['Sources',(valuation?.source_ids||[]).join(', ')||'Unavailable']]})}>{t('View detailed report')} <span aria-hidden="true">→</span></button></section>
  <section className="ir-card" aria-label="Financial filing evidence" style={{padding:18,marginBlock:16}}>
   <header className="ir-section-heading"><div><h2>Financial filing source</h2><p>{secLoading?'Checking SEC XBRL filings…':canUseSec?"Financial indicators above use the selected company's fiscal-year SEC filing. These machine-read figures have not been human-reviewed.":(secStatus||'Financial figures require an accepted filing or eligible SEC XBRL data.')}</p></div></header>
   {sec&&<p>{sec.issuer} · FY {sec.period_end} · {sec.source_status} · <a href={sec.filing_url} target="_blank" rel="noopener noreferrer">SEC filing ↗</a></p>}
   <p>Valuation models use separately accepted issuer facts and reviewed assumptions. SEC machine-read observations never automatically authorize a fair-value estimate.</p>
   {canUseSec&&<details><summary>Financial fact definitions and source tags</summary>{Object.entries(sec.source_details||{}).map(([key,rows])=><p key={key}><strong>{key}:</strong> {rows.map(r=>r.tag).join(', ')}</p>)}</details>}
  </section>
  <footer className="ir-page-footnote">{t('Reviewed calculations populate the existing cards. Missing source facts, assumptions, quotes and peer coverage remain unavailable.')}</footer>

  {detail&&<Dialog title={t(detail.full||detail.name)} onClose={()=>setDetail(null)} className="ir-detail-dialog"><p className="ir-detail-description">{t(status)}</p>{detail.drivers&&<dl>{detail.drivers.map(([label,value])=><div key={label}><dt>{t(label)}</dt><dd>{value}</dd></div>)}</dl>}<p>{t('Model values are sensitive to growth, discount rates, financial statement quality, and market conditions. Review source documents and update the assumptions before using this analysis.')}</p><button type="button" className="ir-dialog-close" onClick={()=>setDetail(null)}>{t('Close')}</button></Dialog>}
 </div>;
}
