"""Bounded public-news retrieval for Pasion event evidence.

Two data channels: Google News search RSS (multiple editorial editions) and
GDELT DOC 2.0 ArtList. Provider failure is partial, never silently rewritten
to verified news. No arbitrary URLs are fetched from user input.
"""
import concurrent.futures
import html
from html.parser import HTMLParser
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode,urlsplit
from urllib.request import HTTPRedirectHandler,Request,build_opener
from event_topic_matcher import normalize
from event_news_queries import COUNTRY_TERMS, REGION_COUNTRIES, REGION_TERMS, VIETNAMESE_TOPICS

# Four Google editions, GDELT, and at most one factor-specific provider job.
# Direct first-party publishing feeds (not RSS syndication). Endpoints verified
# against the publishers' public RSS directories, October 2026.
# Avoid claiming a feed establishes the truth of its individual statements.
OFFICIAL_FEEDS={
 'BLS CPI':('https://www.bls.gov/feed/cpi.rss','www.bls.gov',
            'U.S. Bureau of Labor Statistics','Inflation'),
 'BLS Employment Situation':('https://www.bls.gov/feed/empsit.rss','www.bls.gov',
            'U.S. Bureau of Labor Statistics','Labor market'),
 'EIA Today in Energy':('https://www.eia.gov/rss/todayinenergy.xml','www.eia.gov',
            'U.S. Energy Information Administration','Energy'),
 'EIA Press Releases':('https://www.eia.gov/rss/press_rss.xml','www.eia.gov',
            'U.S. Energy Information Administration','Energy')
}

def _official_jobs(factor,region):
 """Only query official US releases in their declared geography and factor."""
 if region[0]!='United States':return []
 if factor=='Inflation':return ['BLS CPI']
 if factor=='Labor market':return ['BLS Employment Situation']
 if factor in ('Oil supply','Natural gas','Energy prices'):return ['EIA Today in Energy','EIA Press Releases']
 return []

MAX_RESP=1_300_000
_VIETNAM_QUERY='(Vietnam OR "Viet Nam" OR "Việt Nam" OR Hanoi OR "Hà Nội" OR "Ho Chi Minh City" OR "TP.HCM")'
_REGION_ALIASES={
 "world":("World","",None), "global":("World","",None),
 "worldwide":("World","",None), "international":("World","",None),
 "all regions":("World","",None),"earth":("World","",None),
 "asia":("Asia","(Asia OR Asian OR ASEAN OR Southeast Asia)",None),
 "asian":("Asia","(Asia OR Asian OR ASEAN OR Southeast Asia)",None),
 "southeast asia":("Southeast Asia","(ASEAN OR Southeast Asia OR Vietnam OR Thailand OR Indonesia OR Malaysia)",None),
 "asean":("Southeast Asia","(ASEAN OR Southeast Asia OR Vietnam OR Thailand OR Indonesia OR Malaysia)",None),
 "vietnam":("Vietnam",_VIETNAM_QUERY, "VN"),
 "viet nam":("Vietnam",_VIETNAM_QUERY,"VN"),
 "việt nam":("Vietnam",_VIETNAM_QUERY,"VN"),
 "us":("United States","(US OR USA OR United States)", "US"),
 "usa":("United States","(US OR USA OR United States)", "US"),
 "united states":("United States","(US OR USA OR United States)", "US"),
 "america":("United States","(US OR USA OR United States)", "US"),
 "europe":("Europe","(Europe OR European OR EU)",None),
 "european union":("Europe","(Europe OR European Union OR EU)",None),
 "africa":("Africa","(Africa OR African)",None),
 "middle east":("Middle East","(Middle East OR Gulf OR Israel OR Iran)",None),
 "latin america":("Latin America","(Latin America OR South America OR Brazil OR Mexico)",None)
}

class FeedError(Exception):
 def __init__(self,reason,coverage=None):
  super().__init__(reason)
  self.coverage=coverage
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  return None

