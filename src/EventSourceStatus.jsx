import React, {useEffect, useRef, useState} from 'react';
import {sourceUrl} from './eventScenarios.js';

const count = value => Number.isInteger(value) && value >= 0 ? value : null;
const contextKey = query => JSON.stringify([query.category,query.factor,(query.focus || 'World').trim().toLowerCase(),query.horizon]);
const blankArchive = () => ({phase:'idle',data:null,error:'',selected:'',limit:12});
const pollLabels = {
  NEW_REVISION:'New reporting was stored', UNCHANGED:'No change at the last collection',
  FETCH_FAILED:'The last collection attempt failed', INSUFFICIENT_EVIDENCE:'The last collection had insufficient relevant reporting',
};
const feedLabels = {
  NEWS_NETWORK_OR_PROVIDER_ERROR:'Provider could not be reached', NEWS_HTTP_ERROR:'Provider returned an HTTP error',
  RSS_PARSE_FAILED:'Provider returned unreadable RSS', GDELT_INVALID_JSON:'Provider returned unreadable data',
  NEWS_RESPONSE_TOO_LARGE:'Provider response exceeded the size limit', UNTRUSTED_PROVIDER:'Provider address was rejected',
};

function archiveSnapshot(entry, query) {
  const snapshot = entry?.snapshot;
  if (!snapshot || contextKey(snapshot) !== contextKey(query) || !Array.isArray(snapshot.items)) return null;
  return {...entry,items:snapshot.items.filter(item => item && typeof item === 'object')};
}

