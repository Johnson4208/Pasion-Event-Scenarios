import React, {useEffect, useState} from 'react';
import {companies, percent} from './marketData';
import {usePreferences} from './Preferences';
import './company-news.scss';


export const newsLayouts=['Morning Edition','Three-Desk Newsroom','Reading Focus','Signal Timeline','Topic Library'];

const storyImages=['macro','economy','energy','technology'];
const EMPTY=[];
const text=value=>typeof value==='string'?value:'';

function normalizeFeed(data){
 if(!data||data.version!==1||!Array.isArray(data.articles))throw Error('The news library returned an invalid response. Try again.');
 const ids=new Set();
 const normalized=data.articles.map(article=>{
  if(!article||typeof article!=='object'||typeof article.id!=='string'||!article.id.trim()||ids.has(article.id)||typeof article.title!=='string'||!article.title.trim()||!Number.isFinite(Date.parse(article.published_at)))throw Error('The news library returned an invalid response. Try again.');
  ids.add(article.id);
  let source;
  try{source=new URL(article.url);if(source.protocol!=='https:'||source.username||source.password)throw Error();}
  catch{throw Error('The news library returned an invalid response. Try again.');}
  return {...article,url:source.href,summary:text(article.summary),category:text(article.category)||'Research',provider:text(article.provider)||text(article.source),
   tickers:Array.isArray(article.tickers)?article.tickers.filter(value=>typeof value==='string'):[],
   claims:Array.isArray(article.claims)?article.claims.filter(claim=>claim&&typeof claim==='object'):[]};
 });
 return {...data,articles:normalized,bookmarks:Array.isArray(data.bookmarks)?data.bookmarks.filter(id=>typeof id==='string'):[],
  coverage:Array.isArray(data.coverage)?data.coverage.filter(provider=>provider&&typeof provider==='object').map(provider=>({id:text(provider.id),name:text(provider.name),status:text(provider.status),last_known_at:text(provider.last_known_at)})):[]};
}

