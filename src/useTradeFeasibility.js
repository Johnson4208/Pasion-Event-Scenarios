import {useEffect,useState} from 'react';
import {fetchVersioned,feasibilityView} from './researchApi';

export default function useTradeFeasibility(draft){
 const key=JSON.stringify(draft);const [state,setState]=useState(null),[clock,setClock]=useState(Date.now());
 useEffect(()=>{let active=true;const controller=new AbortController();setState(null);const timer=setTimeout(async()=>{const timeout=setTimeout(()=>controller.abort(),10000);try{const data=await fetchVersioned('/api/trades/feasibility',{method:'POST',headers:{'Content-Type':'application/json'},body:key,signal:controller.signal});if(active)setState({key,data});}catch{if(active)setState({key,data:{status:'UNAVAILABLE',reason_codes:['FEASIBILITY_SERVICE_UNAVAILABLE']}});}finally{clearTimeout(timeout);}},300);return()=>{active=false;clearTimeout(timer);controller.abort();};},[key]);
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[]);
 const value=state?.key===key?state.data:null;
 return feasibilityView(value,clock);
}
