"""Public RSS event-research preview, adapted from SolvAI58 evidence weighting.

Not a probability estimator, trade signal, or approved news claim. No SSRF:
only fixed Google News RSS hosts and constructed queries. Fail closed on
stale/no content; deduplicate publisher-headline groups, not RSS entries.
"""
import hashlib,html,json,math,re,threading,time,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode,urlparse
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError
import event_feed_sources
import event_bayesian
import event_scenario_board
import event_horizons
import event_topic_matcher
import event_direction
import event_forecasts
import event_outcome_data
import event_series_forecasts
import event_scenario_presentation

_TOPICS={
 'Geopolitics': {'Conflict risk':('conflict escalation ceasefire regional security','conflict escalation ceasefire stability'),
                 'Sanctions':('sanctions export restrictions exemptions','sanctions restrictions relief'),
                 'Trade disruption':('shipping trade route supply disruption','trade disruption normalization')},
 'Economy':{'Inflation':('inflation CPI consumer prices central bank','inflation acceleration deceleration'),
            'GDP growth':('GDP growth economic output recession','GDP contraction expansion'),
            'Labor market':('unemployment payroll jobs hiring layoffs','labor deterioration recovery')},
 'Energy':{'Oil supply':('crude oil OPEC oil supply disruption production','oil production shortages oversupply'),
           'Natural gas':('natural gas supply LNG disruptions demand','natural gas supply shortage surplus'),
           'Energy prices':('energy prices electricity fuel costs','energy price surge decline')},
 'Banking & Credit':{'Credit conditions':('bank lending credit conditions tightening','credit tightening easing'),
 'Bank lending':('bank loan demand lending standards','lending contraction expansion'),
 'Central bank policy':('interest rates central bank monetary policy','rates hike cut')},
 'Business':{'M&A activity':('mergers acquisitions deal activity','deal slowdown recovery'),
 'Earnings outlook':('corporate earnings guidance outlook','profit downside upside'),
 'Hiring plans':('corporate hiring freeze expansion','hiring freeze rebound')},
 'Consumer':{'Consumer demand':('retail spending consumer demand','consumer spending weak strong'),
 'Household spending':('household spending disposable income','household spending contraction rebound'),
 'Consumer confidence':('consumer confidence sentiment surveys','consumer confidence weak strong')},
 'Health':{'Drug approvals':('drug approval FDA clinical trial decision','FDA reject approve'),
 'Healthcare costs':('healthcare costs insurance premiums','healthcare inflation relief'),
 'Public health':('public health outbreak health agency','outbreak escalation containment')},
 'Markets':{'Equity volatility':('stock volatility VIX markets','market volatility surge settle'),
 'Market liquidity':('market liquidity funding stress','liquidity tightening improving'),
 'Risk appetite':('investor risk appetite equity markets','risk off risk on')},
 'Politics & Policy':{'Fiscal policy':('government budget stimulus deficit','fiscal tightening stimulus'),
 'Regulation':('financial regulation compliance rule','regulation tightening easing'),
 'Trade policy':('trade tariffs trade agreement negotiations','tariffs escalation reduction')},
 'Real Estate':{'Property prices':('housing home prices real estate','house prices downturn recovery'),
 'Mortgage rates':('mortgage rates housing finance','mortgage rates rising falling'),
 'Commercial demand':('commercial real estate occupancy leasing','commercial property slump recovery')},
 'Science':{'Research funding':('research funding science budget','research grant funding cut increase'),
 'Clinical progress':('clinical trial research outcomes','clinical trial failure success'),
 'Technology adoption':('technology deployment industry adoption','technology adoption slowdown acceleration')},
 'Technology':{'AI adoption':('artificial intelligence enterprise adoption','AI adoption slow accelerate'),
 'Semiconductor supply':('semiconductor chip production capacity','chip shortage surplus'),
 'Cybersecurity':('cybersecurity breaches threats regulation','cybersecurity incidents reduction')}
}
_lock=threading.RLock()
_cache={}
_TTL=900

