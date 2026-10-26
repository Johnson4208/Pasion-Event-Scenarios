const scenarioSets={
  'Geopolitics':{
    'Conflict risk':[
      {name:'Conditions improve',description:'Risk eases and conditions move in a favorable direction.',percent:42,tag:'FAVORABLE',tone:'positive'},
      {name:'Conditions remain broadly stable',description:'No material change from the current baseline.',percent:36,tag:'STABLE',tone:'neutral'},
      {name:'Conditions deteriorate',description:'Risk increases and conditions move in an adverse direction.',percent:22,tag:'ADVERSE',tone:'negative'}
    ],
    'Trade disruption':[
      {name:'Trade flows normalize',description:'Logistics and cross-border activity move toward smoother conditions.',percent:39,tag:'FAVORABLE',tone:'positive'},
      {name:'Disruption remains contained',description:'Current frictions persist without broadening materially.',percent:41,tag:'STABLE',tone:'neutral'},
      {name:'Disruption intensifies',description:'Delays and trade restrictions expand across key routes.',percent:20,tag:'ADVERSE',tone:'negative'}
    ],
    'Sanctions':[
      {name:'Restrictions ease',description:'Policy pressure moderates and market access improves.',percent:27,tag:'FAVORABLE',tone:'positive'},
      {name:'Current measures persist',description:'The policy environment remains close to its present baseline.',percent:51,tag:'STABLE',tone:'neutral'},
      {name:'Restrictions broaden',description:'Additional measures increase operating and market-access risk.',percent:22,tag:'ADVERSE',tone:'negative'}
    ]
  },
  'Economy':{
    'Inflation':[
      {name:'Price pressures cool',description:'Inflation moderates and purchasing conditions improve.',percent:45,tag:'FAVORABLE',tone:'positive'},
      {name:'Inflation stays near baseline',description:'Price growth remains broadly within its current range.',percent:34,tag:'STABLE',tone:'neutral'},
      {name:'Price pressures re-accelerate',description:'Renewed cost pressure weighs on households and businesses.',percent:21,tag:'ADVERSE',tone:'negative'}
    ],
    'GDP growth':[
      {name:'Growth strengthens',description:'Economic activity broadens across demand and investment.',percent:38,tag:'FAVORABLE',tone:'positive'},
      {name:'Growth stays steady',description:'Output remains close to the current trajectory.',percent:43,tag:'STABLE',tone:'neutral'},
      {name:'Growth loses momentum',description:'Demand weakens and activity underperforms the baseline.',percent:19,tag:'ADVERSE',tone:'negative'}
    ],
    'Labor market':[
      {name:'Hiring conditions improve',description:'Employment demand and workforce participation strengthen.',percent:35,tag:'FAVORABLE',tone:'positive'},
      {name:'Labor conditions hold steady',description:'Hiring and employment remain near their current balance.',percent:44,tag:'STABLE',tone:'neutral'},
      {name:'Labor conditions weaken',description:'Hiring slows and labor-market slack increases.',percent:21,tag:'ADVERSE',tone:'negative'}
    ]
  },
  'Markets':{
    'Equity volatility':[
      {name:'Volatility moderates',description:'Market swings ease and risk appetite recovers.',percent:40,tag:'FAVORABLE',tone:'positive'},
      {name:'Volatility remains contained',description:'Trading conditions stay close to the recent range.',percent:37,tag:'STABLE',tone:'neutral'},
      {name:'Volatility rises',description:'Larger price moves signal elevated uncertainty.',percent:23,tag:'ADVERSE',tone:'negative'}
    ],
    'Market liquidity':[
      {name:'Liquidity improves',description:'Market depth strengthens and execution conditions ease.',percent:33,tag:'FAVORABLE',tone:'positive'},
      {name:'Liquidity stays balanced',description:'Trading depth remains close to its present level.',percent:48,tag:'STABLE',tone:'neutral'},
      {name:'Liquidity thins',description:'Reduced depth increases the impact of large trades.',percent:19,tag:'ADVERSE',tone:'negative'}
    ],
    'Risk appetite':[
      {name:'Risk appetite expands',description:'Investors become more willing to hold growth-sensitive assets.',percent:36,tag:'FAVORABLE',tone:'positive'},
      {name:'Risk appetite is mixed',description:'Positioning remains balanced across risk-sensitive assets.',percent:42,tag:'STABLE',tone:'neutral'},
      {name:'Risk appetite contracts',description:'Investors shift toward a more defensive stance.',percent:22,tag:'ADVERSE',tone:'negative'}
    ]
  },
  'Technology':{
    'AI adoption':[
      {name:'Adoption broadens',description:'More organizations move from pilots to practical deployment.',percent:48,tag:'FAVORABLE',tone:'positive'},
      {name:'Adoption progresses gradually',description:'Deployment continues at a measured pace.',percent:35,tag:'STABLE',tone:'neutral'},
      {name:'Adoption faces delays',description:'Cost, infrastructure, or governance barriers slow rollout.',percent:17,tag:'ADVERSE',tone:'negative'}
    ],
    'Semiconductor supply':[
      {name:'Supply availability improves',description:'Capacity and delivery conditions become more favorable.',percent:34,tag:'FAVORABLE',tone:'positive'},
      {name:'Supply remains balanced',description:'Availability broadly matches current demand conditions.',percent:46,tag:'STABLE',tone:'neutral'},
      {name:'Supply constraints deepen',description:'Capacity bottlenecks create wider delivery delays.',percent:20,tag:'ADVERSE',tone:'negative'}
    ],
    'Cybersecurity':[
      {name:'Threat exposure declines',description:'Preparedness and response capabilities improve.',percent:26,tag:'FAVORABLE',tone:'positive'},
      {name:'Threat levels remain elevated',description:'The operating risk environment stays near its current baseline.',percent:49,tag:'STABLE',tone:'neutral'},
      {name:'Threat exposure rises',description:'More frequent or severe incidents increase disruption risk.',percent:25,tag:'ADVERSE',tone:'negative'}
    ]
  },
  'Energy':{
    'Oil supply':[
      {name:'Supply conditions loosen',description:'Availability improves and supply pressure eases.',percent:31,tag:'FAVORABLE',tone:'positive'},
      {name:'Supply remains balanced',description:'Production and demand stay close to the present balance.',percent:46,tag:'STABLE',tone:'neutral'},
      {name:'Supply tightens',description:'Disruptions or production limits increase supply pressure.',percent:23,tag:'ADVERSE',tone:'negative'}
    ],
    'Natural gas':[
      {name:'Availability improves',description:'Storage and delivery conditions strengthen.',percent:37,tag:'FAVORABLE',tone:'positive'},
      {name:'Conditions remain steady',description:'Supply and demand remain close to their current balance.',percent:40,tag:'STABLE',tone:'neutral'},
      {name:'Supply becomes constrained',description:'Weather, logistics, or production limits tighten availability.',percent:23,tag:'ADVERSE',tone:'negative'}
    ],
    'Energy prices':[
      {name:'Price pressure eases',description:'Cost conditions move in a more supportive direction.',percent:41,tag:'FAVORABLE',tone:'positive'},
      {name:'Prices stay within range',description:'Energy prices remain close to their current range.',percent:35,tag:'STABLE',tone:'neutral'},
      {name:'Price pressure increases',description:'Supply or demand shocks push costs higher.',percent:24,tag:'ADVERSE',tone:'negative'}
    ]
  },
  'Politics & Policy':{
    'Fiscal policy':[
      {name:'Policy path becomes clearer',description:'Greater predictability supports planning and investment.',percent:32,tag:'FAVORABLE',tone:'positive'},
      {name:'Policy direction remains mixed',description:'Signals continue without a clear change in direction.',percent:45,tag:'STABLE',tone:'neutral'},
      {name:'Uncertainty increases',description:'Policy shifts complicate business and market expectations.',percent:23,tag:'ADVERSE',tone:'negative'}
    ],
    'Regulation':[
      {name:'Rules become more predictable',description:'Clearer requirements improve planning conditions.',percent:29,tag:'FAVORABLE',tone:'positive'},
      {name:'Regulatory settings hold',description:'Existing requirements remain broadly in place.',percent:50,tag:'STABLE',tone:'neutral'},
      {name:'Compliance burden expands',description:'New requirements increase operating complexity.',percent:21,tag:'ADVERSE',tone:'negative'}
    ],
    'Trade policy':[
      {name:'Trade policy becomes more open',description:'Market access improves and friction eases.',percent:34,tag:'FAVORABLE',tone:'positive'},
      {name:'Current policy framework persists',description:'Trade settings remain close to the present baseline.',percent:43,tag:'STABLE',tone:'neutral'},
      {name:'Trade restrictions broaden',description:'New barriers weigh on cross-border activity.',percent:23,tag:'ADVERSE',tone:'negative'}
    ]
  }
};
const categorySelect=document.querySelector('#category');
const factorSelect=document.querySelector('#factor');
const regionInput=document.querySelector('#region');
const durationSelect=document.querySelector('#duration');
const questionSelect=document.querySelector('#probabilityQuestion');
const scenarioList=document.querySelector('#scenarioList');
const toast=document.querySelector('#toast');
const modal=document.querySelector('#modalBackdrop');
let horizon='short';let toastTimer;
function fillFactors(){const factors=Object.keys(scenarioSets[categorySelect.value]||{});factorSelect.replaceChildren(...factors.map(f=>new Option(f,f)));renderScenarios()}
function getScenarios(){return scenarioSets[categorySelect.value]?.[factorSelect.value]||scenarioSets.Geopolitics['Conflict risk']}
function renderScenarios(){const rows=getScenarios();scenarioList.innerHTML=rows.map((r,i)=>`<article class="scenario-row ${i===0?'lead-row':''}"><div class="scenario-rank">0${i+1}</div><div class="scenario-body"><div class="scenario-top"><div><h3>${r.name}</h3><p>${r.description}</p></div><div class="scenario-value"><strong>${r.percent}</strong><span>%</span></div></div><div class="probability-track"><span class="track-fill ${r.tone}" style="width:${r.percent}%"></span></div><div class="scenario-meta"><span class="outcome-tag ${r.tone}-tag"><i></i> ${r.tag}</span><span class="share-label">of modeled outcomes</span></div></div></article>`).join('');document.querySelector('#totalValue').innerHTML=`${rows.reduce((sum,row)=>sum+row.percent,0)}<span>%</span>`;document.querySelector('#resultContext').textContent=`${factorSelect.value} · ${regionInput.value.trim()||'Global'} · ${durationSelect.value} · ${questionSelect.value.replace('At the end of the period','End of period').replace('Event occurs at any point','Occurrence')}`;document.querySelector('#horizonPill').textContent=durationSelect.value.toUpperCase();document.querySelectorAll('.chart-column').forEach((column,index)=>{column.querySelector('.column-value').textContent=`${rows[index].percent}%`;column.querySelector('i').style.height=`${Math.max(24,rows[index].percent*1.7)}%`})}
function showToast(message){toast.textContent=message;toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),2400)}
function openModal(title,message){document.querySelector('#modalTitle').textContent=title;document.querySelector('#modalText').textContent=message;modal.hidden=false;document.querySelector('#modalOk').focus()}
categorySelect.addEventListener('change',fillFactors);factorSelect.addEventListener('change',renderScenarios);regionInput.addEventListener('input',renderScenarios);durationSelect.addEventListener('change',renderScenarios);questionSelect.addEventListener('change',renderScenarios);
document.querySelectorAll('.horizon-toggle button').forEach(button=>button.addEventListener('click',()=>{horizon=button.dataset.horizon;document.querySelectorAll('.horizon-toggle button').forEach(item=>{item.classList.toggle('selected',item===button);item.setAttribute('aria-pressed',item===button?'true':'false')});durationSelect.replaceChildren(...(horizon==='short'?['30 days','60 days','90 days']:['180 days','1 year','2 years']).map(value=>new Option(value,value)));renderScenarios()}));
document.querySelector('#analyzeButton').addEventListener('click',()=>{const button=document.querySelector('#analyzeButton');button.querySelector('span:first-child').textContent='Preview updated';renderScenarios();showToast('Static sample preview refreshed. No data was fetched.');setTimeout(()=>button.querySelector('span:first-child').textContent='Preview scenarios',1300)});
document.querySelector('#resetButton').addEventListener('click',()=>{categorySelect.value='Geopolitics';fillFactors();factorSelect.value='Conflict risk';regionInput.value='Vietnam';horizon='short';document.querySelectorAll('.horizon-toggle button').forEach((button,index)=>{button.classList.toggle('selected',index===0);button.setAttribute('aria-pressed',index===0?'true':'false')});durationSelect.replaceChildren(...['30 days','60 days','90 days'].map(value=>new Option(value,value)));durationSelect.value='30 days';questionSelect.value='At the end of the period';renderScenarios();showToast('Preview settings reset.')});
document.querySelector('#copyButton').addEventListener('click',async()=>{const text=`${factorSelect.value} · ${regionInput.value.trim()||'Global'} · ${durationSelect.value}\n${getScenarios().map(row=>`${row.name}: ${row.percent}%`).join('\n')}\nTotal: 100% · Illustrative sample only`;try{await navigator.clipboard.writeText(text);showToast('Sample summary copied to clipboard.')}catch{showToast('Clipboard access is unavailable in this preview.')}});
document.querySelector('#dismissBanner').addEventListener('click',()=>document.querySelector('.demo-banner').remove());document.querySelector('#profileButton').addEventListener('click',()=>openModal('Demo profile','This preview does not connect to account settings or save user data.'));document.querySelector('#planButton').addEventListener('click',()=>openModal('PASION Pro preview','This is a static design preview. There is no subscription or payment flow connected.'));document.querySelector('#helpButton').addEventListener('click',()=>openModal('Preview help','Use the filters to change the sample scenario context. The preview values are fixed examples and are not calculated from real-world evidence.'));document.querySelector('#modalClose').addEventListener('click',()=>modal.hidden=true);document.querySelector('#modalOk').addEventListener('click',()=>modal.hidden=true);modal.addEventListener('click',event=>{if(event.target===modal)modal.hidden=true});window.addEventListener('keydown',event=>{if(event.key==='Escape')modal.hidden=true});
const menuButton=document.querySelector('#menuButton');menuButton.addEventListener('click',()=>{const open=document.querySelector('#sidebar').classList.toggle('open');menuButton.setAttribute('aria-expanded',String(open))});document.querySelectorAll('.nav-link').forEach(link=>link.addEventListener('click',event=>{if(link.hash!=='#event-scenarios'){event.preventDefault();showToast('This navigation item is shown for design context only.')}document.querySelector('#sidebar').classList.remove('open');menuButton.setAttribute('aria-expanded','false')}));
renderScenarios();
