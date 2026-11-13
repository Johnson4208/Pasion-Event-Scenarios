import React,{useEffect,useState} from 'react';
import {usePreferences} from './Preferences';
import './financial-sources.scss';

export default function FinancialSources({market,snapshot,loading,error,onRefresh}) {
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
 const errors={
  SEC_USER_AGENT_NOT_CONFIGURED:text('An administrator needs to save a contact email once to enable automatic SEC downloads.','Quản trị viên cần lưu email liên hệ một lần để bật tải SEC tự động.'),
  SEC_NETWORK_UNAVAILABLE:text('SEC could not be reached. Try again later.','Chưa kết nối được SEC. Hãy thử lại sau.'),
  TICKER_NOT_IN_SEC_UNIVERSE:text('This ticker is not in SEC. Check its market.','Không tìm thấy mã trên SEC. Hãy kiểm tra thị trường.'),
  NO_PUBLIC_FINANCIALS:text('No financial statements were returned for this ticker. Check the ticker and market.','Nguồn chưa trả báo cáo cho mã này. Kiểm tra mã và thị trường.'),
  UNSUPPORTED_REPORT_TEMPLATE:text('This company uses a financial report format that is not yet supported.','Mẫu báo cáo của doanh nghiệp này chưa được hỗ trợ.'),
  PROVIDER_UNAVAILABLE:text('The data provider is temporarily unavailable.','Chưa kết nối được nhà cung cấp dữ liệu.'),
  REFRESH_COOLDOWN:text('Please wait one minute before refreshing again.','Vui lòng đợi một phút trước khi cập nhật lại.'),
  SEC_REFRESH_COOLDOWN:text('Please wait one minute before refreshing again.','Vui lòng đợi một phút trước khi cập nhật lại.'),
 };
 const ready=snapshot&&snapshot.cache_status!=='STALE';
 return <section className="financial-sources" aria-label={text('Financial data sources','Nguồn dữ liệu tài chính')}>
  <div className="financial-source-status" role="status"><span><i className={ready?'is-ready':''}/>{loading?text('Loading company financials…','Đang tải số liệu doanh nghiệp…'):ready?`${snapshot.provider} · ${snapshot.period} ${snapshot.period_end} · ${text('Financials loaded automatically','Đã tự động tải số liệu')}`:text('Financial data is not available yet','Chưa tải được số liệu tài chính')}</span><button type="button" onClick={onRefresh} disabled={loading}>{text('Refresh data','Cập nhật')}</button></div>
  {error&&<p className="financial-source-error">{errors[error]||text('Unable to load this source: ','Chưa tải được nguồn này: ')+error}</p>}
  {snapshot?.cache_status==='STALE'&&<p>{text('The saved copy is stale; its values are excluded until refresh succeeds.','Bản lưu đã cũ; chưa sử dụng số liệu cho đến khi cập nhật thành công.')}</p>}
  <details><summary>{text('Data details & connection settings','Chi tiết dữ liệu và cấu hình kết nối')}</summary>
   {snapshot&&<p>{snapshot.issuer} · {snapshot.provider} · {snapshot.period} {snapshot.period_end} · <a href={snapshot.source_url} target="_blank" rel="noopener noreferrer">{text('View source','Xem nguồn')} ↗</a>{snapshot.retrieved_at&&<> · {text('Retrieved','Tải lúc')} {new Date(snapshot.retrieved_at).toLocaleString(vn?'vi-VN':'en-US')}</>}</p>}
   <p>{text('Financial values fill the table automatically. Each row shows its reporting period and source; reviewed values take priority for that metric. Annual FY figures are not trailing twelve months (TTM).','Số liệu tự điền vào bảng. Mỗi dòng ghi kỳ báo cáo và nguồn; số liệu đã duyệt được ưu tiên cho từng chỉ tiêu. FY là số liệu năm, không phải 12 tháng gần nhất (TTM).')}</p>
   {snapshot?.warnings?.length>0&&<p>{text('Some source sections could not be loaded. Available metrics are still shown.','Một số phần của nguồn chưa tải được. Các chỉ tiêu đã có dữ liệu vẫn được hiển thị.')}</p>}
   {market==='US'&&<>
    {catalog&&!catalog.sec_configured&&<p>{text('SEC requires an application contact email, sent with data requests.','SEC yêu cầu email liên hệ của ứng dụng, gửi kèm các yêu cầu tải dữ liệu.')}</p>}
    {catalog?.can_configure&&catalog.configuration_origin!=='environment'&&<form onSubmit={save}><label>{text('Contact email','Email liên hệ')}<input type="email" required maxLength={160} autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/></label><button disabled={saving}>{text('Save connection settings','Lưu cấu hình kết nối')}</button></form>}
    {catalog&&!catalog.sec_configured&&!catalog.can_configure&&<p>{text('Ask an administrator to save the SEC contact email.','Nhờ quản trị viên lưu email liên hệ SEC.')}</p>}
    {catalog?.configuration_origin==='environment'&&<p>{text('Contact configured on the server.','Liên hệ đã được cấu hình trên máy chủ.')}</p>}
   </>}
   <small>{text('Public source data has not been reviewed in PASION. Valuation models additionally need reviewed assumptions and suitable market prices.','Dữ liệu nguồn công khai chưa được duyệt trong PASION. Mô hình định giá cần thêm giả định được duyệt và giá thị trường phù hợp.')}</small>
  </details>
  {message&&<p role="status">{message}</p>}
 </section>;
}
