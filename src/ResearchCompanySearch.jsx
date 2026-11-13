import React,{useState} from 'react';
import {usePreferences} from './Preferences';
import {companies} from './marketData';

const vietnam=[['FPT','FPT'],['HPG','Hòa Phát'],['VNM','Vinamilk'],['VCB','Vietcombank'],['MBB','MB Bank'],['TCB','Techcombank'],['VIC','Vingroup'],['VHM','Vinhomes'],['SSI','SSI'],['MWG','Thế Giới Di Động'],['HSG','Hoa Sen']].map(([ticker,name])=>({ticker,name,market:'VN',country:'Vietnam'}));
const directory=[...vietnam,...companies.map(c=>({...c,market:'US',country:'United States'}))];
export function researchCompany(query,market='US'){
 const q=query.trim().toUpperCase();
 const found=directory.find(c=>c.ticker===q||c.name.toUpperCase()===q);
 return found||(/^[A-Z0-9.-]{1,16}$/.test(q)?{ticker:q,name:q,market,country:market==='VN'?'Vietnam':'United States'}:null);
}
export function companyMarket(company){
 if(company?.market)return company.market;
 const country=String(company?.country||'').toLowerCase();
 return country.includes('vietnam')||country.includes('việt')||vietnam.some(c=>c.ticker===company?.ticker)?'VN':'US';
}
export default function ResearchCompanySearch({company,query='',onQuery,onChoose}){
 const {language}=usePreferences();const vi=language==='vi';const text=(en,vn)=>vi?vn:en;
 const [market,setMarket]=useState(companyMarket(company));const [error,setError]=useState('');
 const matches=query.trim()?directory.filter(c=>(c.ticker+' '+c.name).toLowerCase().includes(query.toLowerCase())).slice(0,6):[];
 function choose(c){setMarket(c.market);setError('');onChoose(c);onQuery('');}
 function submit(e){e.preventDefault();const exact=directory.find(c=>c.market===market&&c.ticker===query.trim().toUpperCase());const c=exact||(/^[A-Za-z0-9.-]{1,16}$/.test(query.trim())?{ticker:query.trim().toUpperCase(),name:query.trim().toUpperCase(),market,country:market==='VN'?'Vietnam':'United States'}:researchCompany(query,market));if(c)choose(c);else setError(text('Enter a stock ticker or select a company.','Nhập mã cổ phiếu hoặc chọn doanh nghiệp.'));}
 return <div className="ir-company-search"><form onSubmit={submit} aria-label={text('Find company financials','Tìm số liệu doanh nghiệp')}>
  <label>{text('Company or ticker','Doanh nghiệp hoặc mã cổ phiếu')}<input aria-label={text('Financial company search','Tìm công ty để phân tích')} value={query} onChange={e=>{onQuery(e.target.value);setError('');}} placeholder="FPT, HPG, AAPL, MSFT…" autoComplete="off"/></label>
  <label>{text('Market','Thị trường')}<select aria-label={text('Company market','Thị trường của công ty')} value={market} onChange={e=>setMarket(e.target.value)}><option value="VN">{text('Vietnam','Việt Nam')}</option><option value="US">{text('United States','Hoa Kỳ')}</option></select></label>
  <button type="submit">{text('View financials','Xem số liệu')}</button>
 </form>{matches.length>0&&<div className="ir-search-results" aria-label={text('Matching companies','Doanh nghiệp phù hợp')}>{matches.map(c=><button key={c.market+c.ticker} type="button" onClick={()=>choose(c)}><b>{c.ticker}</b> {c.name} <small>{c.market}</small></button>)}</div>}
 {error&&<p role="status">{error}</p>}<small>{text('Selecting a company automatically loads its available financial statements.','Chọn doanh nghiệp để tự động tải số liệu báo cáo tài chính hiện có.')}</small></div>;
}
