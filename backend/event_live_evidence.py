"""Public RSS evidence for PASION Event Scenarios.

Adapted conceptually from SolvAI58 event_probability/sources.py and analysis.py:
bounded fetching, domain caps, near-duplicate clustering, relevance, age, source
quality and directional evidence. Outputs are HEURISTIC EVIDENCE SHARES, never
statistically calibrated outcome probabilities or verified news claims.
No fetched article can enter reviewed F10/F11 evidence automatically.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import math
import re
import threading
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

VERSION="pasion-event-rss-v1"
RSS_BASE="https://news.google.com/rss/search"
HORIZONS={"7 days":7,"30 days":30,"90 days":90,"180 days":180}
CATEGORIES={
 "Banking & Credit":("Credit conditions","Bank lending","Central bank policy"),
 "Business":("M&A activity","Earnings outlook","Hiring plans"),
 "Consumer":("Consumer demand","Household spending","Consumer confidence"),
 "Economy":("Inflation","GDP growth","Labor market"),
 "Energy":("Oil supply","Natural gas","Energy prices"),
 "Geopolitics":("Conflict risk","Sanctions","Trade disruption"),
 "Health":("Drug approvals","Healthcare costs","Public health"),
 "Markets":("Equity volatility","Market liquidity","Risk appetite"),
 "Politics & Policy":("Fiscal policy","Regulation","Trade policy"),
 "Real Estate":("Property prices","Mortgage rates","Commercial demand"),
 "Science":("Research funding","Clinical progress","Technology adoption"),
 "Technology":("AI adoption","Semiconductor supply","Cybersecurity"),
}
# Domain-independent, auditable and intentionally small phrase dictionary.
# The direction is interpreted as "more adverse" versus "more supportive"
# for the factor, not the direction of a stock's price.
PROFILES={
 "Inflation":(("inflation","cpi","consumer prices","lạm phát","giá tiêu dùng"),("accelerates","rises","surges","higher","tăng mạnh","leo thang"),("eases","cools","slows","declines","giảm","hạ nhiệt")),
 "Oil supply":(("oil","opec","brent","crude","dầu","nguồn cung"),("disruption","shortage","cuts supply","supply falls","gián đoạn","thiếu hụt"),("supply recovers","supply rises","output increase","production increases","phục hồi nguồn cung")),
 "Conflict risk":(("conflict","tension","war","military","xung đột","căng thẳng"),("escalates","attack","intensifies","clashes","leo thang","tấn công"),("ceasefire","de-escalation","peace deal","tạm ngừng bắn","hạ nhiệt")),
 "GDP growth":(("gdp","growth","economy","tăng trưởng","kinh tế"),("contracts","slows","recession","declines","suy giảm","suy thoái"),("expands","accelerates","recovers","rebounds","phục hồi","tăng trưởng mạnh")),
 "Central bank policy":(("central bank","fed","federal reserve","interest rates","sbv","ngân hàng nhà nước","lãi suất"),("tightens","rate hike","raises rates","thắt chặt","tăng lãi suất"),("eases","rate cut","cuts rates","nới lỏng","giảm lãi suất")),
 "Consumer demand":(("consumer","spending","retail sales","demand","tiêu dùng","bán lẻ"),("weakens","falls","contracts","declines","suy yếu","giảm mạnh"),("rebounds","grows","accelerates","recovers","phục hồi","tăng trưởng")),
 "Trade disruption":(("tariff","shipping","supply chain","trade","thuế quan","thương mại"),("disruption","restrictions","tariffs rise","blockade","gián đoạn","đình trệ"),("deal signed","restrictions lifted","agreement","resumes","tháo gỡ","khôi phục")),
 "Energy prices":(("energy prices","gas prices","oil prices","giá năng lượng","giá dầu"),("spikes","surges","rises sharply","tăng vọt","leo thang"),("falls","cools","declines","hạ nhiệt","giảm")),
}
DEFAULT_TERMS={
 "Banking & Credit":("banking","credit","loans","ngân hàng","tín dụng"),
 "Business":("business","companies","earnings","doanh nghiệp","lợi nhuận"),
 "Consumer":("consumer","household","retail","tiêu dùng"),
 "Economy":("economy","growth","inflation","kinh tế","lạm phát"),
 "Energy":("energy","oil","natural gas","năng lượng"),
 "Geopolitics":("conflict","sanctions","geopolitics","địa chính trị"),
 "Health":("healthcare","drug","health","y tế"),
 "Markets":("stock market","equities","liquidity","thị trường","thanh khoản"),
 "Politics & Policy":("government","regulation","policy","chính sách"),
 "Real Estate":("property","mortgage","housing","bất động sản"),
 "Science":("research","science","clinical","nghiên cứu"),
 "Technology":("technology","semiconductor","ai","công nghệ"),
}
TRUSTED={"reuters.com":0.88,"apnews.com":0.88,"bloomberg.com":0.84,"ft.com":0.84,
 "wsj.com":0.84,"cnbc.com":0.73,"vietnamplus.vn":0.81,"vneconomy.vn":0.72,
 "vnexpress.net":0.74,"thanhnien.vn":0.70,"tuoitre.vn":0.73}
CACHE={}
LOCK=threading.RLock()
CACHE_SECONDS=900

def clean(value):
 text=re.sub(r"<[^>]*>"," ",str(value or ""))
 return re.sub(r"\s+"," ",text).strip()[:450]

def tokens(value):
 return set(re.findall(r"[a-zà-ỹ0-9]+",clean(value).casefold()))

def _has_phrase(text,phrase):
 return bool(re.search(r"(?<!\w)"+re.escape(phrase.casefold())+r"(?!\w)",text))

def _contains(text,phrases):
 text=text.casefold()
 return any(_has_phrase(text,p) for p in phrases)

def domain(url):
 parsed=urlparse(str(url or ""))
 if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
  return ""
 return parsed.hostname.casefold().removeprefix("www.")

def reliability(publisher):
 if publisher.endswith(".gov") or publisher.endswith(".gov.vn"):
  return 0.92
 for trusted,value in TRUSTED.items():
  if publisher==trusted or publisher.endswith("."+trusted):
   return value
 return 0.55

def parse_date(raw,now):
 try:
  parsed=parsedate_to_datetime(raw)
  if parsed.tzinfo is None:return None
  parsed=parsed.astimezone(timezone.utc)
  if parsed>now+timedelta(minutes=5):return None
  return parsed
 except (TypeError,ValueError,OverflowError):return None

def parse_rss(payload,now):
 if len(payload)>2_000_000:raise ValueError("FEED_TOO_LARGE")
 root=ET.fromstring(payload)
 results=[]
 for item in root.findall(".//channel/item")[:70]:
  def field(name):
   node=item.find(name)
   return (node.text or "").strip() if node is not None else ""
  title=clean(field("title"))
  link=field("link")
  published=parse_date(field("pubDate"),now)
  element=item.find("source")
  publisher_name=clean(element.text) if element is not None else ""
  publisher_url=element.attrib.get("url","") if element is not None else ""
  publisher_domain=domain(publisher_url)
  if not title or not domain(link) or not published or not publisher_domain:continue
  results.append({"title":title,"url":link,"publisher":publisher_name or publisher_domain,
   "publisher_domain":publisher_domain,"published_at":published.isoformat(),
   "summary":clean(field("description"))[:300],
   "source_type":"GOOGLE_NEWS_RSS_UNVERIFIED_PUBLISHER_ATTRIBUTION"})
 return results

def fetch_feed(query,region,now):
 params={"q":query,"hl":"vi","gl":"VN","ceid":"VN:vi"} if region=="VN" else {"q":query,"hl":"en-US","gl":"US","ceid":"US:en"}
 url=RSS_BASE+"?"+urlencode(params)
 req=Request(url,headers={"User-Agent":"PasionResearch/1.0 (public RSS; no crawler)","Accept":"application/rss+xml, application/xml"})
 with urlopen(req,timeout=9) as response:
  if response.geturl().split("?",1)[0]!=RSS_BASE:raise ValueError("RSS_UNEXPECTED_REDIRECT")
  data=response.read(2_000_001)
 return parse_rss(data,now)

def dedupe(items):
 kept=[];counts=Counter();duplicates=0
 for item in sorted(items,key=lambda a:a["published_at"],reverse=True):
  if counts[item["publisher_domain"]]>=3:continue
  title_tokens=tokens(item["title"])
  if any(item["url"]==old["url"] or (len(title_tokens)>=4 and len(title_tokens & tokens(old["title"]))/max(1,len(title_tokens | tokens(old["title"])))>=.78) for old in kept):
   duplicates+=1;continue
  kept.append(item);counts[item["publisher_domain"]]+=1
  if len(kept)>=32:break
 return kept,duplicates

def _direction(text,category,factor):
 profile=PROFILES.get(factor)
 if profile:
  relevant,adverse,supportive=profile
 else:
  relevant=DEFAULT_TERMS.get(category,())+(factor.casefold(),)
  adverse=("disruption","weaker","decline","risk rises","shortage","suy yếu","gián đoạn")
  supportive=("recovery","improves","easing","strengthens","phục hồi","cải thiện")
 if not _contains(text,relevant):return None
 bad=_contains(text,adverse);good=_contains(text,supportive)
 if bad and good:return "mixed"
 if bad:return "weakening"
 if good:return "supportive"
 return "mixed"

def _rounded(values):
 nums=[round(v,1) for v in values]
 nums[1]=round(nums[1]+round(100-sum(nums),1),1)
 return nums

def analyze(category,factor,focus,horizon,fetcher=fetch_feed,now=None):
 if category not in CATEGORIES or factor not in CATEGORIES[category]:raise ValueError("UNKNOWN_FACTOR")
 if horizon not in HORIZONS:raise ValueError("UNKNOWN_HORIZON")
 if not isinstance(focus,str) or len(focus)>75 or any(ord(c)<32 for c in focus):raise ValueError("INVALID_FOCUS")
 focus=focus.strip()
 if focus and not re.fullmatch(r"[\w\s.,&()/-]{1,75}",focus,re.UNICODE):raise ValueError("INVALID_FOCUS")
 now=now or datetime.now(timezone.utc)
 if now.tzinfo is None:raise ValueError("AWARE_TIME_REQUIRED")
 days=min(30,HORIZONS[horizon])
 key=(category,factor,focus.casefold(),horizon)
 if fetcher is fetch_feed:
  with LOCK:
   cached=CACHE.get(key)
   if cached and time.monotonic()-cached[0]<CACHE_SECONDS:
    return {**cached[1],"cache_hit":True}
 terms=PROFILES.get(factor,(DEFAULT_TERMS.get(category,()),))[0]
 query=(" OR ".join('"'+s+'"' for s in terms[:3])+" "+focus).strip()+f" when:{days}d"
 results=[];errors=[]
 for region in ("VN","US"):
  try:results.extend(fetcher(query,region,now))
  except (ValueError,OSError,TimeoutError,ET.ParseError) as exc:
   errors.append({"feed":region,"code":"RSS_UNAVAILABLE","detail":type(exc).__name__})
 cutoff=now-timedelta(days=days)
 usable=[x for x in results if cutoff<=datetime.fromisoformat(x["published_at"])<=now+timedelta(minutes=5)]
 items,duplicates=dedupe(usable)
 bucket={"weakening":0.0,"mixed":0.0,"supportive":0.0};scores=[]
 for item in items:
  sentence=(item["title"]+" "+item["summary"]).casefold()
  signal=_direction(sentence,category,factor)
  if signal is None:continue
  age=(now-datetime.fromisoformat(item["published_at"])).total_seconds()/86400
  fresh=math.exp(-max(0,age)/max(2,days/2))
  source=reliability(item["publisher_domain"])
  factor_terms=PROFILES.get(factor,(DEFAULT_TERMS.get(category,()),))[0]
  relevance=min(1.0,0.50+0.15*sum(_contains(sentence,(v,)) for v in factor_terms[:5]))
  score=round(source*fresh*relevance,5)
  bucket[signal]+=score
  scores.append({**item,"stance":signal,"source_reliability":source,"freshness":round(fresh,3),
   "factor_relevance":round(relevance,3),"weight":score})
 unique=len({x["publisher_domain"] for x in scores})
 directional=sum(x["stance"]!="mixed" for x in scores)
 sufficient=len(scores)>=4 and unique>=3 and directional>=2
 total=sum(bucket.values())
 share=None
 if sufficient and total>0:
  # Evidence-normalized mass; neutral stories contribute only to mixed.
  # No Dirichlet pseudo-counts or equal-baseline when evidence is absent.
  share=_rounded([100*bucket[k]/total for k in ("weakening","mixed","supportive")])
 shares=[{"key":k,"share":share[i] if share else None,
  "evidence_count":sum(x["stance"]==k for x in scores),
  "weight_sum":round(bucket[k],5)} for i,k in enumerate(("weakening","mixed","supportive"))]
 status="EVIDENCE_WEIGHTED_UNCALIBRATED" if share else "INSUFFICIENT_EVIDENCE"
 response={"version":1,"calculation_version":VERSION,"status":status,
  "probability_status":"UNAVAILABLE_NO_OUTCOME_CALIBRATION",
  "display_label":"Evidence-weighted shares (NOT probabilities)",
  "category":category,"factor":factor,"focus":focus,"horizon":horizon,"as_of":now.isoformat(),
  "results":shares,"evidence_count":len(scores),"unique_sources":unique,
  "directional_evidence":directional,"duplicate_count":duplicates,
  "source_errors":errors,"articles":sorted(scores,key=lambda x:x["weight"],reverse=True)[:18],
  "model":{"weight_formula":"source_reliability × exp(-age_days / max(2, lookback_days/2)) × topical_relevance",
   "source_policy":"Publisher attribution comes from Google News RSS; articles have not been verified against original reporting.",
   "deduplication":"Near-duplicate headlines clustered; maximum three articles per publisher.",
   "eligibility":"At least four relevant dated articles, three publisher domains and two directional articles.",
   "share_formula":"100 × sum(article weights assigned to scenario) / sum(all eligible article weights).",
   "limits":"Heuristic topical and directional keywords; negation/irony/causality not fully modeled. Not statistically calibrated; never a Kelly, BUY/SELL or stock P(up) input."},
  "sources_status":"LIVE_RSS" if results and not errors else "PARTIAL_RSS" if results else "RSS_UNAVAILABLE"}
 if fetcher is fetch_feed:
  with LOCK:CACHE[key]=(time.monotonic(),response)
 return {**response,"cache_hit":False}
