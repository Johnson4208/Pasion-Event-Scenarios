import {companyData,valuationData,portfolioData,comparisonData} from './demoData';
import {marketPulseInstruments} from './marketPulseData';
const nativeFetch=window.fetch.bind(window);
let signedIn=sessionStorage.getItem('pasion-demo-session')==='1';
const user={name:'Demo User',email:'demo@example.com',stars:5,plan:'pro'};
window.fetch=async(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(!url.pathname.startsWith('/api/'))return nativeFetch(input,options);
 const path=url.pathname;let body={};try{body=JSON.parse(options.body||'{}')}catch{}
 let status=200;let data={version:1,status:'READY',items:[],sources:[],accounts:[],message:'Demo only — changes are kept in this browser.'};
 if(path==='/api/session')data={authenticated:signedIn,isAdmin:false,user:signedIn?user:null};
 else if(path==='/api/login'){signedIn=true;sessionStorage.setItem('pasion-demo-session','1');data={authenticated:true,isAdmin:false,user,message:'Demo workspace'}}
 else if(path==='/api/logout'){signedIn=false;sessionStorage.removeItem('pasion-demo-session');data={message:'Signed out'}}
 else if(path==='/api/market/summary')data={version:1,mode:url.searchParams.get('mode')||'demo',status:'READY',quotes:marketPulseInstruments.map(x=>({...x,origin:'SAMPLE',status:'READY',source:'Demo'}))};
 else if(path.startsWith('/api/research/company/'))data=companyData(path.split('/').at(-1));
 else if(path==='/api/research/valuation')data=valuationData(body.ticker);
 else if(path==='/api/portfolio/snapshot')data=portfolioData(options.method==='POST'?body:null);
 else if(path==='/api/research/compare')data=comparisonData(url.searchParams.get('tickers')||'AAPL,MSFT');
 else if(path==='/api/research/watch')data={version:1,intents:[],events:[],acknowledgments:[]};
 else if(path.includes('/events/')){const context=options.method==='POST'?body:Object.fromEntries(url.searchParams);data={...data,...context,generated_at:new Date().toISOString(),items:[],dynamic_scenarios:{ranked_scenarios:[]},coverage:{status:'READY'}};}
 else if(path.includes('assistant'))data={...data,answer:'This is a sample research response. The displayed companies and figures are illustrative.',citations:[]};
 else if(['/api/register','/api/change-password','/api/forgot-password'].includes(path))data={message:'Demo completed. Sign in with demo@example.com and any sample password.'};
 else {status=503;data={version:1,status:'UNAVAILABLE',message:'Demo preview: this live service is not connected.'};}
 return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
};
