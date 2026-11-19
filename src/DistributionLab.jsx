import React, {useEffect, useRef, useState} from 'react';
import './distribution-lab.scss';

const endpoint = '/api/admin/distribution/lab';
const labels = {
  customers: 'Khách hàng ban đầu', daily_requests: 'Yêu cầu tối đa mỗi ngày',
  max_per_symbol: 'Giới hạn mỗi mã (lượt)', max_per_sector: 'Giới hạn mỗi ngành (lượt)',
  window_days: 'Cửa sổ giới hạn (ngày)', cooldown_days: 'Chờ trước khi lặp mã (ngày)',
  utility_tolerance: 'Chênh lệch điểm cho phép', speed: 'Tốc độ (ngày mô phỏng/giây)',
  seed: 'Seed ngẫu nhiên',
};
const rules = ['max_per_symbol', 'max_per_sector', 'window_days', 'cooldown_days',
               'utility_tolerance', 'daily_requests', 'speed'];
const states = {paused:'Tạm dừng', running:'Đang chạy', completed:'Hoàn tất', failed:'Đã dừng do lỗi'};
const reasons = {SYMBOL_EXPOSURE_CAP:'Đạt giới hạn mã', SECTOR_EXPOSURE_CAP:'Đạt giới hạn ngành',
                 CUSTOMER_REPEAT_COOLDOWN:'Khách vừa nhận mã'};
const number = value => value.toLocaleString('vi-VN');
const dateLabel = value => value.split('-').reverse().join('/');
const asFields = form => Object.fromEntries(Array.from(new FormData(form), ([name, value]) =>
  [name, name === 'start_date' ? value : Number(value)]));

function NumberField({name, config, limits}) {
  return <label>{labels[name]}<input type="number" name={name} defaultValue={config[name]} required
    min={limits[name][0]} max={limits[name][1]} step={name === 'utility_tolerance' ? 'any' : 1}/></label>;
}

function ScenarioForm({defaults, limits, busy, create}) {
  const [days, setDays] = useState(defaults.days);
  return <form className="dl-form" onSubmit={e => {e.preventDefault(); create(asFields(e.currentTarget));}}>
    <fieldset disabled={busy}>
      <div className="dl-duration"><label>Thời gian mô phỏng (ngày)
        <input type="number" name="days" min="1" max={limits.days[1]} required value={days}
          onChange={e=>setDays(e.target.value)}/></label>
        <div className="dl-buttons">{[[365,'1 năm'],[730,'2 năm']].map(([n, label]) =>
          <button key={n} type="button" aria-pressed={Number(days)===n} onClick={()=>setDays(n)}>{label}</button>)}
          <button type="button" onClick={()=>setDays(1 + Math.floor(Math.random()*limits.days[1]))}>Ngẫu nhiên</button>
        </div>
      </div>
      <div className="dl-fields"><label>Ngày bắt đầu<input type="date" name="start_date" min="2000-01-01"
        max="2099-12-31" defaultValue={defaults.start_date} required/></label>
        <NumberField name="customers" config={defaults} limits={limits}/>
        <NumberField name="seed" config={defaults} limits={limits}/>
      </div>
      <details><summary>Thông số thuật toán và tốc độ</summary><div className="dl-fields">
        {rules.map(name=><NumberField key={name} {...{name,config:defaults,limits}}/>)}</div></details>
      <button className="dl-primary" type="submit">Tạo lượt mô phỏng</button>
    </fieldset>
  </form>;
}

function Trend({history}) {
  const size = Math.max(1, Math.ceil(history.length/32));
  const buckets = [];
  for (let i=0; i<history.length; i+=size) {
    const days = history.slice(i, i+size);
    buckets.push({first:days[0].day, last:days.at(-1).day,
      selected:days.reduce((sum,d)=>sum+d.selected,0), withheld:days.reduce((sum,d)=>sum+d.withheld,0)});
  }
  const max = Math.max(1, ...buckets.map(b=>b.selected+b.withheld));
  return <section className="dl-card"><h3>Yêu cầu theo thời gian</h3>
    <div className="dl-legend"><span>Đã gợi ý</span><span>Giữ lại</span></div>
    {history.length ? <><div className="dl-chart" role="list" aria-label="Lượng yêu cầu theo kỳ">
      {buckets.map(b=>{const label='Ngày '+b.first+'–'+b.last+' · '+b.selected+' đã gợi ý · '+b.withheld+' giữ lại';
        return <div key={b.first} role="listitem" title={label} aria-label={label}>
          <i style={{height:100*b.withheld/max+'%'}}/><i style={{height:100*b.selected/max+'%'}}/>
        </div>;})}</div><div className="dl-axis"><span>{dateLabel(history[0].date)}</span>
          <span>{size} ngày/cột</span><span>{dateLabel(history.at(-1).date)}</span></div></>
      : <p className="dl-empty">Chạy hoặc tiến một ngày để xem diễn biến.</p>}
  </section>;
}

