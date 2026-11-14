// Interactive scenarios are user calculations, never reviewer-approved valuations.
export function calculateValuation(method,input){
 const n=key=>{const raw=input[key];if(raw===undefined||raw===null||String(raw).trim()===''||!Number.isFinite(Number(raw)))throw Error('MISSING_INPUTS');return Number(raw);};
 const positive=key=>{const value=n(key);if(value<=0)throw Error('POSITIVE_INPUT_REQUIRED');return value;};
 const nonnegative=key=>{const value=n(key);if(value<0)throw Error('NONNEGATIVE_INPUT_REQUIRED');return value;};
 const growth=key=>{const value=n(key)/100;if(value<=-1)throw Error('INVALID_GROWTH');return value;};
 let value,enterprise=null,cashflows=[],formula;
 if(method==='P/E'){
  value=positive('eps')*positive('multiple');formula='EPS × target P/E';
 }else if(method==='Asset-based'){
  value=(n('equity')+n('adjustments'))/positive('shares');formula='(Equity attributable to owners + net asset adjustments) / shares';
 }else{
  const rate=positive('discount')/100,terminal=growth('terminal');
  if(rate<=terminal)throw Error('DISCOUNT_MUST_EXCEED_GROWTH');
  if(method==='Gordon'){
   value=positive('nextDividend')/(rate-terminal);formula='Next annual dividend per share / (cost of equity − perpetual growth)';
  }else if(method==='DCF'||method==='DDM'){
   const annualGrowth=growth('growth');let cash=positive(method==='DCF'?'fcff':'dividend');
   for(let year=1;year<=5;year++){cash*=1+annualGrowth;cashflows.push({year,cash,presentValue:cash/(1+rate)**year});}
   const terminalValue=cash*(1+terminal)/(rate-terminal);
   const present=cashflows.reduce((sum,row)=>sum+row.presentValue,0)+terminalValue/(1+rate)**5;
   if(method==='DCF'){
    enterprise=present;
    value=(present+nonnegative('cash')+nonnegative('nonOperating')-nonnegative('debt')-nonnegative('minority'))/positive('shares');
    formula='PV of 5 years FCFF + PV of terminal value + cash + non-operating assets − debt − minority claims, divided by shares';
   }else{value=present;formula='PV of 5 years dividends per share + PV of terminal dividend value';}
  }else throw Error('UNKNOWN_METHOD');
 }
 if(!Number.isFinite(value)||value<=0)throw Error('NON_POSITIVE_EQUITY_VALUE');
 return {value,enterprise,cashflows,formula,status:'USER_SCENARIO',inputs:{...input}};
}

export const calculatorFields={
 'P/E':[['eps','EPS (report period)','EPS (kỳ báo cáo)'],['multiple','Target P/E multiple','Hệ số P/E mục tiêu']],
 DCF:[['fcff','Base annual FCFF (before debt payments)','FCFF năm cơ sở (trước chi trả nợ)'],['growth','FCFF growth for 5 years (%)','Tăng trưởng FCFF trong 5 năm (%)'],['discount','WACC / discount rate (%)','WACC / tỷ lệ chiết khấu (%)'],['terminal','Perpetual growth (%)','Tăng trưởng dài hạn (%)'],['cash','Cash and equivalents','Tiền và tương đương tiền'],['nonOperating','Other non-operating assets (enter 0 if none)','Tài sản phi hoạt động khác (nhập 0 nếu không có)'],['debt','Borrowings and leases','Nợ vay và thuê tài chính'],['minority','Minority / other senior claims (enter 0 if none)','Lợi ích không kiểm soát / quyền ưu tiên khác (nhập 0 nếu không có)'],['shares','Current share count','Số cổ phiếu hiện tại']],
 DDM:[['dividend','Last annual dividend per share','Cổ tức năm gần nhất trên mỗi cổ phiếu'],['growth','Dividend growth for 5 years (%)','Tăng trưởng cổ tức trong 5 năm (%)'],['discount','Cost of equity (%)','Chi phí vốn chủ sở hữu (%)'],['terminal','Perpetual dividend growth (%)','Tăng trưởng cổ tức dài hạn (%)']],
 Gordon:[['nextDividend','Next annual dividend per share','Cổ tức năm kế tiếp trên mỗi cổ phiếu'],['discount','Cost of equity (%)','Chi phí vốn chủ sở hữu (%)'],['terminal','Perpetual dividend growth (%)','Tăng trưởng cổ tức dài hạn (%)']],
 'Asset-based':[['equity','Equity attributable to owners','Vốn chủ thuộc cổ đông công ty mẹ'],['adjustments','Net asset adjustments (enter 0 if none)','Điều chỉnh tài sản ròng (nhập 0 nếu không có)'],['shares','Current share count','Số cổ phiếu hiện tại']]
};
