import {chooseMetric,usable,formatFinancial,missingReason} from './automaticFinancials';
const definitions={
 'Gross revenue':'gross_revenue','Revenue deductions':'revenue_deductions','Non-controlling interest profit':'nci_profit','SG&A':'sga','Total liabilities & equity':'liabilities_equity','Receivables / revenue':'receivables_revenue','Property, plant & equipment':'ppe','Depreciation':'depreciation_cf','Free cash flow margin':'fcf_margin','Free cash flow conversion':'fcf_conversion','Book value / share':'book_value_per_share_fy',
 'Net revenue':'revenue','Revenue growth (YoY)':'revenue_growth','Cost of goods sold':'cost_of_revenue','Gross profit':'gross_profit','Gross margin':'gross_margin','Operating profit':'operating_profit','Operating margin':'operating_margin','EBITDA':'ebitda','EBITDA margin':'ebitda_margin','Net income used in analysis':'net_income','Parent-attributable profit':'net_income_common','Total consolidated profit':'net_income','Selling expense':'selling_expense','Administrative expense':'administrative_expense','Net margin':'net_margin','Earnings growth (YoY)':'net_income_growth',
 'Total assets':'assets','Total liabilities':'liabilities','Shareholders’ equity':'equity','Current assets':'current_assets','Current liabilities':'current_liabilities','Working capital':'working_capital','Current ratio':'current_ratio','Receivables':'receivables','Short-term debt':'short_debt','Long-term debt':'long_debt','Total debt':'debt','Debt / equity':'debt_equity','Return on equity':'roe','Return on assets':'roa','Debt / EBITDA':'debt_ebitda',
 'Statement operating cash flow':'cfo','Cash flow margin':'cfo_margin','Statement cash conversion':'cfo_net_income','Free cash flow':'free_cash_flow','Capital expenditure':'capex',
 'Market capitalization':'market_cap','P/E (trailing)':'pe','Price / book':'pb','EPS (trailing)':'eps','Shares outstanding':'shares_outstanding_fy','Dividend yield':'dividend_yield'
};
export function bindStockFinancials(groups,reviewed,snapshot,language='en'){
 const ids=[...new Set(Object.values(definitions))];
 const available=ids.filter(id=>usable(chooseMetric(id,reviewed,snapshot))).length;
 return groups.map(group=>({...group,rows:group.rows.map(row=>{
  const id=definitions[row.label];let result=id?chooseMetric(id,reviewed,snapshot):null;
  if(row.label==='Price'&&snapshot?.cache_status!=='STALE'&&snapshot?.quote?.status==='READY')result={...snapshot.quote,value:snapshot.quote.price,unit:'currency',provider:snapshot.provider,period_label:snapshot.quote.as_of};
  const coverage={'Available core indicators':available,'Core indicator coverage':ids.length?available/ids.length*100:0,'Available report lines':snapshot?.statements?.reduce((n,t)=>n+t.rows.filter(r=>Object.values(r.values).some(v=>v!==null)).length,0),'Tracked report lines':snapshot?.statement_row_count};
  if(snapshot&&snapshot.cache_status!=='STALE'&&coverage[row.label]!==undefined)result={status:'READY',value:coverage[row.label],unit:row.label==='Core indicator coverage'?'%':row.label==='Available core indicators'?'indicators':'lines',provider:row.label.includes('core')||row.label==='Core indicator coverage'?'Mapped indicators':'Parsed source tables',period_label:snapshot.period_end};
  const unavailable={
   'EBITDA':'Needs expense depreciation/amortization reconciliation; cash-flow adjustment includes goodwill amortization.',
   'EBITDA margin':'Needs reconciled EBITDA.', 'Debt / EBITDA':'Needs reconciled EBITDA.', 'Net debt / EBITDA':'Needs reconciled EBITDA.',
   'Forward P/E':'Needs forecast earnings.', 'Beta (1Y)':'Needs aligned stock and benchmark price histories.',
   'Average volume (10D)':'Needs ten trading sessions of volume.', 'Dividend / share':'Needs dated dividend-per-share disclosures.',
   'Dividend yield':'Needs compatible dividends and price.', 'Payout ratio':'Needs compatible dividend and earnings periods.',
   'Ex-dividend date':'Needs an issuer corporate-action announcement.', 'Market state':'No trading-session status source connected.',
   'Research score':'No research-score methodology configured.', 'Report quality':'No report-quality assessment completed.',
   'Scanned line coverage':'Source tables are parsed; complete PDF scanning coverage has not been measured.',
   'Indexed reports':'No document-index count connected.', 'Operating cash flow (market)':'No separate market-provider cash-flow series.'
  };
  const ready=usable(result),period=result?.period_label||result?.period_type||'';
  const value=ready&&result.unit==='currency'?new Intl.NumberFormat(language==='vi'?'vi-VN':'en-US',{notation:'compact',maximumFractionDigits:2}).format(Number(result.value))+' '+result.currency:formatFinancial(result,language);
  return {...row,label:row.label==='EPS (trailing)'&&period.startsWith('FY')?'EPS (report period)':row.label==='Shares outstanding'?'Shares outstanding (FY end)':row.label==='Book value / share'?'Book value / share (FY end)':row.label==='Depreciation'?'Depreciation / amortization (cash-flow adjustment)':row.label,value,
   evidence:ready?[result.provider,period].filter(Boolean).join(' · '):'Unavailable',
   note:ready?formatFinancial(result,language):(unavailable[row.label]||missingReason(result,language==='vi')),result};
 })}));
}
