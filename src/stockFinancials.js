import {chooseMetric,usable,formatFinancial,missingReason} from './automaticFinancials';
const definitions={
 'Net revenue':'revenue','Revenue growth (YoY)':'revenue_growth','Cost of goods sold':'cost_of_revenue','Gross profit':'gross_profit','Gross margin':'gross_margin','Operating profit':'operating_profit','Operating margin':'operating_margin','EBITDA':'ebitda','EBITDA margin':'ebitda_margin','Net income used in analysis':'net_income','Parent-attributable profit':'net_income_common','Total consolidated profit':'net_income','Selling expense':'selling_expense','Administrative expense':'administrative_expense','Net margin':'net_margin','Earnings growth (YoY)':'net_income_growth',
 'Total assets':'assets','Total liabilities':'liabilities','Shareholders’ equity':'equity','Current assets':'current_assets','Current liabilities':'current_liabilities','Working capital':'working_capital','Current ratio':'current_ratio','Receivables':'receivables','Short-term debt':'short_debt','Long-term debt':'long_debt','Total debt':'debt','Debt / equity':'debt_equity','Return on equity':'roe','Return on assets':'roa','Debt / EBITDA':'debt_ebitda',
 'Statement operating cash flow':'cfo','Cash flow margin':'cfo_margin','Statement cash conversion':'cfo_net_income','Free cash flow':'free_cash_flow','Capital expenditure':'capex',
 'Market capitalization':'market_cap','P/E (trailing)':'pe','Price / book':'pb','EPS (trailing)':'eps','Shares outstanding':'shares_outstanding','Dividend yield':'dividend_yield'
};
export function bindStockFinancials(groups,reviewed,snapshot,language='en'){
 return groups.map(group=>({...group,rows:group.rows.map(row=>{
  const id=definitions[row.label];let result=id?chooseMetric(id,reviewed,snapshot):null;
  if(row.label==='Price'&&snapshot?.cache_status!=='STALE'&&snapshot?.quote?.status==='READY')result={...snapshot.quote,value:snapshot.quote.price,unit:'currency',provider:snapshot.provider,period_label:snapshot.quote.as_of};
  const ready=usable(result),period=result?.period_label||result?.period_type||'';
  const value=ready&&result.unit==='currency'?new Intl.NumberFormat(language==='vi'?'vi-VN':'en-US',{notation:'compact',maximumFractionDigits:2}).format(Number(result.value))+' '+result.currency:formatFinancial(result,language);
  return {...row,label:row.label==='EPS (trailing)'&&period.startsWith('FY')?'EPS (report period)':row.label,value,
   evidence:ready?[result.provider,period].filter(Boolean).join(' · '):'Unavailable',
   note:ready?formatFinancial(result,language):missingReason(result,language==='vi'),result};
 })}));
}