class Unavailable(Exception):
 def __init__(self,reason,coverage=None):
  super().__init__(reason)
  self.coverage=coverage

def _clean(s):return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html.unescape(s or ''))).strip()[:400]
def _tokens(s):return set(re.findall(r'[a-z0-9]+',s.casefold()))
def _date(s):
 try:
  x=parsedate_to_datetime(s).astimezone(timezone.utc)
  return x
 except (TypeError,ValueError,OverflowError,AttributeError):return None
def _round_shares(xs):
 vals=[round(x*100,1) for x in xs]
 diff=round(100-sum(vals),1)
 vals[max(range(len(vals)),key=lambda i:xs[i])]=round(vals[max(range(len(vals)),key=lambda i:xs[i])]+diff,1)
 return vals

def fetch(query,focus):
 # User text only becomes a query parameter, never a URL or hostname.
 terms=' '.join([query,focus]).strip()[:220]
 params=urlencode({'q':terms,'hl':'en-US','gl':'US','ceid':'US:en'})
 url='https://news.google.com/rss/search?'+params
 req=Request(url,headers={'User-Agent':'Pasion-EventResearch/1.0 (public RSS preview)','Accept':'application/rss+xml,application/xml'})
 try:
  with urlopen(req,timeout=9) as response:
   if response.status!=200:raise Unavailable('NEWS_PROVIDER_HTTP_FAILURE')
   data=response.read(1_000_001)
 except (TimeoutError,OSError,HTTPError,URLError) as exc:raise Unavailable('NEWS_PROVIDER_UNREACHABLE') from exc
 if len(data)>1_000_000:raise Unavailable('NEWS_FEED_TOO_LARGE')
 try:root=ET.fromstring(data)
 except ET.ParseError as exc:raise Unavailable('INVALID_RSS') from exc
 rows=[]
 for node in root.findall('.//channel/item')[:50]:
  title=_clean(node.findtext('title'));link=(node.findtext('link') or '').strip()
  when=_date(node.findtext('pubDate'))
  if not title or not link.startswith('https://') or not when:continue
  if when>datetime.now(timezone.utc):continue
  origin=_clean(node.findtext('source') or title.rsplit(' - ',1)[-1])[:100]
  desc=_clean(node.findtext('description'))
  rows.append({'title':title,'url':link,'source':origin,'published_at':when.isoformat(),'description':desc})
 return rows

def _forecast(category,factor,focus,horizon,basis,now):
 model=event_forecasts.forecast(category,factor,focus,horizon,basis,now)
 if model['status']=='REFERENCE_ESTIMATE_AVAILABLE':return model
 research=event_series_forecasts.forecast(category,factor,focus,horizon,basis,now)
 return research if research.get('status')=='RESEARCH_ESTIMATE_AVAILABLE' else model


def _with_forecast(result, basis, now):
 # Model changes and expiry are checked even when the news snapshot is cached.
 result=json.loads(json.dumps(result))
 result['basis']=basis
 result['outcome_history']=event_outcome_data.coverage(result['category'],result['factor'],result['focus'])
 result['scenario_forecast']=_forecast(result['category'],result['factor'],result['focus'],result['horizon'],basis,now)
 result['scenario_presentation']=event_scenario_presentation.display(result)
 status=result['scenario_forecast'].get('status')
 if status in ('REFERENCE_ESTIMATE_AVAILABLE','RESEARCH_ESTIMATE_AVAILABLE'):
  result['probability_status']='HISTORICAL_REFERENCE_ESTIMATE' if status=='REFERENCE_ESTIMATE_AVAILABLE' else 'RETROSPECTIVE_RESEARCH_ESTIMATE'
  result['horizon_info']['model_status']=result['probability_status']
 elif any(row.get('experimental_probability') for row in result.get('dynamic_scenarios',{}).get('ranked_scenarios',[])):
  result['probability_status']='EXPERIMENTAL_UNCALIBRATED'
 if result['scenario_forecast']['status'] in ('REFERENCE_ESTIMATE_AVAILABLE','RESEARCH_ESTIMATE_AVAILABLE') and result['status']=='UNAVAILABLE':
  result['status']='FORECAST_AVAILABLE'
 return result


