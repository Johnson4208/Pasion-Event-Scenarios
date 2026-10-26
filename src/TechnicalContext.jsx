import React,{useEffect,useState} from 'react';
export default function TechnicalContext({ticker}){
 const [state,setState]=useState(null);
 useEffect(()=>{let active=true;const controller=new AbortController();setState(null);fetch('/api/market/'+encodeURIComponent(ticker)+'/indicators',{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{if(active&&d.version===1)setState(d);}).catch(()=>{});return()=>{active=false;controller.abort();};},[ticker]);
 const ready=state?.ticker===ticker&&state.status==='READY'&&Date.now()-Date.parse(state.as_of)<=86400000;
 return <details><summary>Completed-bar technical context · {ready?'READY':state?.status||'UNAVAILABLE'}</summary><p>Shared indicator service; heuristic context is not model probability or measured order flow.</p>{['RVOL20','RSI14','ATR14','SMA20','SMA60','SMA200'].map(k=><p key={k}>{k}: {ready&&state.indicators[k]?.status==='READY'?state.indicators[k].value:'Unavailable'}</p>)}<p>{state?.as_of} · {state?.reason_codes?.join(', ')}</p></details>;
}