_OPENER=build_opener(NoRedirect())
_SCOPE_ALIASES=dict(COUNTRY_TERMS)
for _area,_countries in REGION_COUNTRIES.items():
 _SCOPE_ALIASES[_area]=tuple(REGION_TERMS[_area])+tuple(term for country in _countries for term in COUNTRY_TERMS[country])
_ALL_SCOPE_TERMS=frozenset(term for terms in _SCOPE_ALIASES.values() for term in terms)

def geography(value):
 if not isinstance(value,str) or len(value)>120 or any(ch in value for ch in '\r\n\x00'):
  raise ValueError('Invalid focus')
 clean=' '.join(value.strip().split())
 if not clean:return ("World","",None)
 alias=_REGION_ALIASES.get(clean.casefold())
 if alias:return alias
 # Canonical names/demonyms share the same query and scope aliases. City
 # mentions are used to classify articles, never to widen a city-only focus.
 normalized=normalize(clean)
 for country,mentions in COUNTRY_TERMS.items():
  country_forms=mentions[:3] if country=='Vietnam' else mentions[:4] if country=='United States' else mentions
  if normalized==normalize(country) or normalized in country_forms:
   return (country,'"'+country+'"',None)
 # Free-text search is supported but bounded. It cannot become URL or GDELT syntax.
 if not re.fullmatch(r"[\w\s.\-']{1,70}",clean,re.UNICODE):
  raise ValueError('Invalid focus query')
 if len(clean.split())>5:raise ValueError('Focus too broad')
 return (clean,'"'+clean.replace('"','')+'"',None)

def _text(value):
 return re.sub(r'\s+',' ',re.sub(r'<[^>]*>',' ',html.unescape(str(value or '')))).strip()[:500]

def _get(url,accept):
 parsed=urlsplit(url)
 if (parsed.scheme!='https' or parsed.hostname not in ('news.google.com','api.gdeltproject.org','www.federalreserve.gov','mykn.kuehne-nagel.com','www.bls.gov','www.eia.gov')
     or parsed.port not in (None,443) or parsed.username or parsed.password):
  raise FeedError("UNTRUSTED_PROVIDER")
 req=Request(url,headers={'User-Agent':'Pasion-Research/1.1 (public news search)','Accept':accept})
 try:
  with _OPENER.open(req,timeout=7) as response:
   if response.status!=200:raise FeedError(f'NEWS_HTTP_{response.status}' if type(response.status) is int and 100<=response.status<=599 else 'NEWS_HTTP_ERROR')
   raw=response.read(MAX_RESP+1)
 except HTTPError as exc:
  raise FeedError(f'NEWS_HTTP_{exc.code}' if type(exc.code) is int and 100<=exc.code<=599 else 'NEWS_HTTP_ERROR') from exc
 except (OSError,URLError,TimeoutError) as exc:
  raise FeedError("NEWS_NETWORK_OR_PROVIDER_ERROR") from exc
 if len(raw)>MAX_RESP:raise FeedError("NEWS_RESPONSE_TOO_LARGE")
 return raw

def _official_rss(name):
 """Parse published first-party RSS, bound to a fixed host and direct links."""
 if name not in OFFICIAL_FEEDS:raise FeedError('UNKNOWN_OFFICIAL_FEED')
 address,expected_host,source,_=OFFICIAL_FEEDS[name]
 try:root=ET.fromstring(_get(address,'application/rss+xml, application/xml, text/xml'))
 except ET.ParseError as exc:raise FeedError('OFFICIAL_RSS_PARSE_FAILED') from exc
 # Both direct US publisher feeds use RSS2; reject arbitrary embedded links.
 now=datetime.now(timezone.utc);rows=[]
 for node in root.findall('.//channel/item')[:65]:
  title=_text(node.findtext('title'))
  link=str(node.findtext('link') or '').strip()
  parsed=urlsplit(link)
  if parsed.scheme!='https' or parsed.hostname not in (expected_host,expected_host.removeprefix('www.')) or parsed.username or parsed.password:continue
  raw_date=node.findtext('pubDate')
  try:when=parsedate_to_datetime(raw_date).astimezone(timezone.utc)
  except (TypeError,ValueError,OverflowError,AttributeError):continue
  if not title or when>now:continue
  rows.append({'title':title,'description':_text(node.findtext('description')),
               'url':link,'source':source,'published_at':when.isoformat(),
               'provider':name,'time_basis':'PUBLISHED','edition':'US',
               'source_tier':'PRIMARY_OFFICIAL_UNVERIFIED_CLAIM',
               'publisher_domain':expected_host,'source_direct':True})
 return rows