export default function EventSourceStatus({result, query, failedCoverage, showArchive=true, t, formatDate}) {
  const context = result || query;
  const identity = contextKey(context);
  const activeIdentity=useRef(identity);
  activeIdentity.current=identity;
  const [archives,setArchives] = useState({agent:blankArchive(),library:blankArchive()});
  const pending = useRef({agent:null,library:null});
  useEffect(() => {
    setArchives({agent:blankArchive(),library:blankArchive()});
    return () => {
      for (const request of Object.values(pending.current)) request?.abort();
      pending.current={agent:null,library:null};
    };
  },[identity]);

  const diagnostics = result?.filter_diagnostics || {};
  const coverage = failedCoverage || result?.coverage || {};
  const value = number => count(number) ?? t('Not recorded');
  const retrieved = count(diagnostics.retrieved) ?? count(coverage.raw_results);
  const accepted = count(diagnostics.accepted) ?? count(result?.source_count) ?? (Array.isArray(result?.items) ? result.items.length : null);
  const regional = count(result?.scope_source_count) ?? (result?.items?.length && result.items.every(item => typeof item.geographic_relation === 'string')
    ? result.items.filter(item => ['GLOBAL_SCOPE','DIRECT_SCOPE'].includes(item.geographic_relation)).length : null);
  const requests = Array.isArray(coverage.request_results) ? coverage.request_results.filter(item => item && typeof item === 'object') : [];
  const failures = Array.isArray(coverage.feed_failures) ? coverage.feed_failures.filter(item => item && typeof item === 'object') : [];
  const update = (kind,changes) => setArchives(current => ({...current,[kind]:{...current[kind],...changes}}));
  const feedFailure = reason => typeof reason === 'string' && /^NEWS_HTTP_\d{3}$/.test(reason)
    ? t('Provider returned HTTP {status}',{status:reason.slice(-3)})
    : t(Object.hasOwn(feedLabels,reason) ? feedLabels[reason] : 'Provider request failed');

  async function loadArchive(kind) {
    pending.current[kind]?.abort();
    const controller = new AbortController();
    pending.current[kind]=controller;
    update(kind,{phase:'loading',data:null,error:'',selected:'',limit:12});
    const timeout = setTimeout(() => controller.abort(),20000);
    const current = () => pending.current[kind] === controller && activeIdentity.current === identity;
    try {
      const params = new URLSearchParams({category:context.category,factor:context.factor,focus:context.focus || 'World',horizon:context.horizon});
      const response = await fetch(kind === 'agent' ? '/api/research/events/agent?'+params : '/api/research/news',
        {credentials:'same-origin',signal:controller.signal});
      if (!current()) return;
      if (!response.ok) throw Error(response.status === 401 ? 'Sign in again to read previously collected reporting.' :
        response.status === 403 ? 'This account cannot access this reporting library.' : 'Previously collected reporting could not be read.');
      const data = await response.json();
      if (!current()) return;
      if (!data || typeof data !== 'object' || (kind === 'agent' ? typeof data.status !== 'string' : !Array.isArray(data.articles))) {
        throw Error('The reporting library returned an unreadable response.');
      }
      if (kind === 'agent') {
        const entries = Array.isArray(data.versions) ? data.versions : data.latest ? [data.latest] : [];
        const versions=entries.map(entry => archiveSnapshot(entry,context)).filter(Boolean);
        if (entries.length && !versions.length) throw Error('The stored collection does not match this research context.');
        update(kind,{phase:'ready',data:{...data,versions},selected:versions.length ? String(versions[0].id) : ''});
      } else {
        update(kind,{phase:'ready',data:{...data,articles:data.articles.filter(item => item && typeof item === 'object').slice(0,200)}});
      }
    } catch (error) {
      if (!current()) return;
      update(kind,{phase:'error',error:error.name === 'AbortError' ? 'Reading the reporting library timed out. Try again.' :
        error instanceof TypeError || error instanceof SyntaxError ? 'Previously collected reporting could not be read.' : error.message});
    } finally {
      clearTimeout(timeout);
      if (pending.current[kind] === controller) pending.current[kind]=null;
    }
  }

  function articleList(items,kind) {
    const archive=archives[kind];
    return <>
      <div className="ev-collected-articles">{items.slice(0,archive.limit).map((article,index) => {
        const url=sourceUrl(article.url);
        const title=typeof article.title === 'string' ? article.title : t('Original article');
        return <article key={article.id || article.url || index}>
          {url ? <a href={url} target="_blank" rel="noopener noreferrer">{title} ↗</a> : <strong>{title}</strong>}
          <p>{typeof article.source === 'string' ? article.source : typeof article.provider === 'string' ? article.provider : t('Source unavailable')}</p>
          <p>{t('Published')}: {formatDate(article.published_at)}{article.ingested_at && <> · {t('Collected')}: {formatDate(article.ingested_at)}</>}</p>
          {typeof (article.description || article.summary) === 'string' && <p>{article.description || article.summary}</p>}
        </article>;
      })}</div>
      {items.length > archive.limit && <button type="button" className="ev-secondary" onClick={() => update(kind,{limit:archive.limit+12})}>{t('Show more collected articles')} ({items.length-archive.limit})</button>}
    </>;
  }

  function archiveBody(kind) {
    const archive=archives[kind];
    if (archive.phase === 'idle') return null;
    if (archive.phase === 'loading') return <p role="status">{t('Reading previously collected reporting…')}</p>;
    if (archive.phase === 'error') return <p className="ev-archive-error" role="alert">{t(archive.error)}</p>;
    const data=archive.data;
    if (kind === 'library') return <div className="ev-collected-result">
      <p>{t('Company News library: up to 200 latest stored articles across broader topics. These are not automatically evidence for this scenario.')}</p>
      {data.articles.length ? <><strong>{t('{count} stored articles available',{count:data.articles.length})}</strong>{articleList(data.articles,kind)}</> :
        <p>{t('No stored articles were found here. If an older version contained reporting, recover its data before checking again.')}</p>}
    </div>;
    const version=data.versions.find(entry => String(entry.id) === archive.selected) || data.versions[0];
    const statusText={
      AGENT_NOT_INITIALIZED:'No collector archive is available in this version.',
      WATCH_NOT_CONFIGURED:'The collector has no saved watch for this exact factor, region and horizon.',
      AGENT_STORAGE_UNAVAILABLE:'The collector archive could not be read.',
      WAITING_FOR_FIRST_POLL:'This watch has no recorded collection attempt yet.',
    }[data.status];
    return <div className="ev-collected-result">
      {statusText && <p>{t(statusText)}</p>}
      {data.last_poll && <p>{t('Last recorded collection')}: {formatDate(data.last_poll.checked_at)} · {t(pollLabels[data.last_poll.status] || 'Collection status is not recorded')}</p>}
      {data.versions.length > 1 && <label>{t('Saved collection')}<select value={archive.selected} onChange={event => update(kind,{selected:event.target.value,limit:12})}>
        {data.versions.map((entry,index) => <option key={entry.id ?? index} value={String(entry.id)}>{formatDate(entry.created_at)}</option>)}
      </select></label>}
      {version ? <><p>{t('Archived reporting as of')}: {formatDate(version.created_at || version.snapshot.generated_at)}</p>
        <strong>{t('{count} stored articles available',{count:version.items.length})}</strong>{articleList(version.items,kind)}</> :
        data.status !== 'AGENT_STORAGE_UNAVAILABLE' && <p>{t('If an older version contained reporting, recover its collector data. A new source ZIP does not include local archives.')}</p>}
    </div>;
  }

  return <>
    <section className="ev-collection-status" aria-label={t(failedCoverage ? 'Latest failed news search' : 'News collection status')}>
      <span className="ev-kicker">{t('NEWS COLLECTION')}</span><h3>{t(failedCoverage ? 'The latest news search failed' : 'Where the reporting went')}</h3>
      <dl className="ev-collection-counts"><div><dt>{t('Feed entries retrieved')}</dt><dd>{value(retrieved)}</dd></div>
        <div><dt>{t('Distinct articles kept')}</dt><dd>{value(accepted)}</dd></div><div><dt>{t('Within the selected region')}</dt><dd>{value(regional)}</dd></div></dl>
      <p>{t('News articles and historical outcome observations are separate. Zero outcome observations does not mean no news was collected.')}</p>
      {failedCoverage && <p>{t('These request results belong to the latest failed search. Any previous report keeps its original dates and collection counts.')}</p>}
      {!result && !failedCoverage && <p>{t('Run an analysis to see current feed and filtering counts. Stored reporting can be opened below without a live search.')}</p>}
      {(result || failedCoverage) && <>
        <p>{t('Feed requests succeeded')}: {value(coverage.feed_successes)} / {value(coverage.requests)}</p>
        <details className="ev-collection-details" open={failedCoverage ? true : undefined}><summary>{t('Collection and filtering details')}</summary>
          <dl>{[['retrieved','Retrieved entries'],['accepted','Accepted entries'],['stale','Outside the news window'],['duplicate','Duplicate entries'],['off_topic','Outside the selected topic'],['future','Future-dated entries'],['invalid','Unreadable dates or entries']].map(([key,label]) => <div key={key}><dt>{t(label)}</dt><dd>{value(diagnostics[key])}</dd></div>)}</dl>
          {requests.length > 0 && <div className="ev-feed-results">{requests.map((entry,index) => <p key={index}><strong>{typeof entry.provider === 'string' ? entry.provider : t('Source unavailable')}{typeof entry.edition === 'string' ? ' · '+entry.edition : ''}</strong><span>{t(entry.status === 'SUCCESS' ? 'Request succeeded' : entry.status === 'FAILED' ? 'Request failed' : 'Request status not recorded')} · {t('Returned entries')}: {value(entry.returned_count)}</span></p>)}</div>}
          {failures.length > 0 && <div className="ev-feed-failures"><strong>{t('Failed feed requests')}</strong>{failures.map((entry,index) => <p key={index}>{typeof entry.provider === 'string' ? entry.provider : t('Source unavailable')}{typeof entry.edition === 'string' ? ' · '+entry.edition : ''} · {feedFailure(entry.reason)}</p>)}</div>}
          {!requests.length && !failures.length && <p>{t('Individual request results were not recorded in this report.')}</p>}
        </details>
      </>}
    </section>
    {showArchive && <section className="ev-collected-reporting" aria-label={t('Previously collected reporting')}>
      <span className="ev-kicker">{t('STORED REPORTING')}</span><h3>{t('Previously collected reporting')}</h3>
      <p>{t('Open saved reporting from this installation. Archive articles retain their dates and do not change the current scores or probabilities.')}</p>
      <div className="ev-collected-actions"><button type="button" className="ev-secondary" disabled={archives.agent.phase === 'loading'} onClick={() => loadArchive('agent')}>{t('Read collector archive')}</button>
        <button type="button" className="ev-secondary" disabled={archives.library.phase === 'loading'} onClick={() => loadArchive('library')}>{t('Read Company News library')}</button></div>
      <div className="ev-collector-archive">{archiveBody('agent')}</div>
      <div className="ev-company-archive">{archiveBody('library')}</div>
    </section>}
  </>;
}
