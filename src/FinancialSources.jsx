import React,{useEffect,useState} from 'react';
import {usePreferences} from './Preferences';
import './financial-sources.scss';

export default function FinancialSources({market,onMarket,sec,loading,error,onRefresh}) {
 const {language}=usePreferences();
 const vn=language==='vi';
 const text=(en,vi)=>vn?vi:en;
 const [catalog,setCatalog]=useState(null),[email,setEmail]=useState(''),[message,setMessage]=useState(''),[saving,setSaving]=useState(false);
 useEffect(()=>{let active=true;const controller=new AbortController();
  fetch('/api/research/financial-sources',{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{if(active)setCatalog(d);}).catch(()=>{if(active)setMessage(text('Source settings unavailable.','Không tải được cấu hình nguồn.'));});
  return()=>{active=false;controller.abort();};
 },[]);
 async function save(e){e.preventDefault();setSaving(true);setMessage('');
  try{const r=await fetch('/api/admin/financial-sources',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});const d=await r.json();if(!r.ok)throw Error(d.message);setCatalog(d);setEmail('');setMessage(text('Contact saved. You can now load SEC filings.','Đã lưu liên hệ. Bạn có thể tải báo cáo SEC.'));onRefresh();}
  catch(e){setMessage(e.message||text('Unable to save.','Không lưu được.'));}finally{setSaving(false);}
 }
 const errors={SEC_USER_AGENT_NOT_CONFIGURED:text('Set a contact email below to connect to SEC.','Cấu hình email liên hệ bên dưới để kết nối SEC.'),SEC_NETWORK_UNAVAILABLE:text('SEC is unreachable. Retry later.','Không kết nối được SEC. Hãy thử lại sau.'),TICKER_NOT_IN_SEC_UNIVERSE:text('Ticker not found in SEC. Check the market or use reviewed reports.','Không tìm thấy mã trên SEC. Kiểm tra thị trường hoặc dùng báo cáo đã duyệt.'),SEC_REFRESH_COOLDOWN:text('Please wait one minute before refreshing again.','Vui lòng đợi một phút trước khi cập nhật lại.')};
 return <section className="ir-card financial-sources" aria-label={text('Financial data sources','Nguồn dữ liệu tài chính')}>
  <header><div><h2>{text('Financial data sources','Nguồn dữ liệu tài chính')}</h2><p>{text('Choose the reporting source for this company.','Chọn nguồn báo cáo cho doanh nghiệp này.')}</p></div>
   <label>{text('Source','Nguồn')}<select value={market} onChange={e=>onMarket(e.target.value)}><option value="US">SEC · {text('US filings','Báo cáo Mỹ')}</option><option value="VN">{text('Vietnam · reviewed reports','Việt Nam · báo cáo đã duyệt')}</option><option value="reviewed">{text('Reviewed reports only','Chỉ báo cáo đã duyệt')}</option></select></label>
  </header>
  {market==='US'?<>
   <div className="financial-source-status"><span>{loading?text('Loading SEC financial statements…','Đang tải báo cáo SEC…'):sec?text('Filing available','Đã có báo cáo'):text('No SEC filing loaded','Chưa tải được báo cáo SEC')}</span><button type="button" onClick={onRefresh} disabled={loading}>{text('Refresh SEC data','Cập nhật dữ liệu SEC')}</button></div>
   {error&&<p role="status">{errors[error]||text('SEC data unavailable: ','Dữ liệu SEC chưa có: ')+error}</p>}
   {sec&&<p>{sec.issuer} · FY {sec.period_end} · {sec.source_status==='CURATED_2025_SEC_REFERENCE_NOT_AUTO_SCAN'?text('Historical reference; not live','Bản tham khảo lịch sử; không phải dữ liệu trực tiếp'):text('Machine-read; not human-reviewed','Máy trích xuất; chưa được duyệt')} · <a href={sec.filing_url} target="_blank" rel="noopener noreferrer">{text('Original filing','Báo cáo gốc')} ↗</a>{sec.retrieved_at&&<> · {text('Retrieved','Tải lúc')} {new Date(sec.retrieved_at).toLocaleString(vn?'vi-VN':'en-US')}</>}{sec.cache_status==='STALE'&&<strong> · {text('Cached copy is stale; excluded from indicators','Bản lưu đã cũ; không dùng tính chỉ số')}</strong>}</p>}
   {catalog&&!catalog.sec_configured&&<p>{text('SEC needs an application contact email. This contact is sent to SEC with requests.','SEC cần email liên hệ của ứng dụng. Email này được gửi tới SEC khi tải dữ liệu.')}</p>}
   {catalog?.can_configure&&catalog.configuration_origin!=='environment'&&<details><summary>{text('Configure SEC contact','Cấu hình liên hệ SEC')}</summary><form onSubmit={save}><label>{text('Contact email','Email liên hệ')}<input type="email" required maxLength={160} autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/></label><button disabled={saving}>{text('Save connection settings','Lưu cấu hình kết nối')}</button></form></details>}
   {catalog&&!catalog.sec_configured&&!catalog.can_configure&&<p>{text('Ask an administrator to configure SEC from this panel.','Quản trị viên có thể cấu hình SEC tại khung này.')}</p>}
   {catalog?.configuration_origin==='environment'&&<p>{text('Contact configured on the server.','Liên hệ đã được cấu hình trên máy chủ.')}</p>}
  </>:<p>{text('Upload the original statement in Administration → Documents, review its financial observations, then approve them to populate the indicators. Keep consolidated/separate statements, reporting periods and currency scales distinct.','Tải báo cáo gốc tại Quản trị → Tài liệu, kiểm tra và duyệt số liệu để đưa vào các chỉ số. Phân biệt báo cáo hợp nhất/riêng lẻ, kỳ báo cáo và đơn vị tiền tệ.')}</p>}
  {market==='VN'&&<nav aria-label={text('Vietnam filing sources','Nguồn báo cáo Việt Nam')}>{(catalog?.sources||[]).filter(s=>s.market==='VN').map(s=><a key={s.id} href={s.url} target="_blank" rel="noopener noreferrer">{{ssc:text('SSC disclosures','Công bố thông tin UBCKNN'),hnx:'HNX',fiingroup:text('FiinGroup · service not connected','FiinGroup · chưa kết nối dịch vụ')}[s.id]} ↗</a>)}</nav>}
  {message&&<p role="status">{message}</p>}
  <small>{text('Accepted reports take priority. SEC annual data is labeled FY, not TTM. Valuation still requires reviewed inputs and a market price.','Ưu tiên báo cáo đã duyệt. Dữ liệu năm từ SEC được ghi FY, không phải TTM. Định giá vẫn cần đầu vào được duyệt và giá thị trường.')}</small>
 </section>;
}