def _rss(query,edition):
 hl,gl,ceid=edition
 address="https://news.google.com/rss/search?"+urlencode({'q':query,'hl':hl,'gl':gl,'ceid':ceid})
 try:root=ET.fromstring(_get(address,'application/rss+xml, application/xml'))
 except ET.ParseError as exc:raise FeedError("RSS_PARSE_FAILED") from exc
 now=datetime.now(timezone.utc);result=[]
 for node in root.findall('.//channel/item')[:65]:
  title=_text(node.findtext('title'))
  url=str(node.findtext('link') or '').strip()
  source=_text(node.findtext('source') or title.rsplit(' - ',1)[-1])
  try:published=parsedate_to_datetime(node.findtext('pubDate') or '').astimezone(timezone.utc)
  except (TypeError,ValueError,OverflowError,AttributeError):continue
  if not title or not source or urlsplit(url).hostname!='news.google.com' or published>now:continue
  result.append({'title':title,'url':url,'source':source,'published_at':published.isoformat(),
    'description':_text(node.findtext('description')),'provider':'Google News RSS',
    'time_basis':'PUBLISHED','edition':gl})
 return result

def _lookback(value):
 if type(value) is not int or not 1<=value<=90:
  raise ValueError('News lookback must be an integer from 1 to 90 days')
 return value