export function Newsroom(props){
 const [feed,setFeed]=useState(null),[state,setState]=useState('LOADING'),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 useEffect(()=>{
  let active=true;const controller=new AbortController();
  setState('LOADING');setError('');setFeed(null);
  const timeout=setTimeout(()=>controller.abort(),20000);
  fetch('/api/research/news',{credentials:'same-origin',signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error(response.status===401?'Sign in again to load your stored news.':response.status===403?'Your account cannot access this news library.':'Stored news is temporarily unavailable. Try again.');
   let data;try{data=await response.json();}catch{throw Error('The news library returned an invalid response. Try again.');}
   return normalizeFeed(data);
  }).then(data=>{if(active){setFeed(data);setState('READY');}}).catch(failure=>{
   if(active){setError(failure.name==='AbortError'?'The news library request timed out. Try again.':failure instanceof TypeError?'Could not connect to the stored news library. Try again.':failure.message);setState('FAILED');}
  }).finally(()=>clearTimeout(timeout));
  return()=>{active=false;clearTimeout(timeout);controller.abort();};
 },[attempt]);
 const stories=(feed?.articles||[]).map(article=>({...article,body:[article.summary,`Published ${article.published_at}; known ${article.known_at}; source ${article.provider||article.source||'Unavailable'}`,...(article.claims||[]).map(claim=>`${claim.statement||claim.text||''}: ${claim.status||claim.evidence_status||'INSUFFICIENT'}`)].join(' | '),time:new Date(article.published_at).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'}),category:article.category||'Research'}));
 return <SampleNewsroom {...props} reviewedArticles={stories} reviewedBookmarks={feed?.bookmarks||EMPTY} collectionState={state} collectionError={error} feedCoverage={feed?.coverage||EMPTY} onRetry={()=>setAttempt(value=>value+1)}/>;
}

function SampleNewsroom({variant=0,query='',onArticle,storageKey,watched=[],onCompany,onClearSearch,reviewedArticles=[],reviewedBookmarks=EMPTY,collectionState='LOADING',collectionError='',feedCoverage=EMPTY,onRetry}){
 const articles=reviewedArticles;
 const relatedTickers=Object.fromEntries(articles.map(article=>[article.id,article.tickers||[]]));
 const {t}=usePreferences();
 const ready=collectionState==='READY';
 const [topic,setTopic]=useState('All');
 const [companyFilter,setCompanyFilter]=useState('All companies');
 const [sortBy,setSortBy]=useState('latest');
 const [saved,setSaved]=useState(()=>{
  try{const value=JSON.parse(localStorage.getItem(storageKey+'-news'));return Array.isArray(value)?value:[]}
  catch{return []}
 });
 const [onlySaved,setOnlySaved]=useState(false);
 useEffect(()=>setSaved(reviewedBookmarks),[reviewedBookmarks]);
 const [saveError,setSaveError]=useState('');

 useEffect(()=>{
  try{localStorage.setItem(storageKey+'-news',JSON.stringify(saved));setSaveError('')}
  catch{setSaveError('Bookmarks could not be saved on this browser.')}
 },[saved,storageKey]);

 const topicOptions=['All',...new Set(articles.map(article=>article.category))];
 const allRelatedTickers=[...new Set(Object.values(relatedTickers).flat())];
 const companyOptions=companies.filter(company=>allRelatedTickers.includes(company.ticker));
 const stories=articles
  .filter(article=>(topic==='All'||article.category===topic)
   &&(!onlySaved||saved.includes(article.id))
   &&(companyFilter==='All companies'||relatedTickers[article.id]?.includes(companyFilter))
   &&(`${article.title} ${article.summary} ${article.body}`).toLowerCase().includes(query.toLowerCase()))
  .sort((a,b)=>sortBy==='topic'
   ?a.category.localeCompare(b.category)||Date.parse(b.published_at)-Date.parse(a.published_at)
   :Date.parse(b.published_at)-Date.parse(a.published_at));
 const savedStories=articles.filter(article=>saved.includes(article.id));
 const toggleSaved=async article=>{const next=!saved.includes(article.id);try{const response=await fetch('/api/research/news/bookmarks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({article_id:article.id,saved:next})});if(!response.ok)throw Error();setSaved(current=>next?[...current,article.id]:current.filter(id=>id!==article.id));setSaveError('');}catch{setSaveError('Bookmark service unavailable');}};
 const clearFilters=()=>{setTopic('All');setCompanyFilter('All companies');setSortBy('latest');setOnlySaved(false);onClearSearch?.()};

 function storyCard(article,index){
  const related=(relatedTickers[article.id]||[]).map(ticker=>companies.find(company=>company.ticker===ticker)).filter(Boolean);
  return <article key={article.id} className={'editorial-card company-news-card '+(index===0?'lead-story':'')}>
   <div className="editorial-image company-news-image" style={{backgroundImage:`url(/news/${storyImages[article.id-1]||'macro'}.jpg)`}}>
    <span className="category-pill">{t(article.category)}</span>
    {index===0&&<span className="company-news-featured">{t('From the news library')}</span>}
    <button type="button" aria-label={t(saved.includes(article.id)?'Unsave {title}':'Save {title}',{title:article.title})} aria-pressed={saved.includes(article.id)} onClick={()=>toggleSaved(article)}>{saved.includes(article.id)?'★':'☆'}</button>
   </div>
   <div className="company-news-story-content">
    <div className="company-news-story-meta"><span>{t(article.category+' briefing')}</span><time dateTime={article.published_at}>{article.time}</time><span>{t('Stored source article')}</span></div>
    <button type="button" className="news-article company-news-open" onClick={()=>onArticle(article)}>
     <h3>{article.title}</h3><p>{article.summary}</p><b>{t('Read briefing')} <span aria-hidden="true">→</span></b>
    </button>
    <div className="company-news-lenses"><span>{t('Companies in context')}</span><div>{related.map(company=><button type="button" key={company.ticker} onClick={()=>onCompany?.(company)} aria-label={t('Explore {ticker}',{ticker:company.ticker})}><strong>{company.ticker}</strong><span className={company.change<0?'is-negative':'is-positive'}>{percent(company.change)}</span></button>)}</div></div>
   </div>
  </article>;
 }

 return <section className={'newsroom newsroom-'+variant+' company-news'}>
  <header className="company-news-masthead">
   <div><span className="eyebrow">{t('COMPANY & MARKET BRIEFINGS')}</span><h2>{t(newsLayouts[variant]||newsLayouts[0])}</h2><p>{t('Follow the stories behind your companies and the markets around them.')}</p></div>
   <div className="company-news-head-actions"><span className="company-news-sample"><i/>{t(ready?'Stored-source reporting':collectionState==='LOADING'?'Loading stored news…':'News library unavailable')}</span><button type="button" className="company-news-save-toggle" disabled={!ready} aria-pressed={onlySaved} onClick={()=>setOnlySaved(value=>!value)}><span aria-hidden="true">☆</span>{t('Saved')} <b>{ready?saved.length:'—'}</b></button></div>
  </header>

  <div className="company-news-context" aria-label={t('Newsroom overview')}>
   <div><span>{t('Briefings')}</span><strong>{ready?articles.length:'—'}</strong><small>{t('Loaded from the news library')}</small></div>
   <div><span>{t('Topic desks')}</span><strong>{ready?topicOptions.length-1:'—'}</strong><small>{t('Across stored reporting')}</small></div>
   <div><span>{t('Saved by you')}</span><strong>{ready?saved.length:'—'}</strong><small>{t('Saved article bookmarks')}</small></div>
   <div className="company-news-context-note"><span className="company-news-spark" aria-hidden="true">✳</span><p>{t('Stored reporting retains its publication dates. An article is not automatically a verified claim or a probability forecast.')}</p></div>
  </div>

  <section className="company-news-collection" aria-label={t('News collection status')} aria-busy={collectionState==='LOADING'}>
   {collectionState==='LOADING'?<p role="status">{t('Loading stored news…')}</p>:collectionState==='FAILED'?<><p role="alert">{t(collectionError)}</p><p>{t('The article count is unknown until the library loads successfully.')}</p><button type="button" onClick={onRetry}>{t('Retry loading news')}</button></>:<>
    <h3>{t('News collection status')}</h3>
    <p>{t('{count} stored articles loaded',{count:articles.length})}{articles.length>=200&&<> · {t('Showing up to 200 available articles.')}</>}</p>
    <p>{t('Registered sources require article ingestion; opening this page does not start an automatic collector.')}</p>
    {!feedCoverage.length?<p>{t('No permitted feeds registered in this news library.')}</p>:<details><summary>{t('{count} registered news sources',{count:feedCoverage.length})}</summary><ul>{feedCoverage.map((provider,index)=><li key={provider.id||index}><strong>{provider.name||t('Source unavailable')}</strong><span>{t(provider.status==='READY'?'Recent accepted arrival':provider.status==='GAP'?'No recent accepted arrival':'Collection status unavailable')}</span>{provider.last_known_at&&Number.isFinite(Date.parse(provider.last_known_at))&&<time dateTime={provider.last_known_at}>{new Date(provider.last_known_at).toLocaleString()}</time>}</li>)}</ul></details>}
    {!articles.length&&<p>{t('If this library previously contained articles, recover the data from the older project. A source-only download does not contain your saved news.')}</p>}
   </>}
  </section>

  <div className="company-news-controls">
   <div className="company-news-topics" role="group" aria-label={t('Filter stories by topic')}>
    {topicOptions.map(option=><button type="button" key={option} aria-pressed={topic===option} onClick={()=>setTopic(option)}>{t(option)}{option==='All'&&<span>{articles.length}</span>}</button>)}
   </div>
   <div className="company-news-filters">
    <label><span>{t('Company')}</span><select aria-label={t('Filter by company')} value={companyFilter} onChange={event=>setCompanyFilter(event.target.value)}><option value="All companies">{t('All companies')}</option>{companyOptions.map(company=><option value={company.ticker} key={company.ticker}>{company.ticker} · {company.name}</option>)}</select></label>
    <label><span>{t('Sort')}</span><select aria-label={t('Sort stories')} value={sortBy} onChange={event=>setSortBy(event.target.value)}><option value="latest">{t('Latest first')}</option><option value="topic">{t('Topic')}</option></select></label>
    <button type="button" className="company-news-clear" onClick={clearFilters}>{t('Clear filters')}</button>
   </div>
  </div>
  {saveError&&<p role="alert" className="company-news-error">{t(saveError)}</p>}
  {variant===4&&<div className="topic-library company-news-topic-library">{topicOptions.filter(option=>option!=='All').map(option=><button type="button" key={option} onClick={()=>{setTopic(option);setOnlySaved(false)}}><strong>{t(option)}</strong><span>{t('{count} briefings →',{count:articles.filter(article=>article.category===option).length})}</span></button>)}</div>}

  <div className="company-news-layout">
   <div className="company-news-main">
    <div className="company-news-feed-heading"><div><span className="eyebrow">{t(onlySaved?'YOUR READING LIST':'THE LATEST')}</span><h3>{t(onlySaved?'Saved stories':'Market desk')}</h3></div><span>{ready?t('{count} stories',{count:stories.length}):t('Article count unavailable')}</span></div>
    <div className="company-news-story-grid">
     {stories.map(storyCard)}
     {ready&&!stories.length&&<div className="home-card empty-state company-news-empty"><span aria-hidden="true">⌕</span><h3>{t(articles.length?'No articles match these filters.':'No stored articles in this news library.')}</h3><p>{t(articles.length?'Try a different topic, company, or search term.':'News sources and saved articles belong to the data in this project.')}</p>{!!articles.length&&<button type="button" className="dashboard-button secondary-action" onClick={clearFilters}>{t('Clear filters')}</button>}</div>}
    </div>
   </div>

   <aside className="company-news-sidebar">
    <section className="home-card company-news-watchlist">
     <header><div><span className="eyebrow">{t('YOUR UNIVERSE')}</span><h3>{t('Companies to follow')}</h3></div><span>{watched.length}</span></header>
     {watched.length?watched.slice(0,5).map(company=><button type="button" className="company-news-watch-row" key={company.ticker} onClick={()=>onCompany?.(company)}><span className="company-news-ticker" style={{'--ticker-color':company.color}}>{company.ticker.slice(0,2)}</span><span className="company-news-watch-name"><strong>{company.ticker}</strong><small>{t(company.sector)}</small></span><span className={company.change<0?'is-negative':'is-positive'}>{percent(company.change)}</span><span className="company-news-row-arrow" aria-hidden="true">↗</span></button>):<p className="company-news-empty-copy">{t('Follow companies to see them here.')}</p>}
     <p className="company-news-aside-note">{t('Sample watchlist moves; select a company to open its research.')}</p>
    </section>

    <section className="home-card company-news-reading-list">
     <header><div><span className="eyebrow">{t('PICK UP WHERE YOU LEFT OFF')}</span><h3>{t('Reading list')}</h3></div><span>{savedStories.length}</span></header>
     {savedStories.length?savedStories.map(article=><button type="button" key={article.id} onClick={()=>onArticle(article)}><span className="category-pill">{t(article.category)}</span><strong>{article.title}</strong><small>{t('Saved briefing')} · {article.time}</small></button>):<div className="company-news-empty-copy"><span aria-hidden="true">☆</span><p>{t('Save a briefing to build your reading list.')}</p></div>}
    </section>

    <div className="company-news-disclaimer"><span aria-hidden="true">i</span><p>{t('Source articles and claims require separate review. Stored reporting does not automatically change scenario probabilities.')}</p></div>
   </aside>
  </div>
 </section>;
}
