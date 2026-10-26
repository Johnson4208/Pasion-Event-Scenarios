import {marketPulseInstruments} from './marketPulseData';
const nativeFetch=window.fetch.bind(window);
let signedIn=false;
const user={name:'Demo User',email:'demo@example.com',stars:5,plan:'pro'};
window.fetch=async(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(!url.pathname.startsWith('/api/'))return nativeFetch(input,options);
 const path=url.pathname;let body={};try{body=JSON.parse(options.body||'{}')}catch{}
 let data={version:1,status:'READY',items:[],sources:[],accounts:[],message:'Demo only — changes are kept in this browser.'};
 if(path==='/api/session')data={authenticated:signedIn,isAdmin:false,user:signedIn?user:null};
 else if(path==='/api/login'){signedIn=true;data={authenticated:true,isAdmin:false,user,message:'Demo workspace'}}
 else if(path==='/api/logout'){signedIn=false;data={message:'Signed out'}}
 else if(path==='/api/market/summary')data={version:1,mode:url.searchParams.get('mode')||'demo',status:'READY',quotes:marketPulseInstruments.map(x=>({...x,origin:'SAMPLE',status:'READY',source:'Demo'}))};
 else if(path.includes('/events/')){const context=options.method==='POST'?body:Object.fromEntries(url.searchParams);data={...data,...context,generated_at:new Date().toISOString(),items:[],dynamic_scenarios:{ranked_scenarios:[]},coverage:{status:'READY'}};}
 else if(path.includes('assistant'))data={...data,answer:'This is a sample research response. The displayed companies and figures are illustrative.',citations:[]};
 return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
};
