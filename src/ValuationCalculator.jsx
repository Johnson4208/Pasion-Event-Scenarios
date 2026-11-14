import React,{useState} from 'react';
import Dialog from './Dialog';
import {usePreferences} from './Preferences';
import {usable,formatFinancial} from './automaticFinancials';
import {calculateValuation,calculatorFields} from './valuationCalculators';

export default function ValuationCalculator({method,ticker,metrics,currency,saved,onApply,onClose,onClear}){
 const {language}=usePreferences(),vi=language==='vi',text=(en,vn)=>vi?vn:en;
 const fill={eps:'eps',cash:'cash',debt:'debt',equity:'common_equity'};
 const defaults={};for(const [field,metric] of Object.entries(fill)){const m=metrics[metric];if(usable(m)&&m.currency===currency)defaults[field]=m.value;}
 const [inputs,setInputs]=useState(saved?.inputs||defaults),[error,setError]=useState(''),[result,setResult]=useState(saved||null);
 const errors={MISSING_INPUTS:text('Complete every input, including explicit zero values.','Điền đầy đủ các đầu vào, kể cả số 0 nếu không có.'),POSITIVE_INPUT_REQUIRED:text('EPS, dividends, FCFF, rates and shares must be positive.','EPS, cổ tức, FCFF, tỷ lệ chiết khấu và số cổ phiếu phải dương.'),NONNEGATIVE_INPUT_REQUIRED:text('Cash, debt and claims cannot be negative.','Tiền, nợ vay và các quyền ưu tiên không được âm.'),INVALID_GROWTH:text('Growth must be greater than −100%.','Tăng trưởng phải lớn hơn −100%.'),DISCOUNT_MUST_EXCEED_GROWTH:text('The discount rate must exceed perpetual growth.','Tỷ lệ chiết khấu phải lớn hơn tăng trưởng dài hạn.'),NON_POSITIVE_EQUITY_VALUE:text('These assumptions do not produce a positive equity value.','Các giả định này không tạo ra giá trị vốn chủ dương.')};
 function calculate(e){e.preventDefault();try{const next={...calculateValuation(method,inputs),currency,ticker,calculated_at:new Date().toISOString()};setResult(next);setError('');onApply(next);}catch(e){setError(errors[e.message]||e.message);setResult(null);}}
 return <Dialog title={ticker+' · '+method+' · '+text('Calculator','Công cụ tính')} onClose={onClose} className="ir-calculator-dialog">
  <p>{text('Available report values are prefilled. Enter your own model assumptions; all monetary inputs use ','Số liệu báo cáo có sẵn được tự điền. Nhập các giả định của bạn; mọi đầu vào tiền tệ dùng ')}<strong>{currency}</strong>.</p>
  {method==='DCF'&&<p className="ir-calculator-note">{text('FCFF must be a cash flow available to all capital providers. Operating cash flow minus capex is not automatically substituted for FCFF.','FCFF là dòng tiền dành cho cả chủ nợ và cổ đông. Dòng tiền kinh doanh trừ chi đầu tư không tự được coi là FCFF.')}</p>}
  <form onSubmit={calculate}><div className="ir-calculator-fields">{calculatorFields[method].map(([key,en,vn])=><label key={key}>{text(en,vn)}<input type="number" step="any" required value={inputs[key]??''} onChange={e=>{setInputs({...inputs,[key]:e.target.value});setResult(null);setError('');}}/>{fill[key]&&defaults[key]!==undefined&&<small>{text('Report value','Số liệu báo cáo')}: {formatFinancial(metrics[fill[key]],language)} · {metrics[fill[key]]?.period_label||metrics[fill[key]]?.period_type}</small>}</label>)}</div><div className="ir-calculator-actions"><button type="submit">{text('Calculate scenario','Tính kịch bản')}</button>{saved&&<button type="button" onClick={()=>{onClear();onClose();}}>{text('Remove my scenario','Xóa kịch bản của tôi')}</button>}</div></form>
  {error&&<p role="alert" className="ir-calculator-error">{error}</p>}
  {result&&<section className="ir-calculator-result" role="status"><span>{text('Your scenario estimate','Ước tính theo kịch bản của bạn')}</span><strong>{new Intl.NumberFormat(vi?'vi-VN':'en-US',{maximumFractionDigits:2}).format(result.value)} {currency}/share</strong><small>{result.formula}</small></section>}
  <p className="ir-explorer-caption">{text('This is an editable scenario, not a reviewed valuation or a buy/sell signal. Results are kept for this company during the current view.','Đây là kịch bản có thể chỉnh sửa, chưa phải định giá đã duyệt hay tín hiệu mua/bán. Kết quả được giữ cho công ty này trong lượt xem hiện tại.')}</p>
 </Dialog>;
}
