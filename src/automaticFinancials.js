export function usable(metric){return metric?.status==='READY'&&['number','string'].includes(typeof metric.value)&&String(metric.value).trim()!==''&&Number.isFinite(Number(metric.value));}
export function chooseMetric(id,reviewed,snapshot){
 const accepted=reviewed?.metrics?.[id];
 if(usable(accepted))return {...accepted,provider:'Reviewed',period_label:accepted.period_type||reviewed.period||'TTM',source_kind:'reviewed'};
 const fetched=snapshot?.financials?.metrics?.[id];
 if(snapshot?.cache_status==='STALE')return {status:'UNAVAILABLE',reason_codes:['STALE_PUBLIC_DATA']};
 return fetched||accepted;
}
export function formatFinancial(metric,language='en'){
 if(!usable(metric))return '—';
 const n=Number(metric.value);const locale=language==='vi'?'vi-VN':'en-US';
 if(metric.unit==='currency')return new Intl.NumberFormat(locale,{maximumFractionDigits:2}).format(n)+' '+metric.currency;
 return new Intl.NumberFormat(locale,{maximumFractionDigits:2}).format(n)+' '+(metric.unit==='currency/share'?metric.currency+'/share':metric.unit==='x'?'×':metric.unit||'');
}
export function missingReason(metric,vi=false){
 const code=metric?.reason_codes?.[0];
 const reasons={
  EBITDA_EXPENSE_RECONCILIATION_REQUIRED:['The source does not provide reconciled EBITDA.','Nguồn chưa cung cấp EBITDA đủ cơ sở đối chiếu.'],
  CASH_FLOW_RECONCILIATION_REQUIRED:['Capital expenditure does not reconcile with the cash-flow statement.','Chi đầu tư chưa khớp với tổng lưu chuyển tiền đầu tư.'],
  STALE_PUBLIC_DATA:['The saved data could not be refreshed.','Dữ liệu lưu chưa cập nhật lại được.'],
  INVALID_DENOMINATOR_OR_SIGN:['The source inputs do not support this ratio.','Đầu vào chưa đủ điều kiện tính tỷ số này.'],
  BANK_METRIC_NOT_APPLICABLE:['This industrial-company metric does not apply to a bank.','Chỉ số này không áp dụng theo công thức doanh nghiệp thường cho ngân hàng.'],
 };
 return (reasons[code]||['The source has not supplied compatible inputs.','Nguồn chưa có đủ số liệu cùng kỳ để tính.'])[vi?1:0];
}