function LiveControls({run, limits, busy, send}) {
  return <section className="dl-card"><h3>Điều khiển lượt hiện tại</h3>
    <p>Thay đổi áp dụng từ ngày mô phỏng tiếp theo.</p>
    <form onSubmit={e=>{e.preventDefault();send('update', asFields(e.currentTarget));}}>
      <fieldset disabled={busy} className="dl-inline"><label>Thêm khách giả lập<input type="number"
        name="add_customers" min="1" max={Math.max(0,limits.customers[1]-run.config.customers)} defaultValue="50" required/></label>
        <button disabled={run.config.customers>=limits.customers[1]}>Thêm khách</button></fieldset></form>
    <details><summary>Chỉnh giới hạn và tốc độ</summary><form key={run.changes.length}
      onSubmit={e=>{e.preventDefault();send('update',asFields(e.currentTarget));}}>
      <fieldset disabled={busy}><div className="dl-fields">
        {rules.map(name=><NumberField key={name} name={name} config={run.config} limits={limits}/>)}</div>
        <button type="submit">Áp dụng thông số</button></fieldset></form></details>
  </section>;
}

function Results({run}) {
  const largest = Math.max(1,...Object.values(run.symbols));
  return <>
    <div className="dl-grid"><Trend history={run.history}/>
      <section className="dl-card"><h3>Lượt gợi ý theo mã</h3>
        <div className="dl-bars">{Object.entries(run.symbols).map(([s,n])=><div key={s}>
          <span>{s}</span><div><i style={{width:100*n/largest+'%'}}/></div><b>{number(n)}</b>
        </div>)}</div></section></div>
    <section className="dl-card"><h3>Quyết định gần nhất</h3>
      <div className="dl-reasons">{Object.entries(reasons).map(([k,label])=>
        <span key={k}>{label} <b>{number(run.reasons[k] || 0)}</b></span>)}</div>
      <p>Số yêu cầu gặp từng giới hạn trong cả lượt chạy. Một yêu cầu có thể gặp nhiều giới hạn.</p>
      {run.events.length ? <div className="dl-scroll"><table><thead><tr>{['Ngày · UTC','Khách hàng','Ưu tiên ban đầu','Kết quả','Lý do đổi hoặc giữ lại'].map(s=><th key={s}>{s}</th>)}</tr></thead>
        <tbody>{run.events.map(e=><tr key={e.date+'-'+e.second}>
          <td>{dateLabel(e.date)} · {new Date(e.second*1000).toISOString().slice(11,19)}</td>
          <td>{e.customer}</td><td>{e.preferred}</td><td><b>{e.symbol || 'Giữ lại'}</b></td>
          <td>{e.reasons.map(r=>reasons[r] || r).join(', ') || '—'}</td></tr>)}</tbody></table></div>
        : <p>Chưa phát sinh yêu cầu.</p>}
    </section>
    <details className="dl-card"><summary>Lịch sử điều chỉnh ({run.changes.length})</summary>
      <div className="dl-scroll"><table><thead><tr>{['Từ ngày','Khách','Yêu cầu/ngày','Trần mã / ngành','Cửa sổ / chờ (ngày)','Chênh điểm','Ngày/giây'].map(s=><th key={s}>{s}</th>)}</tr></thead>
      <tbody>{run.changes.map(({day,config:c},i)=><tr key={i}><td>{day}</td><td>{number(c.customers)}</td>
        <td>{c.daily_requests}</td><td>{c.max_per_symbol} / {c.max_per_sector}</td>
        <td>{c.window_days} / {c.cooldown_days}</td><td>{c.utility_tolerance}</td><td>{c.speed}</td></tr>).reverse()}</tbody></table></div>
    </details>
  </>;
}

