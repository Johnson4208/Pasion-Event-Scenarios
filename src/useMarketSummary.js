import {useEffect, useState} from 'react';
import {marketPulseInstruments} from './marketPulseData';

const demo = () => ({version: 1, mode: 'demo', status: 'READY', reason: 'ILLUSTRATIVE_FIXTURE',
  provider_status: 'UNAVAILABLE', quotes: marketPulseInstruments.map(item => ({...item,
    origin: 'SAMPLE', status: 'READY', source: 'Pasion demo fixture', as_of: null, reason: 'ILLUSTRATIVE_FIXTURE'}))});

export default function useMarketSummary(mode) {
  const [result, setResult] = useState(demo);
  useEffect(() => {
    let active = true;
    let controller;
    async function refresh() {
      controller?.abort();
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      try {
        const response = await fetch('/api/market/summary?mode=' + mode, {signal: controller.signal});
        if (!response.ok) throw new Error('Market service unavailable');
        const body = await response.json();
        if (body.version !== 1 || body.mode !== mode || !Array.isArray(body.quotes)) throw new Error('Invalid contract');
        if (mode === 'provider') body.quotes = body.quotes.map(quote => {
          if (quote.status !== 'READY') return {...quote, price:null, change:null};
          const valid = quote.origin === 'ACTUAL' && Number.isFinite(quote.price) && quote.price > 0 &&
            Number.isFinite(quote.change) && Number.isFinite(Date.parse(quote.as_of)) &&
            Date.parse(quote.as_of) <= Date.now() && Date.parse(quote.expires_at) > Date.now();
          return valid ? quote : {...quote, price:null, change:null, status:'WITHHELD', reason:'INVALID_QUOTE_OR_SESSION'};
        });
        if (mode === 'provider') body.benchmark = body.quotes.find(q => q.ticker === 'SPX' && q.status === 'READY') || {status:'UNAVAILABLE'};
        if (active) setResult(body);
      } catch {
        if (active) setResult(mode === 'demo' ? demo() : {version: 1, mode, status: 'UNAVAILABLE',
          provider_status: 'UNAVAILABLE', reason: 'MARKET_SERVICE_UNAVAILABLE', quotes: []});
      } finally { clearTimeout(timeout); }
    }
    setResult(mode === 'demo' ? demo() : {mode, status: 'UNAVAILABLE', reason: 'LOADING', quotes: []});
    refresh();
    const timer = setInterval(refresh, 30000);
    const expiryTimer = setInterval(() => {
      if (mode !== 'provider') return;
      setResult(previous => {
        const expired = previous.quotes.some(q => q.status === 'READY' && Date.parse(q.expires_at) <= Date.now());
        if (!expired) return previous;
        const quotes = previous.quotes.map(q => q.status === 'READY' && Date.parse(q.expires_at) <= Date.now() ?
          {...q, status:'STALE', reason:'QUOTE_EXPIRED', price:null, change:null} : q);
        const benchmark = quotes.find(q => q.ticker === 'SPX' && q.status === 'READY');
        return {...previous, quotes, benchmark:benchmark || {status:'UNAVAILABLE'},
          coverage:{...previous.coverage, available:quotes.filter(q => q.status === 'READY').length}};
      });
    }, 1000);
    return () => { active = false; clearInterval(timer); clearInterval(expiryTimer); controller?.abort(); };
  }, [mode]);
  // Never render the previous mode while a new request is pending.
  return result.mode === mode ? result : {mode, status: 'UNAVAILABLE', reason: 'LOADING', quotes: []};
}
