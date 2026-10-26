import React,{useEffect,useState} from 'react';
export default function OperationalHealth(){
 const [data,setData]=useState(null),[notice,setNotice]=useState('');
 async function load(){try{const r=await fetch('/api/admin/health');const d=await r.json();if(!r.ok)throw Error(d.message||'Health service unavailable');setData(d);setNotice('');}catch(e){setNotice(e.message);}}
 useEffect(()=>{load();},[]);
 return <section><h2>Operational / analytical health</h2><p>Subsystem readiness is independent. A valid financial ratio does not certify a market probability. This panel does not enable production release.</p><button onClick={load}>Refresh health checks</button><p role="status">{notice}</p>{data&&<><p>{data.status} · {data.checked_at} · Run {data.run_id} · Trace {data.trace_id}</p><p>{data.release_gate}</p>{data.subsystems.map(s=><details key={s.subsystem} open><summary>{s.subsystem} · {s.status}</summary><p>{s.reason_codes?.join(' · ')}</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(s,null,2)}</pre></details>)}<details><summary>Recent sanitized request traces</summary>{data.recent_request_traces?.map(r=><p key={r.trace_id}>{r.trace_id} · {r.route_group} · HTTP {r.http_status} · {r.error_code||'OK'} · {r.occurred_at}</p>)}</details></>}</section>;
}
