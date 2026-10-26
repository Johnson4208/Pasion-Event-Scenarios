/** Small boundary adapters; readiness is always explicit, never inferred from value. */
import {useEffect,useState} from 'react';

export function useCompanyCalculations(ticker,period='TTM') {
  const key=ticker+'|'+period;const [state,setState]=useState(null);
  useEffect(()=>{
    let active=true;const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);
    fetchVersioned('/api/research/company/'+encodeURIComponent(ticker)+'?period='+encodeURIComponent(period),{signal:controller.signal})
      .then(data=>{if(active)setState({key,data});}).catch(()=>{if(active)setState({key,data:null});}).finally(()=>clearTimeout(timer));
    return()=>{active=false;clearTimeout(timer);controller.abort();};
  },[key,ticker,period]);
  return state?.key===key?state.data:null;
}

const metricDefinitions={
 'Net revenue':'revenue','Revenue':'revenue','Revenue growth (YoY)':'revenue_growth','Revenue growth':'revenue_growth',
 'Operating profit':'operating_profit','Operating income':'operating_profit','EBIT':'ebit','EBITDA':'ebitda',
 'Net income used in analysis':'net_income','Net income':'net_income','Total consolidated profit':'net_income',
 'Net margin':'net_margin','EBITDA margin':'ebitda_margin','Total assets':'assets','Total liabilities':'liabilities',
 'Shareholders’ equity':'equity','Current assets':'current_assets','Current liabilities':'current_liabilities',
 'Working capital':'working_capital','Current ratio':'current_ratio','Receivables':'receivables','Total debt':'debt',
 'Debt / equity':'debt_equity','Return on equity':'roe','Return on assets':'roa','Debt / EBITDA':'debt_ebitda',
 'Statement operating cash flow':'cfo','Operating cash flow':'cfo','Cash flow margin':'cfo_margin',
 'Cash & equivalents':'cash','Capital expenditure':'capex','Capital expenditures':'capex',
 'EPS (trailing)':'eps','Earnings per share':'eps','Shares outstanding':'shares_outstanding','Dividends':'dividends',
 'Statement cash conversion':'cfo_conversion','Cash conversion':'cfo_conversion',
};
export function bindCompanyIndicators(groups, data) {
  return groups.map(group=>({...group,rows:group.rows.map(row=>{
    const definition=metricDefinitions[row.label];
    const result=data?.metrics?.[definition]||data?.quality?.diagnostics?.find(d=>d.definition_id===definition);
    return {...row,value:metricText(result),prior:'Unavailable',peer:'Unavailable',
      evidence:result?`${result.origin||'DERIVED'} · ${result.status}`:'Unavailable',
      note:result?.reason_codes?.join(', ')||'No compatible reviewed calculation for this existing field',
      source_ids:result?.source_ids||[],result};
  })}));
}
export async function fetchVersioned(url, options = {}) {
  const response = await fetch(url, {...options, credentials: 'same-origin'});
  if (!response.ok) throw new Error('Research service unavailable');
  const data = await response.json();
  if (!data || data.version !== 1) throw new Error('Unsupported research contract');
  return data;
}

const unavailable = reason => ({status:'UNAVAILABLE', shares:null, quantity:null, error:reason});
export function metricText(metric) {
  if (!metric || metric.status !== 'READY' ||
      !['string','number'].includes(typeof metric.value) || String(metric.value).trim() === '' ||
      !Number.isFinite(Number(metric.value)) || !metric.unit) return '—';
  let unit = metric.unit;
  if (unit === 'currency' || unit === 'currency/share') {
    if (!/^[A-Z]{3}$/.test(metric.currency || '')) return '—';
    unit = metric.currency + (unit === 'currency/share' ? '/share' : '');
  }
  return `${metric.value} ${unit}`;
}
export function feasibilityView(value, clock = Date.now()) {
  if (!value) return unavailable('Checking server feasibility');
  if (value.status !== 'READY') return {...value, shares:null, quantity:null,
    error:Array.isArray(value.reason_codes) ? value.reason_codes.join(' · ') : 'Feasibility unavailable'};
  const expires = Date.parse(value.expires_at);
  if (!Number.isFinite(expires)) return unavailable('Invalid feasibility expiry');
  if (expires <= clock) return {status:'STALE',shares:null,quantity:null,error:'Feasibility snapshot expired; change or recheck the draft.'};
  if (!Number.isSafeInteger(value.quantity) || value.quantity <= 0 ||
      !/^[A-Z]{3}$/.test(value.currency || '') || !Number.isSafeInteger(value.lot) ||
      value.lot <= 0 || value.quantity % value.lot !== 0) return unavailable('Invalid quantity or currency contract');
  const amounts = {};
  for (const key of ['riskBudget','maxLoss','potentialProfit','positionValue','ratio']) {
    const raw = value[key];
    if ((typeof raw !== 'string' && typeof raw !== 'number') || String(raw).trim() === '' || !Number.isFinite(Number(raw)))
      return unavailable('Invalid feasibility amount contract');
    amounts[key] = Number(raw);
  }
  return {...value,...amounts,shares:value.quantity,quantity_unit:'shares',amount_currency:value.currency};
}