function exportRun(engine, run) {
  const url = URL.createObjectURL(new Blob([JSON.stringify({engine, run}, null, 2)], {type:'application/json'}));
  const a = document.createElement('a');
  a.href=url; a.download='distribution-lab-'+run.id+'.json'; a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export default function DistributionLab({onExpired}) {
  const [data,setData]=useState(null), [busy,setBusy]=useState(false);
  const [error,setError]=useState(''), [offline,setOffline]=useState('');
  const [showNew,setShowNew]=useState(false);
  const lifecycle=useRef({mounted:false,sequence:0,posting:false});
  const expired=useRef(onExpired);
  expired.current=onExpired;
  async function request(body, signal) {
    const response=await fetch(endpoint, body ? {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body), signal} : {cache:'no-store', signal});
    const result=await response.json();
    if (!response.ok) {
      if (response.status===401 && lifecycle.current.mounted) expired.current?.(result.message);
      throw new Error(result.message || 'Không thể kết nối với lab.');
    }
    return result;
  }
  useEffect(()=>{
    const ref=lifecycle.current;
    ref.mounted=true;
    const controller=new AbortController();
    let timer, closed=false;
    async function refresh() {
      let delay=950;
      if (!ref.posting) {
        const seq=++ref.sequence;
        try {
          const result=await request(null,controller.signal);
          if (!closed && seq===ref.sequence) {setData(result);setOffline('');}
          if (result.run?.status!=='running') delay=2200;
        } catch(e) {
          if (!closed && seq===ref.sequence) {setOffline(e.message);setData(null);}
        }
      }
      if (!closed) timer=setTimeout(refresh,delay);
    }
    refresh();
    return ()=>{closed=true;ref.mounted=false;ref.sequence++;controller.abort();clearTimeout(timer);};
  },[]);
  const run=data?.run;
  async function send(action,values={}) {
    const ref=lifecycle.current;
    if (ref.posting) return;
    ref.posting=true; ref.sequence++;
    setBusy(true);setError('');
    try {
      const result=await request({action,values,run_id:run?.id ?? null,revision:run?.revision ?? 0});
      if (ref.mounted) {setData(result);setOffline('');if(action==='create') setShowNew(false);}
    } catch(e) {
      if (ref.mounted) setError(e.message);
    } finally {
      ref.posting=false;
      if (ref.mounted) setBusy(false);
    }
  }
  const active=run && ['running','paused'].includes(run.status);
  return <section className="distribution-lab">
    <header className="dl-head"><div><h1>Distribution Lab</h1>
      <p>Mô phỏng cách thuật toán phân phối gợi ý giữa các khách hàng giả lập.</p></div>
      {run && <button onClick={()=>exportRun(data.engine,run)}>Xuất kết quả JSON</button>}</header>
    {offline && <p role="alert" className="dl-error">{offline}</p>}
    {error && <p role="alert" className="dl-error">{error}</p>}
    {!data && !offline && <p role="status">Đang kết nối lab…</p>}
    {run && <>
      <section className="dl-card dl-clock"><div className="dl-clock-head"><div><span className={'dl-state '+run.status}>{states[run.status]}</span>
        <h2>Ngày {number(run.day)} <small>/ {number(run.config.days)}</small></h2>
        <p>{run.day ? dateLabel(run.history.at(-1).date) : 'Bắt đầu '+dateLabel(run.config.start_date)} · Seed {run.config.seed} · {data.engine}</p></div>
        <div className="dl-buttons">{active && <><button className="dl-primary" disabled={busy}
          onClick={()=>send(run.status==='running'?'pause':'start')}>{run.status==='running'?'Tạm dừng':'Chạy mô phỏng'}</button>
          {run.status==='paused' && <button disabled={busy} onClick={()=>send('step')}>Tiến 1 ngày</button>}</>}
          {run.status!=='running' && <button aria-expanded={showNew} disabled={busy}
            onClick={()=>setShowNew(v=>!v)}>{showNew?'Đóng thiết lập':'Lượt mới'}</button>}
        </div></div>
        <progress aria-label="Tiến độ mô phỏng" value={run.day} max={run.config.days}/>
      </section>
      {run.error && <p role="alert" className="dl-error">{run.error}</p>}
    </>}
    {data && (!run || (showNew && run.status!=='running')) && <section className="dl-card">
      <h2>Thiết lập lượt mô phỏng</h2><p>{run?'Tạo lượt mới sẽ thay thế kết quả đang xem. Bạn có thể xuất JSON trước.':
        'Chọn thời gian và số khách. Dùng cùng seed và thông số để lặp lại thí nghiệm.'}</p>
      <ScenarioForm defaults={data.defaults} limits={data.limits} busy={busy} create={values=>send('create',values)}/>
    </section>}
    {run && <><div className="dl-kpis">{[['Khách giả lập',run.config.customers],['Yêu cầu',run.totals.requests],
      ['Đã gợi ý',run.totals.selected],['Trong đó đổi mã',run.totals.redirected],['Giữ lại',run.totals.withheld]]
      .map(([label,value])=><div key={label}><span>{label}</span><strong>{number(value)}</strong></div>)}</div>
      {active && <LiveControls key={run.id} run={run} limits={data.limits} busy={busy} send={send}/>}
      <Results run={run}/>
    </>}
  </section>;
}
