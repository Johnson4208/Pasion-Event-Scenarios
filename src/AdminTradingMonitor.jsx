import React,{useEffect,useMemo,useState} from 'react';
import './admin-trading-monitor.scss';
import DistributionLab from './DistributionLab';

const fmt=n=>Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
const empty='—';
export default function AdminTradingMonitor({onExpired}) {
 const local=['localhost','127.0.0.1','[::1]'].includes(window.location.hostname);
 const [mode,setMode]=useState(local?'lab':'records');
 return <section className="trading-monitor">
  <header className="atm-heading"><h1>Trading &amp; Distribution Monitor</h1></header>
  <nav className="atm-tabs" aria-label="Nguồn hoạt động">
   <button type="button" aria-pressed={mode==='lab'} onClick={()=>setMode('lab')}>Distribution Lab</button>
   <button type="button" aria-pressed={mode==='records'} onClick={()=>setMode('records')}>Sổ tài khoản &amp; Shadow</button>
  </nav>
  {mode==='lab'?<DistributionLab onExpired={onExpired}/>:<AccountMonitor/>}
 </section>;
}

function AccountMonitor(){
 const [data,setData]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[currency,setCurrency]=useState(''),[tab,setTab]=useState('Overview');
 async function refresh(){setLoading(true);setError('');try{const r=await fetch('/api/admin/distribution/monitor',{credentials:'same-origin'});if(!r.ok)throw Error(r.status===403?'Administrator permission required':'Monitor endpoint unavailable');setData(await r.json());}catch(e){setError(e.message);}finally{setLoading(false)}}
 useEffect(()=>{refresh()},[]);
 const currencies=data?.manual_activity?.by_currency||[];
 const activeCurrency=currency||currencies[0]?.currency||'';
 const accounts=useMemo(()=> (data?.manual_activity?.top_accounts||[]).filter(x=>x.currency===activeCurrency).sort((a,b)=>Number(b.manual_notional)-Number(a.manual_notional)),[data,activeCurrency]);
 const pools=data?.distribution?.pools||[];
 const totals=currencies.find(x=>x.currency===activeCurrency);
 const events=data?.distribution?.recent_events||[];
 const candidates=data?.distribution?.recent_candidates||[];
 return <div className="atm-root">
  <header className="atm-heading"><div><h2>Account activity</h2><p>Private oversight of manual account activity, candidate admission and simulated capacity. No broker execution is inferred.</p></div><button className="atm-refresh" onClick={refresh} disabled={loading}>{loading?'Loading…':'↻ Refresh data'}</button></header>
  <div className="atm-notice" role="status"><b>Research / shadow mode</b><span>Broker-confirmed trading volume and top executed traders are unavailable until verified fills are connected. Manual entries and shadow slots are shown separately.</span></div>
  {error&&<div role="alert" className="atm-error">{error}. This view requires the full PASION backend, not the static GitHub Pages demo.</div>}
  <div className="atm-tabs">{['Overview','Top accounts','Distribution activity'].map(x=><button key={x} onClick={()=>setTab(x)} aria-pressed={tab===x}>{x}</button>)}</div>
  <div className="atm-metrics">
   <article><span>Recorded manual BUY / SELL</span><strong>{data?.manual_activity?.trade_records??empty}</strong><small>Unverified entries · not fills</small></article>
   <article><span>Reported notional</span><strong>{totals?fmt(totals.notional):empty}</strong><small>{activeCurrency||'No currency'} · manual records only</small></article>
   <article><span>Distribution candidates</span><strong>{data?.distribution?.candidate_count??empty}</strong><small>{data?.distribution?.withheld_count??empty} withheld by safety gates</small></article>
   <article><span>Simulated reservations</span><strong>{pools.reduce((n,p)=>n+(Number(p.reserved_slots)||0),0)}</strong><small>Review slots, NOT market shares</small></article>
  </div>
  {(tab==='Overview'||tab==='Top accounts')&&<div className="atm-columns">
   <section className="atm-panel"><div className="atm-panel-title"><div><span className="atm-kicker">ACTIVITY RANKING</span><h2>Top accounts</h2></div><label>Currency <select value={activeCurrency} onChange={e=>setCurrency(e.target.value)}>{currencies.map(x=><option key={x.currency}>{x.currency}</option>)}</select></label></div><p className="atm-sub">Ranked by user-entered notional within one currency. This is not a ranking of executed traders.</p><div className="atm-table-wrap"><table><thead><tr><th>Rank</th><th>Account</th><th>Currency</th><th>Manual notional</th><th>Records</th></tr></thead><tbody>{accounts.length?accounts.map((x,i)=><tr key={x.account_id+'-'+x.currency}><td>#{i+1}</td><td><b>{x.account_ref}</b></td><td>{x.currency}</td><td>{fmt(x.manual_notional)}</td><td>{x.manual_trade_records}</td></tr>):<tr><td colSpan="5">No eligible manual trade records</td></tr>}</tbody></table></div></section>
   <section className="atm-panel"><div className="atm-panel-title"><div><span className="atm-kicker">ORDER INTELLIGENCE</span><h2>Trading volume</h2></div></div><div className="atm-unavailable"><b>Broker-confirmed volume unavailable</b><span>There is no verified order, fill or exchange tape feed. The system cannot report traded market volume or identify top executed accounts.</span></div><h3>Manual observations by currency</h3>{currencies.length?currencies.map(x=><div className="atm-activity-line" key={x.currency}><span><b>{x.currency}</b> · {x.count} records</span><strong>{fmt(x.quantity)} units</strong></div>):<p className="atm-sub">No manual transaction activity yet.</p>}<p className="atm-sub">Quantities across different symbols are not summed into one actionable volume or liquidity estimate.</p></section>
  </div>}
  {(tab==='Overview'||tab==='Distribution activity')&&<div className="atm-columns">
   <section className="atm-panel"><div className="atm-panel-title"><div><span className="atm-kicker">CAPACITY WATCH</span><h2>Distribution pools</h2></div><span className="atm-tag">SHADOW ONLY</span></div>{pools.length?pools.map(x=><div className="atm-pool" key={x.id}><div><b>{x.horizon} / {x.utility_definition}</b><span>{x.policy}</span></div><div><strong>{x.reserved_slots}/{x.capacity_slots}</strong><small>simulated slots reserved</small></div><div className="atm-track"><span style={{width:`${Math.max(0,Math.min(100,100*x.reserved_slots/x.capacity_slots))}%`}}/></div></div>):<p className="atm-sub">No reviewed shadow capacity policies have been created.</p>}</section>
   <section className="atm-panel"><div className="atm-panel-title"><div><span className="atm-kicker">ADMISSION AUDIT</span><h2>Candidate outcomes</h2></div><span className="atm-tag">NO LIVE ALLOCATION</span></div>{candidates.length?candidates.map(x=><div className="atm-candidate" key={x.id}><div><b>{x.ticker}</b><span className="atm-status">{x.status}</span></div><small>{x.feasibility_status} · {(x.reason_codes||[]).slice(0,2).join(' / ')||'No reasons'}</small></div>):<p className="atm-sub">No candidates received by the Distribution shadow engine.</p>}</section>
  </div>}
  {(tab==='Overview'||tab==='Distribution activity')&&<section className="atm-panel"><div className="atm-panel-title"><div><span className="atm-kicker">IMMUTABLE EVENTS</span><h2>Distribution activity log</h2></div></div><div className="atm-table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Candidate</th><th>Capacity basis</th></tr></thead><tbody>{events.length?events.map((e,i)=><tr key={e.id||i}><td>{e.known_at||empty}</td><td>{e.action||empty}</td><td>{e.candidate_id||empty}</td><td>{e.capacity_unit||'Simulated review slots'}</td></tr>):<tr><td colSpan="4">No transition events recorded yet.</td></tr>}</tbody></table></div></section>}
  <footer className="atm-footer">Designed to match the PASION workspace. Results are read-only; safety gates, concentration policies, real-time tape and broker fill integration must be validated before live allocations.</footer>
 </div>;
}