def _gdelt(query,lookback_days=30):
 lookback_days=_lookback(lookback_days)
 # GDELT may reject, throttle, or temporarily return HTML; treat as optional.
 url="https://api.gdeltproject.org/api/v2/doc/doc?"+urlencode({'query':query,'mode':'artlist',
     'format':'json','sort':'datedesc','maxrecords':50,'timespan':f'{lookback_days}d'})
 try:data=json.loads(_get(url,'application/json'))
 except (ValueError,UnicodeError) as exc:raise FeedError("GDELT_INVALID_JSON") from exc
 now=datetime.now(timezone.utc)
 result=[]
 for article in (data.get('articles') or [])[:60]:
  if not isinstance(article,dict):continue
  url=str(article.get('url') or '')
  parsed=urlsplit(url)
  if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:continue
  title=_text(article.get('title'))
  source=_text(article.get('domain') or parsed.hostname)
  raw=str(article.get('seendate') or '')
  try:when=datetime.strptime(raw[:15],'%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
  except ValueError:
   try:when=datetime.strptime(raw[:8],'%Y%m%d').replace(tzinfo=timezone.utc)
   except ValueError:continue
  if not title or when>now:continue
  result.append({'title':title,'url':url,'source':source,'published_at':when.isoformat(),
    'description':'','provider':'GDELT DOC 2.0','time_basis':'FIRST_SEEN','edition':article.get('language') or 'global'})
 return result

def _variants(topic_terms,focus,location,*,factor=None,lookback_days=30):
 lookback_days=_lookback(lookback_days)
 if factor is not None and factor not in VIETNAMESE_TOPICS:
  raise ValueError('Unsupported news factor')
 if 'shipping trade route supply disruption' in topic_terms and location[0]=='Vietnam':
  return [
   (f'("port congestion" OR "shipping delays" OR "Gemalink" OR "Cat Lai") Vietnam when:{lookback_days}d',('en-US','US','US:en')),
   (f'("vessel delays" OR "port congestion" OR "Vietnam ports") Vietnam when:{lookback_days}d',('en-GB','GB','GB:en')),
   (f'("ùn tắc cảng" OR "tàu chờ cảng" OR "chậm thông quan") Việt Nam when:{lookback_days}d',('vi','VN','VN:vi')),
   (f'("Cát Lái" OR "Cái Mép" OR "Gemalink") (ùn tắc OR trễ tàu OR chậm) when:{lookback_days}d',('vi','VN','VN:vi'))]

 # Do not require every word of a long keyword sequence to appear in one article.
 all_terms=[w for w in re.findall(r"[A-Za-z][A-Za-z-]*",topic_terms) if len(w)>2]
 a=all_terms[:3]
 if not a:raise ValueError("No search terms")
 topic='('+' OR '.join(a)+')'
 specialized=' '.join(all_terms[:2])
 geographical=location[1]
 local_query=(topic+' '+geographical).strip()
 fallback=(specialized+' '+geographical).strip()
 if location[0]=='World':
  local_query=topic
  fallback=' '.join(all_terms[:3])
 vietnamese_topic='('+' OR '.join('"'+phrase+'"' for phrase in VIETNAMESE_TOPICS[factor])+')' if factor else topic
 local_vietnamese=(vietnamese_topic+' '+geographical).strip()
 return [(local_query+f' when:{lookback_days}d',('en-US','US','US:en')),
         (fallback+f' when:{lookback_days}d',('en-GB','GB','GB:en')),
         ((topic+' '+geographical).strip()+f' when:{lookback_days}d',('en-SG','SG','SG:en')),
         # Google redirects hl=vi-VN to hl=vi. Use the canonical endpoint
         # because arbitrary provider redirects are deliberately disabled.
         (local_vietnamese+f' when:{lookback_days}d',('vi','VN','VN:vi'))]

def _fed_official():
 # A directly published Federal Reserve RSS channel; unlike aggregators, provenance
 # is the publishing institution itself. Other topics do not use this source.
 address='https://www.federalreserve.gov/feeds/press_monetary.xml'
 try:root=ET.fromstring(_get(address,'application/rss+xml, application/xml'))
 except ET.ParseError as exc:raise FeedError('FED_RSS_PARSE_FAILED') from exc
 results=[];now=datetime.now(timezone.utc)
 for node in root.findall('.//channel/item')[:50]:
  title=_text(node.findtext('title'))
  link=str(node.findtext('link') or '').strip()
  if urlsplit(link).hostname not in ('www.federalreserve.gov','federalreserve.gov'):continue
  try:published=parsedate_to_datetime(node.findtext('pubDate') or '').astimezone(timezone.utc)
  except (TypeError,ValueError,OverflowError,AttributeError):continue
  if not title or published>now:continue
  results.append({'title':title,'url':link,'source':'Board of Governors of the Federal Reserve System',
   'published_at':published.isoformat(),'description':_text(node.findtext('description')),
   'provider':'Federal Reserve official RSS','time_basis':'PUBLISHED','edition':'US',
   'source_tier':'PRIMARY_OFFICIAL_UNVERIFIED_CLAIM'})
 return results

class _PlainText(HTMLParser):
 def __init__(self):
  super().__init__()
  self.parts=[]
  self.silent=0
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style','noscript'):self.silent+=1
 def handle_endtag(self,tag):
  if tag in ('script','style','noscript'):self.silent=max(0,self.silent-1)
 def handle_data(self,data):
  if not self.silent and data.strip():self.parts.append(data.strip())

def _port_report_vietnam():
 """Fetch recent first-party weekly port operations, scoped to Vietnam paragraph.

 This is not an official government feed; report first published by a logistics
 operator. Only URLs constructed from the observed public weekly path pattern.
 A failed report does not contaminate or satisfy other providers.
 """
 now=datetime.now(timezone.utc)
 # Reports dated on Tuesdays; attempt current and preceding two Tuesdays.
 offset=(now.weekday()-1)%7
 tuesday=(now-timedelta(days=offset)).date()
 results=[];reached=False
 for weeks in (0,1,2):
  report_day=tuesday-timedelta(days=7*weeks)
  if (now.date()-report_day).days>30:continue
  link='https://mykn.kuehne-nagel.com/news/article/port-operational-updates-from-'+report_day.strftime('%d-%m-%Y')
  try:payload=_get(link,'text/html');reached=True
  except FeedError:continue
  parser=_PlainText()
  try:parser.feed(payload.decode('utf-8','replace'))
  except (UnicodeError,ValueError):continue
  full=' '.join(parser.parts)
  # Restrict to a local paragraph, not the entire global market report.
  segments=[]
  for m in re.finditer(r'\bVietnam\b',full,re.I):
   excerpt=full[m.end():m.end()+650]
   if re.search(r'\b(?:Cat Lai|Vung Tau|Gemalink|Ho Chi Minh City|Cai Mep)\b',excerpt,re.I):
    segments.append(excerpt)
  if not segments:continue
  content=segments[-1]
  if not re.search(r'congestion|delay|waiting|berth|yard|disrupt',content,re.I):continue
  results.append({'title':'Vietnam port congestion and shipping delays — operational bulletin',
   'description':_text(content),'url':link,'source':'Kuehne+Nagel Sea Logistics',
   'published_at':datetime.combine(report_day,datetime.min.time(),tzinfo=timezone.utc).isoformat(),
   'provider':'Kuehne+Nagel public port operations','time_basis':'REPORT_DATE',
   'source_tier':'INDUSTRY_OPERATOR_UNVERIFIED'})
 if not reached:raise FeedError('PORT_REPORTS_UNAVAILABLE')
 return results

def retrieve(topic_terms,focus,*,factor=None,lookback_days=30):
 lookback_days=_lookback(lookback_days)
 region=geography(focus)
 jobs=[('Google News RSS',query,edition) for query,edition in _variants(topic_terms,focus,region,factor=factor,lookback_days=lookback_days)]
 gdeltquery=('"shipping disruption" Vietnam' if 'shipping trade route supply disruption' in topic_terms and region[0]=='Vietnam' else ' '.join(re.findall(r"[A-Za-z]+",topic_terms)[:2])+' '+region[1]).strip()
 jobs.append(('GDELT DOC 2.0',gdeltquery,None))
 for name in _official_jobs(factor,region):
  jobs.append((name,'',None))
 # Discover Vietnamese government statistics through indexed search, not a
 # first-party RSS connection. Preserve aggregator/unverified provenance.
 if region[0]=='Vietnam' and factor in ('GDP growth','Inflation','Labor market'):
  vietnamese=('GDP OR "tăng trưởng kinh tế" OR "tổng sản phẩm trong nước"' if factor=='GDP growth'
              else 'CPI OR "chỉ số giá tiêu dùng" OR "lạm phát"' if factor=='Inflation'
              else '"lao động" OR "việc làm" OR "thất nghiệp"')
  q='site:nso.gov.vn ('+vietnamese+') when:'+str(lookback_days)+'d'
  jobs.append(('Google News official-site discovery',q,('vi','VN','VN:vi')))
 if region[0]=='Vietnam' and 'shipping trade route supply disruption' in topic_terms:
  jobs.append(('Kuehne+Nagel public port operations','',None))
 if any(word in topic_terms.lower() for word in ('central bank','interest rates','inflation','credit conditions','mortgage rates','monetary policy')):
  jobs.append(('Federal Reserve official RSS','',None))
 results=[];failed=[];succeeded=0;request_results=[]
 def job(spec):
  name,q,edition=spec
  try:return name,edition,(_official_rss(name) if name in OFFICIAL_FEEDS else _port_report_vietnam() if name=='Kuehne+Nagel public port operations' else _fed_official() if name=='Federal Reserve official RSS' else _gdelt(q,lookback_days=lookback_days) if edition is None else _rss(q,edition)),None
  except (FeedError,ValueError,TypeError,KeyError) as e:
   reason=str(e.args[0]) if e.args else 'PROVIDER_ERROR'
   # Do not expose arbitrary provider responses, request URLs or user data.
   if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',reason):reason='PROVIDER_RESPONSE_ERROR'
   return name,edition,[],reason
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  futures=[pool.submit(job,s) for s in jobs]
  for future in concurrent.futures.as_completed(futures):
   name,edition,items,issue=future.result()
   diagnostic={'provider':name,'edition':edition[1] if edition else 'US' if name=='Federal Reserve official RSS' or name in OFFICIAL_FEEDS else 'VN' if name=='Kuehne+Nagel public port operations' else 'global',
               'status':'FAILED' if issue else 'SUCCESS','returned_count':len(items)}
   if issue:diagnostic['reason']=issue
   request_results.append(diagnostic)
   if issue:failed.append({'provider':name,'reason':issue})
   else:succeeded+=1;results.extend(items)
 # No claim of source independence: providers can syndicate the same article.
 coverage={'region':region[0],'scope_query':region[1],'requests':len(jobs),'lookback_days':lookback_days,
   'feed_successes':succeeded,'feed_failures':failed,'raw_results':len(results),
   'providers':sorted({r['provider'] for r in results}),
   'request_results':sorted(request_results,key=lambda entry:(entry['provider'],entry['edition']))}
 if succeeded==0:raise FeedError('ALL_NEWS_FEEDS_UNAVAILABLE',coverage)
 return results,coverage


def scope_relation(title, description, focus, source=''):
 """Keep international context visible without treating it as local evidence."""
 region=geography(focus)[0]
 if region=='World':return 'GLOBAL_SCOPE'
 # RSS often appends the outlet to BOTH headline and snippet. An Iran story
 # published by "Vietnam.vn" is not evidence about Vietnam.
 publisher=normalize(source)
 def article_text(value):
  raw=str(value or '')
  if source:
   raw=re.sub(r'\s*[-–—|:]?\s*'+re.escape(str(source))+r'\s*$','',raw,flags=re.I)
   raw=re.sub(r'^\s*'+re.escape(str(source))+r'\s*[-–—|:]\s*','',raw,flags=re.I)
  text=normalize(raw)
  # Preserve the normalized-suffix safeguard for punctuation/HTML variants.
  if publisher and (text==publisher or text.endswith(' '+publisher)):
   text=text[:-len(publisher)].strip()
  return text,raw
 headline,raw_title=article_text(title)
 snippet,raw_description=article_text(description)
 content=headline+' '+snippet
 padded=' '+content+' '
 def mentioned(term):return ' '+term+' ' in padded
 us_abbreviation=bool(re.search(r'\b(?:US|U\.S\.?)(?=\s|[,:;]|$)',raw_title+' '+raw_description))
 if region=='United States' and us_abbreviation:return 'DIRECT_SCOPE'
 for term in _SCOPE_ALIASES.get(region,(normalize(region),)):
  if mentioned(term):return 'DIRECT_SCOPE'
 # An official source's place of publication alone does not prove the
 # article concerns that place, but Fed-only reporting is external to Vietnam.
 if region!='United States' and 'federal reserve' in normalize(source):return 'EXTERNAL_CONTEXT'
 if us_abbreviation:return 'EXTERNAL_CONTEXT'
 if any(mentioned(term) for term in _ALL_SCOPE_TERMS):return 'EXTERNAL_CONTEXT'
 return 'UNVERIFIED_SCOPE'
