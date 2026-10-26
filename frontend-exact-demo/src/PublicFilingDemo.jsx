import React,{useState} from 'react';

export default function PublicFilingDemo(){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function run(){
  if(busy)return;
  setBusy(true);setError('');
  try{
   const response=await fetch('/api/research/examples/apple-2025',{credentials:'same-origin'});
   const result=await response.json();
   if(!response.ok||result.case!=='apple-fy2025-form10k'||!Array.isArray(result.metrics))throw Error(result.message||'Example calculation unavailable');
   setData(result);
  }catch(e){setData(null);setError(e.message||'Example calculation unavailable');}
  finally{setBusy(false);}
 }
 function format(row){
  if(row.status!=='READY'||row.value===null)return 'Unavailable';
  const v=Number(row.value);
  if(!Number.isFinite(v))return 'Unavailable';
  if(row.unit==='%')return v.toFixed(2)+'%';
  if(row.unit==='x')return v.toFixed(3)+'x';
  if(row.unit==='currency/share')return v.toFixed(2)+' USD/share';
  if(row.unit==='currency')return (v/1e9).toLocaleString(undefined,{maximumFractionDigits:3})+' USD bn';
  return v.toLocaleString();
 }
 return <section className="ir-card" aria-label="Public SEC financial calculation example" style={{marginBlock:'20px'}}>
  <header className="ir-section-heading" style={{display:'flex',justifyContent:'space-between',gap:'16px',alignItems:'center',flexWrap:'wrap'}}>
   <div><h2>Run economic calculations with a real filing</h2>
    <p>Apple FY2025 SEC Form 10-K · Selected public figures · Isolated example (not your selected stock)</p></div>
   <button type="button" onClick={run} disabled={busy} style={{padding:'10px 18px',borderRadius:'8px',cursor:busy?'wait':'pointer'}}>
    {busy?'Calculating…':data?'Recalculate example':'Run calculations'}</button>
  </header>
  <p style={{fontSize:'.85rem',marginBottom:'12px'}}>The existing financial engine recomputes ratios from the published figures each time you click. No data is imported into your actual portfolio or the reviewed issuer database.</p>
  {error&&<p role="alert" style={{color:'#a61b32'}}>{error}</p>}
  {data&&<>
   <p role="status"><strong>{data.issuer} · {data.period}</strong> · {data.source_basis} · {data.execution_mode}</p>
   <div className="ir-table-scroll" style={{overflowX:'auto'}}>
    <table className="ir-financial-table">
     <thead><tr><th scope="col">Financial metric</th><th scope="col">Calculation or input</th><th scope="col">Result</th><th scope="col">Status</th></tr></thead>
     <tbody>{data.metrics.map(row=><tr key={row.id}>
      <th scope="row">{row.label}</th>
      <td>{row.formula}{row.inputs.length>0&&<details><summary>Source cells ({row.inputs.length})</summary>{row.inputs.map(s=><p key={s.id}>{s.label} · FY end {s.period_end} · filing p. {s.page}</p>)}</details>}</td>
      <td style={{fontWeight:600}}>{format(row)}</td>
      <td>{row.status==='READY'?'Calculated':row.status}{row.status!=='READY'&&<div style={{fontSize:'.76rem'}}>{row.reason_codes.join(', ')||'Insufficient eligible input'}</div>}</td>
     </tr>)}</tbody>
    </table>
   </div>
   <p style={{marginTop:14,fontSize:'.85rem'}}>{data.disclosure}</p>
   <a href={data.source_url} target="_blank" rel="noopener noreferrer">Open the original SEC Form 10-K ↗</a>
  </>}
 </section>;
}