def analyze(category,factor,focus='',horizon='30 days',now=None,basis='END_STATE'):
 now=now or datetime.now(timezone.utc)
 if basis not in event_forecasts.BASES:raise ValueError('Unsupported probability basis')
 if factor not in _TOPICS.get(category,{}):raise ValueError('Unsupported category or event factor')
 horizon_info=event_horizons.info(horizon)
 if not isinstance(focus,str) or len(focus)>120 or any(c in focus for c in '\r\n\x00'):raise ValueError('Invalid geographical focus')
 focus=focus.strip()
 event_feed_sources.geography(focus)
 lookback=horizon_info['news_lookback_days']
 key=(category,factor,focus,horizon)
 with _lock:
  saved=_cache.get(key)
  if saved and time.monotonic()-saved[0]<_TTL:return _with_forecast(saved[1],basis,now)
 terms,_=_TOPICS[category][factor]
 try:rows,coverage=event_feed_sources.retrieve(terms,focus,factor=factor,lookback_days=lookback)
 except event_feed_sources.FeedError as exc:
  # A reviewed historical baseline does not depend on today's news transport.
  forecast=_forecast(category,factor,focus,horizon,basis,now)
  if forecast['status'] not in ('REFERENCE_ESTIMATE_AVAILABLE','RESEARCH_ESTIMATE_AVAILABLE'):
   raise Unavailable(str(exc),coverage=getattr(exc,'coverage',None)) from exc
  rows=[]
  coverage={**(getattr(exc,'coverage',None) or {}),'feed_successes':0,'status':'UNAVAILABLE','reason_code':str(exc)}
  coverage.setdefault('requests',None)
 seen=set();items=[];age_limit=lookback
 diagnostics={'retrieved':len(rows),'stale':0,'duplicate':0,'off_topic':0,'accepted':0,'future':0,'invalid':0}
 for row in sorted(rows,key=lambda r:(str(r.get('published_at','')),str(r.get('title','')),str(r.get('source',''))),reverse=True):
  try:
   t=datetime.fromisoformat(row['published_at'])
   age=(now-t).total_seconds()/86400
  except (KeyError,ValueError,TypeError):
   diagnostics['invalid']+=1;continue
  if age<0:
   diagnostics['future']+=1;continue
  if age>age_limit:
   diagnostics['stale']+=1;continue
  # Preserve word order and dated episodes. Repeated headlines on a later day
  # are separate reports; syndication of the same daily headline is one cluster.
  title=event_topic_matcher.normalize(row['title'])
  publisher=event_topic_matcher.normalize(row['source'])
  if publisher and title.endswith(' '+publisher):title=title[:-len(publisher)].strip()
  identity=title+'|'+t.astimezone(timezone.utc).date().isoformat()
  group=hashlib.sha256(identity.encode()).hexdigest()[:16]
  if group in seen:
   diagnostics['duplicate']+=1;continue
  match=event_topic_matcher.inspect(row.get('title'),row.get('description'),factor,terms)
  if not match['eligible']:
   diagnostics['off_topic']+=1;continue
  seen.add(group)
  query_relevance=match['relevance']
  signal=event_direction.inspect(row['title'],row.get('description',''),factor)
  relation=event_feed_sources.scope_relation(row['title'],row.get('description',''),focus,row.get('source',''))
  # First-party BLS national-statistics RSS is US-scope evidence even if its
  # CPI/Employment Situation headline omits the word "United States".
  # Do not grant the same privilege to aggregator search or other publishers.
  if (row.get('source_direct') is True and row.get('publisher_domain')=='www.bls.gov'
      and event_feed_sources.geography(focus)[0]=='United States'
      and factor in ('Inflation','Labor market')):
   relation='DIRECT_SCOPE'
  # Relevance/recency are heuristic research weights, not truth confidence.
  freshness=math.exp(-age/10)
  provenance_multiplier=1.15 if row.get('source_tier')=='PRIMARY_OFFICIAL_UNVERIFIED_CLAIM' else 1.0
  weight=max(.02,query_relevance)*(.25+.75*freshness)*provenance_multiplier
  diagnostics['accepted']+=1
  items.append({**row,'topic_match_reason':match['reason'],'topic_matched_terms':match['matched'],'id':group,'cluster_id':group,'age_days':round(age,1),'relevance':round(query_relevance,3),
    **signal,'geographic_relation':relation,'weight':round(weight,5),'provenance_multiplier':provenance_multiplier,'source_tier':row.get('source_tier','RSS_AGGREGATED_UNVERIFIED'),
    'source_verification':'FIRST_PARTY_PUBLICATION' if row.get('source_direct') is True
        and row.get('publisher_domain') in ('www.bls.gov','www.eia.gov') else 'INDEXED_OR_AGGREGATED_UNVERIFIED',
    'quality_note':'Primary publisher origin does not verify the interpretation of a reported event.'})
 # Source attribution is not a measurement of publisher independence.
 items.sort(key=lambda x:(-x['weight'],x['id']))
 eligible=[x for x in items if x['geographic_relation'] in ('GLOBAL_SCOPE','DIRECT_SCOPE')]
 # Unknown/conditional reporting is not evidence of an unchanged outcome.
 classified=[x for x in eligible if x['direction_status'] in ('DIRECTIONAL','NEUTRAL','MIXED')]
 total=sum(x['weight'] for x in classified)
 bucket=[sum(x['weight'] for x in classified if x['direction']<-.1),
         sum(x['weight'] for x in classified if abs(x['direction'])<=.1),
         sum(x['weight'] for x in classified if x['direction']>.1)]
 shares=_round_shares([weight/total for weight in bucket]) if total else []
 counts=[sum(x['direction']<-.1 for x in classified),sum(abs(x['direction'])<=.1 for x in classified),sum(x['direction']>.1 for x in classified)]
 result={'version':1,'status':'EVIDENCE_AVAILABLE' if items else 'UNAVAILABLE',
  'horizon_info':{**horizon_info,'model_status':'NO_VALIDATED_HORIZON_MODEL'},
  'category':category,'factor':factor,'focus':focus or 'World','horizon':horizon,
  'outcomes':[{'id':key,'share_pct':pct,'evidence_count':count} for key,pct,count in zip(('weakening','mixed','supportive'),shares,counts)],
  'items':items,'filter_diagnostics':diagnostics,'source_count':len(items),'scope_source_count':len(eligible),
  'unclassified_source_count':len(eligible)-len(classified),
  'directional_source_count':sum(x['direction_status']=='DIRECTIONAL' for x in eligible),
  'independent_source_count':None,'coverage':coverage,'generated_at':now.isoformat(),
  'bayesian_forecast':event_bayesian.unavailable(),'calibrated_probability':False,
  'dynamic_scenarios':event_scenario_board.candidates(items,factor,focus,horizon),
  'evidence_sufficiency':'SINGLE_SOURCE_LOW' if len(items)==1 else 'MULTI_STORY_UNVERIFIED' if items else 'NO_EVIDENCE',
  'model':{'name':'reported-event-evidence-v4','direction_method':event_direction.VERSION,
   'cluster_method':'ordered-headline-utc-day-v1',
   'components':['dated public reporting','topic and geographic relevance','conservative reported direction','supporting and opposing stories'],
   'calibrated_probability':False,'label':'Evidence balance',
   'warning':'Reported evidence is not an event probability. Forecast horizon is research context, not a validated time-to-event model.'},
  'probability_status':'UNAVAILABLE_NO_CALIBRATED_EVENT_MODEL'}
 if not items:result['reason_code']='INSUFFICIENT_RECENT_DISTINCT_STORIES'
 with _lock:_cache[key]=(time.monotonic(),result)
 return _with_forecast(result,basis,now)
