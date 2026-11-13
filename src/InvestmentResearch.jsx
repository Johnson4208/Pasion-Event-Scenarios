import React,{useEffect,useState} from 'react';
import Dialog from './Dialog';
import {usePreferences} from './Preferences';
import './investment-research.scss';
import FinancialSources from './FinancialSources';
import ResearchCompanySearch,{companyMarket} from './ResearchCompanySearch';
import {chooseMetric,formatFinancial,missingReason,usable} from './automaticFinancials';

const valuationModels=[
 {name:'DCF',full:'Discounted Cash Flow'},
 {name:'P/E',full:'Price to Earnings'},
 {name:'DDM',full:'Dividend Discount'},
 {name:'Gordon',full:'Gordon Growth Model'},
 {name:'Asset-based',full:'Asset-based Valuation'},
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

export default function InvestmentResearch(props){return <><ResearchCompanySearch key={companyMarket(props.company)} company={props.company} query={props.query} onQuery={props.onQuery} onChoose={props.onChoose}/><InvestmentResearchBody key={companyMarket(props.company)+':'+(props.company?.ticker||'FPT')} {...props}/></>;}

function InvestmentResearchBody({storageKey='pasion',company}){
 const ticker=company?.ticker||'FPT';
 const {t,language}=usePreferences();const vi=language==='vi';const text=(en,vn)=>vi?vn:en;
 const market=companyMarket(company);
 const [refresh,setRefresh]=useState(0);
 const [facts,setFacts]=useState(null),[valuation,setValuation]=useState(null),[status,setStatus]=useState('Loading reviewed calculations');
 const [snapshot,setSnapshot]=useState(null),[sourceError,setSourceError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{
  let active=true;const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),60000);
  setLoading(true);setSourceError('');setSnapshot(null);
  fetch('/api/research/financials/'+encodeURIComponent(ticker)+'?market='+market+(refresh?'&refresh=1':''),{signal:controller.signal})
   .then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.reason_code||'PUBLIC_FINANCIALS_UNAVAILABLE');if(d.version!==1||d.ticker!==ticker.toUpperCase()||d.market!==market)throw Error('PROVIDER_ENTITY_MISMATCH');return d;})
   .then(d=>{if(active){setSnapshot(d);setSourceError(d.refresh_error||'');}})
   .catch(e=>{if(active)setSourceError(e.name==='AbortError'?'Request timed out':e.message);})
   .finally(()=>{clearTimeout(timer);if(active)setLoading(false);});
  return()=>{active=false;clearTimeout(timer);controller.abort();};
 },[ticker,market,refresh]);
 const selectedMetric=id=>chooseMetric(id,facts,snapshot);
 const metric=id=>formatFinancial(selectedMetric(id),language);
 useEffect(()=>{
  let active=true;const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),12000);
  const read=async(response)=>{if(!response.ok)throw Error('Reviewed calculation service unavailable');const data=await response.json();if(data.version!==1)throw Error('Unsupported calculation contract');return data;};
  Promise.allSettled([fetch('/api/research/company/'+encodeURIComponent(ticker)+'?period=TTM',{signal:controller.signal}).then(read),fetch('/api/research/valuation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticker,scenario:'base',period:'TTM',valuation_date:new Date().toISOString().slice(0,10)}),signal:controller.signal}).then(read)]).then(results=>{
   if(!active)return;if(results[0].status==='fulfilled')setFacts(results[0].value);if(results[1].status==='fulfilled')setValuation(results[1].value);
   setStatus(results.every(r=>r.status==='fulfilled')?'Reviewed calculations; unavailable inputs remain withheld':'Reviewed calculation coverage incomplete; missing inputs are unavailable');
  }).finally(()=>clearTimeout(timeout));return()=>{active=false;clearTimeout(timeout);controller.abort();};
 },[ticker]);
 const currentPrice=valuation?.quote_gap?.status==='READY'?Number(valuation.quote_gap.price):null;
 const publicQuote=snapshot?.cache_status!=='STALE'&&snapshot?.quote?.status==='READY'?snapshot.quote:null;
 const displayPrice=currentPrice??(publicQuote?Number(publicQuote.price):null);
 const models=valuationModels.map(model=>{
  const row=valuation?.methods?.find(r=>r.method===({DCF:'FCFF','P/E':'P/E',DDM:'DDM',Gordon:'Gordon','Asset-based':'Asset-based'}[model.name]));
  const valid=row?.status==='READY'&&row.value!==null&&Number.isFinite(Number(row.value));
  const gap=valuation?.quote_gap?.status==='READY'?valuation.quote_gap.methods?.find(g=>g.method===row?.method&&g.status==='READY'):null;
  return {...model,value:valid?Number(row.value).toLocaleString():'Unavailable',numeric:valid?Number(row.value):null,currency:row?.currency?row.currency+'/share':'',badge:null,tone:gap&&Number(gap.value)<0?'negative':'neutral',change:gap?`${(Number(gap.value)*100).toFixed(1)}%`:(row?.status||'WITHHELD'),drivers:[['Status',row?.status||'WITHHELD'],['Reason',valid?text('Calculated from reviewed inputs','Tính từ đầu vào đã duyệt'):text('Add reviewed model assumptions and compatible financial inputs.','Cần giả định mô hình và đầu vào tài chính phù hợp đã duyệt.')],['Sources',(row?.source_ids||[]).join(', ')||'Unavailable'],['Calculation version',valuation?.calculation_version||'Unavailable']]};
 });
 const financialDefinitions=[['Revenue','revenue'],['Net Profit','net_income'],['Net Margin','net_margin'],['EBITDA Margin','ebitda_margin'],['ROE','roe'],['ROA','roa'],['Debt / Equity','debt_equity'],['Current Ratio','current_ratio'],['Free Cash Flow','free_cash_flow']];
 const readyCount=financialDefinitions.filter(([,id])=>usable(selectedMetric(id))).length;
 const reviewedSummary=[
  ['Profitability',`${text('Net margin','Biên lợi nhuận')}: ${metric('net_margin')}`,usable(selectedMetric('net_margin'))],
  ['Growth',`${text('Revenue growth (FY)','Tăng trưởng doanh thu năm')}: ${metric('revenue_growth')}`,usable(selectedMetric('revenue_growth'))],
  ['Valuation',text('Add model assumptions to calculate fair value.','Cần thêm giả định mô hình để tính giá trị hợp lý.'),false],
  ['Dividends',text('Dividend sustainability needs cash-flow and payout evidence.','Cần số liệu dòng tiền và chi trả để đánh giá cổ tức.'),false],
  ['Financial Health',`${text('Debt / equity','Nợ vay / Vốn chủ')}: ${metric('debt_equity')} · ${text('Current ratio','Thanh toán hiện hành')}: ${metric('current_ratio')}`,usable(selectedMetric('debt_equity'))],
 ];
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
    <div className="ir-company-identity"><span className="ir-company-logo" aria-hidden="true">{ticker.slice(0,3)}</span><div><h1>{snapshot?.issuer||company?.name||facts?.company?.name||ticker}</h1><div className="ir-company-tags"><b>{ticker}</b><b>{company?.country||'—'}</b><span aria-hidden="true">☆</span></div><p>{t(company?.sector||'Industry unavailable')} <i/> {t(company?.country||'Country unavailable')}</p></div></div>
    <div className="ir-quote"><strong>{Number.isFinite(displayPrice)?displayPrice.toLocaleString():text('Unavailable','Chưa có giá')} <small>{valuation?.quote_gap?.status==='READY'?valuation.quote_gap.currency:publicQuote?.currency||''}</small></strong><span>{currentPrice!==null?text('Reviewed quote','Giá đã duyệt'):publicQuote?'CafeF · '+new Date(publicQuote.as_of).toLocaleString(vi?'vi-VN':'en-US'):text('Price source required','Cần nguồn giá')}</span><em>{publicQuote&&currentPrice===null?text('Provider snapshot','Ảnh chụp dữ liệu nguồn'):t('Verified quote required')}</em></div>
    <div className="ir-company-stat"><span>{t('Market Cap')}</span><strong>{metric('market_cap')}</strong></div>
    <div className="ir-company-stat"><span>{t('P/E (trailing)')}</span><strong>{metric('pe')}</strong></div>
    <div className="ir-company-stat"><span>{t('P/B')}</span><strong>{metric('pb')}</strong></div>
    <div className="ir-company-stat"><span>{text('EPS (report period)','EPS (kỳ báo cáo)')}</span><strong>{metric('eps')}</strong></div>
    <button type="button" className={'ir-watch-button '+(saved?'is-saved':'')} aria-pressed={saved} onClick={saveResearch}><span aria-hidden="true">{saved?'✓':'☆'}</span>{t(saved?'Saved to research list':'Save research')}</button>
   </div>
   <nav className="ir-tabs" aria-label={t('Investment research sections')}>
    {navSections.map(item=><button type="button" key={item[0]} aria-pressed={activeSection===item[0]} className={activeSection===item[0]?'is-active':''} onClick={()=>jumpTo(item)}>{t(item[0])}</button>)}
   </nav>
   <div className="ir-disclosure"><span className="ir-disclosure-dot"/>{loading?text('Loading public financial statements…','Đang tải báo cáo tài chính công khai…'):text(`${readyCount} of 9 financial indicators available`,`${readyCount}/9 chỉ tiêu tài chính đã có dữ liệu`)}</div>
  </section>

  <FinancialSources market={market} snapshot={snapshot} loading={loading} error={sourceError} onRefresh={()=>setRefresh(v=>v+1)}/>

  <section className="ir-bottom-grid">
   <article className="ir-card ir-financial-card" id="ir-financials"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">▤</span><div><h2>{t('Key Financial Indicators')}</h2><p>{text('Automatically populated · period and source shown per metric','Tự động điền số liệu · kỳ báo cáo và nguồn theo từng chỉ tiêu')}</p></div></header>
    <div className="ir-table-scroll"><table className="ir-financial-table" aria-busy={loading}><thead><tr><th>{t('Metric')}</th><th>{t('Value')}</th><th>{text('Period','Kỳ')}</th><th>{text('Source','Nguồn')}</th></tr></thead><tbody>{financialDefinitions.map(([label,id])=>{const fact=selectedMetric(id),ready=usable(fact);return <tr key={id}><th scope="row">{t(label)}</th><td className="ir-financial-value">{ready?formatFinancial(fact,language):loading?text('Loading…','Đang tải…'):'—'}{!ready&&!loading&&<small>{missingReason(fact,vi)}</small>}</td><td>{ready?(fact.period_label||fact.period_type||'TTM'):'—'}</td><td>{ready&&fact.source_url?<a href={fact.source_url} title={fact.formula||text('View source','Xem nguồn')} target="_blank" rel="noopener noreferrer">{fact.provider||snapshot?.provider} ↗</a>:ready?(fact.provider||text('Reviewed','Đã duyệt')):'—'}</td></tr>;})}</tbody></table></div>

   </article>
   <article className="ir-card ir-health-card" id="ir-health"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">◉</span><div><h2>{t('Financial Health Assessment')}</h2><p>{t('Reason-coded diagnostics; no invented health score')}</p></div><span className="ir-health-state">{text('Source data','Số liệu nguồn')}</span></header>
    <div className="ir-health-content"><div className="ir-health-gauge" role="img" aria-label={text('Financial data coverage','Mức độ đầy đủ dữ liệu')} style={{background:'var(--pref-soft)'}}><div><strong>{readyCount}/9</strong><span>{text('Indicators loaded','Chỉ tiêu đã tải')}</span></div></div><ul className="ir-health-checks">{[['ROE','roe'],['ROA','roa'],[text('Current ratio','Thanh toán hiện hành'),'current_ratio']].map(([label,id])=><li key={id}>{label}: <strong>{metric(id)}</strong></li>)}</ul></div>
    <aside className="ir-key-insight"><span aria-hidden="true">♧</span><div><strong>{text('Data coverage','Mức độ đầy đủ dữ liệu')}</strong><p>{text('This count measures data availability, not financial health. Open each source to check the figures.','Số lượng trên thể hiện dữ liệu hiện có, không phải điểm sức khỏe tài chính. Mở nguồn để đối chiếu số liệu.')}</p></div></aside>

   </article>
   <article className="ir-card ir-summary-card"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">✥</span><div><h2>{t('Summary')}</h2><p>{t('Key metrics and research context')}</p></div></header>
    <div className="ir-summary-list">{reviewedSummary.map(([title,description,ready])=><div className="ir-summary-row" key={title}><span className="ir-summary-icon" aria-hidden="true">{title==='Profitability'?'◉':title==='Growth'?'↗':title==='Valuation'?'▣':title==='Dividends'?'♧':'⬡'}</span><div><strong>{t(title)}</strong><p>{t(description)}</p></div><span className={'ir-summary-status '+(ready?'positive':'neutral')}>{ready?text('Available','Đã có'):text('Needs inputs','Cần đầu vào')}</span></div>)}</div>
   </article>
  </section>


  <section className="ir-top-grid" id="ir-valuation">
   <article className="ir-card ir-valuation-summary"><header className="ir-section-heading"><span className="ir-heading-icon" aria-hidden="true">◈</span><div><h2>{t('Valuation Summary')}</h2><p>{t('Each eligible method retains its own assumptions and evidence.')}</p></div></header>
    <div className="ir-valuation-highlight"><span>{t('Reviewed valuation')}</span><div className="ir-fair-value"><strong>{t('Method-specific')}</strong><small>{valuation?.status||'WITHHELD'}</small><b>{t('No consensus')}</b></div><p>{t('Verified quote')} <strong>{Number.isFinite(currentPrice)?`${currentPrice.toLocaleString()} ${valuation.quote_gap.currency}`:'Unavailable'}</strong></p><small className="ir-range-caption">{t('No average of correlated methods')}</small></div>
    <div className="ir-recommendation-box"><span>{t('Model signal')}</span><strong className="ir-buy-label">{t('Review required')}</strong><dl><div><dt>{t('Target Price Range')}</dt><dd>{t('Unavailable')}</dd></div><div><dt>{t('Validated holding period')}</dt><dd>{t('Unavailable')}</dd></div></dl></div>
   </article>
   <article className="ir-card ir-chart-card" id="ir-comparison"><header className="ir-section-heading"><div><h2>{t('Valuation Comparison')}</h2><p>{t('Eligible method results; missing values are not plotted')}</p></div><div className="ir-chart-legend"><span><i className="is-current"/>{t('Current Price')}</span><span><i className="is-target"/>{t('Target Price')}</span></div></header><ValuationChart models={models} current={currentPrice}/></article>
  </section>

  <section className="ir-model-section">
   <header className="ir-section-heading ir-section-title"><span className="ir-heading-icon" aria-hidden="true">◫</span><div><h2>{t('Valuation Models')}</h2><p>{text('Financial data loads automatically. These estimates also need growth, discount rates and other model inputs.','Số liệu tài chính tự tải. Các ước tính này còn cần tăng trưởng, tỷ lệ chiết khấu và đầu vào mô hình.')}</p></div><span className="ir-model-count">{t('5 models')}</span></header>
   <div className="ir-model-grid">{models.map(model=><ValueModelCard key={model.name} model={model} onDetails={setDetail} t={t}/>)}</div>
  </section>


  <section className="ir-final-recommendation" id="ir-recommendation"><span className="ir-heading-icon" aria-hidden="true">◈</span><div><h2>{t('Research conclusion')}</h2><p>{t('Review the eligible method results and source assumptions. No automatic BUY recommendation or combined fair value is generated.')}</p><small>{t('Target range and holding period unavailable without an eligible method policy.')}</small></div><button type="button" onClick={()=>setDetail({name:'Research report',full:ticker+' reviewed calculation status',drivers:[['Status',status],['Calculation version',valuation?.calculation_version||'Unavailable'],['Run',valuation?.run_id||'Unavailable'],['Sources',(valuation?.source_ids||[]).join(', ')||'Unavailable']]})}>{t('View detailed report')} <span aria-hidden="true">→</span></button></section>
  <footer className="ir-page-footnote">{text('Statements populate financial indicators automatically. Valuation models require additional assumptions; missing inputs are explained per metric.','Báo cáo tài chính tự điền các chỉ tiêu. Mô hình định giá cần thêm giả định; chỉ tiêu thiếu dữ liệu có ghi rõ lý do.')}</footer>

  {detail&&<Dialog title={t(detail.full||detail.name)} onClose={()=>setDetail(null)} className="ir-detail-dialog"><p className="ir-detail-description">{t(status)}</p>{detail.drivers&&<dl>{detail.drivers.map(([label,value])=><div key={label}><dt>{t(label)}</dt><dd>{value}</dd></div>)}</dl>}<p>{t('Model values are sensitive to growth, discount rates, financial statement quality, and market conditions. Review source documents and update the assumptions before using this analysis.')}</p><button type="button" className="ir-dialog-close" onClick={()=>setDetail(null)}>{t('Close')}</button></Dialog>}
 </div>;
}

