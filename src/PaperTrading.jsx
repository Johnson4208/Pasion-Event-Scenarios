import React from 'react';

const fmt = n => Number(n).toLocaleString('vi-VN',{maximumFractionDigits:2});
const date = value => value.split('-').reverse().join('/');

function Table({columns,children}) {
  return <div className="dl-scroll"><table><thead><tr>{columns.map(x=><th key={x}>{x}</th>)}</tr></thead>
    <tbody>{children}</tbody></table></div>;
}

export default function PaperTrading({run,chart}) {
  const report=run.paper;
  const totals=report?.totals || {buys:0,sells:0,quantity:0,notional:0};
  return <section className="dl-paper" aria-label="Sổ giao dịch mô phỏng">
    <div><h2>Sổ giao dịch mô phỏng</h2><p>{report?.source || 'DNSE / Entrade'} · Vốn ban đầu {fmt(run.config.initial_cash)} VND/khách
      {run.day>0 && !run.history.at(-1).session_open && ' · Ngày này không có phiên giao dịch'}</p></div>
    <div className="dl-kpis">{[['Lượt mua',totals.buys],['Lượt bán',totals.sells],
      ['Cổ phiếu đã giao dịch',totals.quantity],['Giá trị giao dịch (VND)',totals.notional]].map(([k,v])=>
      <div key={k}><span>{k}</span><strong>{fmt(v)}</strong></div>)}</div>
    <div className="dl-grid">{chart}<section className="dl-card"><h3>Khối lượng theo mã</h3>
      {report?.symbols.length ? <Table columns={['Mã','Mua / Bán','Cổ phiếu','Giá trị (VND)']}>
        {report.symbols.map(s=><tr key={s.symbol}><td>{s.symbol}</td><td>{s.buys} / {s.sells}</td>
          <td>{fmt(s.quantity)}</td><td>{fmt(s.notional)}</td></tr>)}</Table>:<p>Chưa có giao dịch mô phỏng.</p>}</section></div>
    <section className="dl-card"><h3>Giao dịch gần nhất</h3>
      {report?.fills.length ? <Table columns={['Ngày','Khách · hồ sơ','Mã','Lệnh','Cổ phiếu','Giá mở cửa (VND)','Căn cứ từ phiên trước']}>
        {report.fills.map(f=><tr key={f.id}><td>{date(f.day)}</td><td>{f.customer} · {f.profile}</td>
          <td>{f.symbol}</td><td>{f.side}</td><td>{fmt(f.quantity)}</td><td>{fmt(f.price)}</td>
          <td>{date(f.signal_date)} · Đóng {fmt(f.prior_close)} {f.side==='BUY'?'≥':'<'} SMA20 {fmt(f.sma20)} · RSI {fmt(f.rsi)}</td></tr>)}
      </Table>:<p>Giao dịch xuất hiện khi tín hiệu và điều kiện vốn, rủi ro, số cổ phiếu nắm giữ cho phép.</p>}</section>
    <details className="dl-card" open><summary>Top tài khoản theo giá trị giao dịch</summary>
      {report?.top_accounts.length ? <Table columns={['Hạng','Khách giả lập','Giá trị giao dịch (VND)','Số giao dịch','Tiền mặt (VND)']}>
        {report.top_accounts.map((a,i)=><tr key={a.customer}><td>{i+1}</td><td>{a.customer}</td><td>{fmt(a.turnover)}</td>
          <td>{fmt(a.trades)}</td><td>{fmt(a.cash)}</td></tr>)}</Table>:<p>Chưa có tài khoản phát sinh giao dịch.</p>}</details>
    <details className="dl-card"><summary>Tín hiệu phân tích theo mã</summary>
      {report && Object.keys(report.signals).length>0 ? <Table columns={['Mã','Phiên tín hiệu','SMA20','RSI14','ATR14','RVOL20','Động lượng 5 phiên','VSA']}>
        {Object.values(report.signals).map(s=><tr key={s.symbol}><td>{s.symbol}</td><td>{date(s.as_of)}</td>
          <td>{fmt(s.sma20)}</td><td>{fmt(s.rsi)}</td><td>{fmt(s.atr)}</td><td>{fmt(s.rvol)}×</td>
          <td>{fmt(s.momentum*100)}%</td><td>{s.events.join(', ') || '—'}</td></tr>)}</Table>:<p>Chưa đến phiên đầu tiên.</p>}</details>
  </section>;
}
