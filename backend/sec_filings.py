"""Read SEC companyfacts (machine-readable XBRL) into an isolated PASION research context.

Only annual issuer-level US-GAAP facts with explicit filing accession, fiscal
calendar, accounting context and unit are admitted. This deliberately does NOT
accept a PDF as verified financial data, publish valuation assumptions or mutate
finance.sqlite3. Filing-source review is still required for investment use.
"""
import json
import os
import re
import tempfile
import threading
import time
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from urllib.request import Request,urlopen

import finance_core
import financial_sources
from examples.apple_sec_2025_case import make as apple_reference_make,URL as APPLE_REFERENCE_URL

SEC_HOST="https://data.sec.gov"
TAG_MAP={
 "revenue":("USD",("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet")),
 "net_income":("USD",("NetIncomeLoss",)),
 "net_income_common":("USD",("NetIncomeLossAvailableToCommonStockholdersBasic",)),
 "cfo":("USD",("NetCashProvidedByUsedInOperatingActivities",)),
 "operating_profit":("USD",("OperatingIncomeLoss",)),
 "weighted_average_shares":("shares",("WeightedAverageNumberOfSharesOutstandingBasic",)),
 "assets":("USD",("Assets",)),
 "liabilities":("USD",("Liabilities",)),
 "equity":("USD",("StockholdersEquity",)),
 "common_equity":("USD",("CommonStockholdersEquity",)),
 "current_assets":("USD",("AssetsCurrent",)),
 "current_liabilities":("USD",("LiabilitiesCurrent",)),
 "cash":("USD",("CashAndCashEquivalentsAtCarryingValue",)),
 "capex":("USD",("PaymentsToAcquirePropertyPlantAndEquipment",)),
 "dividends":("USD",("PaymentsOfDividends",))
}
STOCK=finance_core.STOCK
CACHE={}
LOCK=threading.RLock()
TTL=60*60*6
REQUEST_LOCK=threading.Lock()
LAST_REQUEST=0.0
RESEARCH_LOCK=threading.Lock()
ATTEMPTS={}

class FilingUnavailable(Exception):
 def __init__(self,reason):
  self.reason=reason
  super().__init__(reason)

def fetch_json(url,agent):
 if not financial_sources.valid_agent(agent):
  raise FilingUnavailable("SEC_USER_AGENT_NOT_CONFIGURED")
 global LAST_REQUEST
 with REQUEST_LOCK:
  delay=.25-(time.monotonic()-LAST_REQUEST)
  if delay>0:time.sleep(delay)
  LAST_REQUEST=time.monotonic()
 request=Request(url,headers={"User-Agent":agent,"Accept":"application/json","Accept-Encoding":"identity"})
 try:
  with urlopen(request,timeout=12) as response:
   raw=response.read(12*1024*1024+1)
 except (OSError,TimeoutError) as exc:
  raise FilingUnavailable("SEC_NETWORK_UNAVAILABLE") from exc
 if len(raw)>12*1024*1024:
  raise FilingUnavailable("SEC_RESPONSE_TOO_LARGE")
 try:return json.loads(raw)
 except (ValueError,UnicodeError) as exc:raise FilingUnavailable("INVALID_SEC_RESPONSE") from exc

def ticker_cik(ticker,agent):
 ticker=ticker.upper()
 if not re.fullmatch(r"[A-Z0-9.-]{1,16}",ticker):raise FilingUnavailable("INVALID_TICKER")
 data=fetch_json("https://www.sec.gov/files/company_tickers.json",agent)
 for row in data.values():
  if isinstance(row,dict) and row.get("ticker","").upper()==ticker:
   return int(row["cik_str"]),str(row.get("title") or ticker)
 raise FilingUnavailable("TICKER_NOT_IN_SEC_UNIVERSE")

def rows(gaap,tag,unit):
 item=gaap.get(tag) or {}
 return item.get("units",{}).get(unit,[])

def annual_filings(gaap):
 candidates=[]
 for tag in TAG_MAP["net_income"][1]+TAG_MAP["revenue"][1]:
  for v in rows(gaap,tag,"USD"):
   try:
    if v.get("form")!="10-K" or v.get("fp")!="FY" or not v.get("start"):continue
    days=(date.fromisoformat(v["end"])-date.fromisoformat(v["start"])).days
    if not 335<=days<=385 or v["filed"]>date.today().isoformat():continue
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",v["accn"]):continue
    candidates.append(v)
   except (KeyError,ValueError,TypeError):continue
 # latest two unique fiscal period ends, choose original annual filing, not
 # later repeated comparative XBRL facts with a different (restated) accession.
 by_end={}
 for v in candidates:
  key=(v["start"],v["end"])
  if key not in by_end or v["filed"]<by_end[key]["filed"]:
   by_end[key]=v
 selected=sorted(by_end.values(),key=lambda v:v["end"],reverse=True)[:2]
 if not selected:raise FilingUnavailable("NO_ELIGIBLE_SEC_10K")
 return list(reversed(selected))

def fiscal_quarters(gaap,filing):
 start=date.fromisoformat(filing["start"]);end=date.fromisoformat(filing["end"])
 candidates={}
 for tag in TAG_MAP["revenue"][1]+TAG_MAP["net_income"][1]:
  for v in rows(gaap,tag,"USD"):
   if v.get("form")!="10-Q" or v.get("fp") not in ("Q1","Q2","Q3"):continue
   try:
    day=date.fromisoformat(v["end"])
    if not start<day<end or v["filed"]>date.today().isoformat():continue
    if v.get("fy")!=filing.get("fy"):continue
    q=int(v["fp"][1:])
    previous=candidates.get(q)
    if previous is None or v["filed"]<previous[0]:candidates[q]=(v["filed"],day)
   except (ValueError,TypeError):continue
 if len(candidates)!=3:raise FilingUnavailable("SEC_FISCAL_QUARTERS_INCOMPLETE")
 dates=[candidates[q][1] for q in (1,2,3)]+[end]
 if not start<dates[0]<dates[1]<dates[2]<dates[3]:raise FilingUnavailable("SEC_FISCAL_CALENDAR_CONFLICT")
 if any(not 65<=(b-a).days<=115 for a,b in zip([start-timedelta(days=1)]+dates[:-1],dates)):
  raise FilingUnavailable("SEC_FISCAL_QUARTER_DURATION_INVALID")
 return [d.isoformat() for d in dates]

def find_value(gaap,metric,filing):
 unit,tags=TAG_MAP[metric];stock=metric in STOCK
 for tag in tags:
  candidates=[]
  for v in rows(gaap,tag,unit):
   if v.get("accn")!=filing["accn"] or v.get("end")!=filing["end"]:continue
   if stock and v.get("start"):continue
   if not stock and v.get("start")!=filing["start"]:continue
   if v.get("form")!="10-K":continue
   try:
    number=Decimal(str(v["val"]))
    if number.is_finite():candidates.append((number,v))
   except (ValueError,ArithmeticError,KeyError):continue
  if candidates:
   first=candidates[0][0]
   if any(v[0]!=first for v in candidates):
    raise FilingUnavailable("CONFLICTING_SEC_TAG_VALUE_"+metric.upper())
   return tag,str(first),unit
 return None

def normalize(companyfacts,ticker,cik):
 gaap=companyfacts.get("facts",{}).get("us-gaap",{})
 if not isinstance(gaap,dict) or companyfacts.get("cik")!=cik:
  raise FilingUnavailable("SEC_ENTITY_OR_TAXONOMY_MISMATCH")
 filings=annual_filings(gaap)
 payloads=[]
 for filing in filings:
  quarters=fiscal_quarters(gaap,filing)
  year=filing["end"][:4]
  accession=filing["accn"]
  url="https://www.sec.gov/Archives/edgar/data/"+str(cik)+"/"+accession.replace("-","")+"/"+accession+"-index.html"
  ident="SEC-XBRL-"+ticker+"-"+accession+"-"+filing["end"]
  facts=[]
  for metric in TAG_MAP:
   found=find_value(gaap,metric,filing)
   if not found:continue
   tag,value,unit=found
   kind="INSTANT" if metric in STOCK else "FY"
   facts.append({"id":ident+"-"+metric,"definition_id":metric,"value":value,"scale":"1",
    "period_start":filing["end"] if kind=="INSTANT" else filing["start"],
    "period_end":filing["end"],"period_type":kind,
    "currency":"USD","unit":"shares" if unit=="shares" else "currency",
    "scope":"consolidated","ownership":"SEC_ENTITY_WIDE_NON_DIMENSIONAL",
    "accounting_basis":"US_GAAP","restatement_basis":"SEC_FILING_"+accession,
    "revision":accession,"report_id":ident,"reviewed":True,
    "source_line_label":"us-gaap:"+tag,
    "evidence":{"page":None,"page_kind":"UNPAGINATED_SECTION","section_id":"SEC_COMPANYFACTS",
     "table":"SEC companyfacts XBRL "+accession,"tag":"us-gaap:"+tag}})
  if not facts:raise FilingUnavailable("SEC_NO_MAPPED_FACTS")
  # acceptance time is *this calculation time*, never the historical report date.
  stamp=filing["filed"]+"T23:59:59Z"
  payloads.append({"issuer":{"ticker":ticker,"name":companyfacts.get("entityName",ticker)},
   "calendar":{"year":year,"start":filing["start"],"end":filing["end"],"quarter_ends":quarters},
   "reports":[{"id":ident,"document_id":"SEC-XBRL-"+accession,
     "published_at":stamp,"indexed_at":stamp,"source_url":url,
     "source_kind":"AUTOMATED_SEC_COMPANYFACTS_NOT_HUMAN_REVIEWED"}],
   "facts":facts})
 return payloads,filings[-1]

def statement_tables(companyfacts,filings,cik):
 """Expose all eligible issuer-wide numeric XBRL tags, not only TAG_MAP."""
 periods=[{'id':f['end']+':'+f['accn'],'label':'FY '+f['end'], 'year':int(f['end'][:4]),
           'basis':f['accn'],'description':f.get('form','10-K'),
           'source_url':f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['accn'].replace('-','')}/{f['accn']}-index.html"}
          for f in reversed(filings)]
 result=[]
 for taxonomy,tags in companyfacts.get('facts',{}).items():
  if taxonomy=='dei' or not isinstance(tags,dict):continue
  lines=[]
  for tag,record in tags.items():
   for unit,observations in record.get('units',{}).items():
    values={}; conflicts=[]
    for filing in reversed(filings):
     key=filing['end']+':'+filing['accn']; candidates=set()
     for fact in observations:
      if fact.get('accn')!=filing['accn'] or fact.get('end')!=filing['end'] or fact.get('form')!='10-K':continue
      if fact.get('start') not in (None,filing['start']):continue
      try:
       value=Decimal(str(fact['val']))
       if value.is_finite():candidates.add(value)
      except (KeyError,ValueError,ArithmeticError):continue
     values[key]=str(next(iter(candidates))) if len(candidates)==1 else None
     if len(candidates)>1:conflicts.append(key)
    if not any(v is not None for v in values.values()) and not conflicts:continue
    currency='USD' if unit in ('USD','USD/shares') else None
    lines.append({'id':taxonomy+':'+tag+':'+unit,'code':taxonomy+':'+tag,
                  'label':record.get('label',tag),'description':record.get('description',''),
                  'unit':'currency' if unit=='USD' else 'currency/share' if unit=='USD/shares' else unit,
                  'currency':currency,'values':values,'conflicting_periods':conflicts})
  if lines:result.append({'id':'xbrl-'+taxonomy,'category':'xbrl','title':taxonomy+' · reported XBRL facts',
                         'periods':periods,'rows':lines,'provider':'SEC',
                         'source_url':periods[0]['source_url']})
 return result

def build(ticker,agent):
 cik,name=ticker_cik(ticker,agent)
 data=fetch_json(SEC_HOST+"/api/xbrl/companyfacts/CIK"+str(cik).zfill(10)+".json",agent)
 payloads,last=normalize(data,ticker.upper(),cik)
 with tempfile.TemporaryDirectory(prefix="pasion-sec-xbrl-") as tmp:
  root=Path(tmp)
  for payload in payloads:finance_core.ingest(root,payload,"SEC_MACHINE_XBRL_UNREVIEWED")
  end=payloads[-1]["calendar"]["end"]
  result=finance_core.company(root,ticker.upper(),"FY",end)
  source_details={}
  for metric,record in result["metrics"].items():
   if record.get("source_ids"):
    sources=[finance_core.evidence(root,s) for s in record["source_ids"]]
    source_details[metric]=[{"tag":s.get("source_line_label"),"url":s.get("source_url"),
      "filing":s.get("report_id"),"period_end":s.get("period_end")} for s in sources if s]
  tables=statement_tables(data,annual_filings(data.get('facts',{}).get('us-gaap',{})),cik)
  return {"version":1,"ticker":ticker.upper(),"issuer":result["company"]["name"],
   "period":"FY","period_end":end,"source_status":"SEC_MACHINE_XBRL_NOT_HUMAN_REVIEWED",
   "filing_url":payloads[-1]["reports"][0]["source_url"],
   "filing_accession":last["accn"],
   "source_details":source_details,"financials":result,"statements":tables,
   "statement_row_count":sum(len(t['rows']) for t in tables),
   "review_required_for_valuation":True}

def apple_reference():
 with tempfile.TemporaryDirectory(prefix="pasion-apple-reference-") as tmp:
  root=Path(tmp)
  for year in ("2024","2025"):
   finance_core.ingest(root,apple_reference_make(year),"CURATED_PUBLIC_REFERENCE_NOT_ADMIN_REVIEW")
  result=finance_core.company(root,"AAPL","FY","2025-09-27")
  sources={}
  for metric,record in result["metrics"].items():
   if record.get("source_ids"):
    sources[metric]=[{"tag":record["definition_id"],"url":APPLE_REFERENCE_URL,
     "filing":"Apple 2025 Form 10-K","period_end":record.get("period_end")}]
  return {"version":1,"ticker":"AAPL","issuer":"Apple Inc.","period":"FY","period_end":"2025-09-27",
   "source_status":"CURATED_2025_SEC_REFERENCE_NOT_AUTO_SCAN",
   "filing_url":APPLE_REFERENCE_URL,"filing_accession":"0000320193-25-000079",
   "source_details":sources,"financials":result,"review_required_for_valuation":True}

def research(ticker,refresh=False,root=None):
 root=Path(root) if root is not None else Path(__file__).resolve().parent
 ticker=ticker.upper()
 if not re.fullmatch(r"[A-Z0-9.-]{1,16}",ticker):raise FilingUnavailable("INVALID_TICKER")
 agent,_=financial_sources.settings(root)
 if not financial_sources.valid_agent(agent):
  if ticker=="AAPL":return apple_reference()
  raise FilingUnavailable("SEC_USER_AGENT_NOT_CONFIGURED")
 cache_path=financial_sources.directory(root)/("sec-"+ticker+".json")
 key=(str(root.resolve()),ticker)
 # One preparation at a time also prevents duplicate concurrent refreshes.
 with RESEARCH_LOCK:
  previous=CACHE.get(key)
  if previous is None:
   try:
    entry=json.loads(cache_path.read_text(encoding='utf-8'))
    result=entry['result'];stamp=entry['timestamp']
    if (entry.get('cache_version')==2 and isinstance(stamp,(int,float)) and
        0<=time.time()-stamp and result.get('version')==1 and result.get('ticker')==ticker and
        result.get('source_status')=='SEC_MACHINE_XBRL_NOT_HUMAN_REVIEWED'):
     previous=(stamp,result)
   except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
  def cached(error=None):
   age=time.time()-previous[0]
   return {**previous[1], 'cache_status':'FRESH' if age<TTL else 'STALE',
           'refresh_error':error}
  if not refresh and previous and time.time()-previous[0]<TTL:return cached()
  if time.time()-ATTEMPTS.get(key,0)<60:
   if previous:return cached('SEC_REFRESH_COOLDOWN')
   raise FilingUnavailable('SEC_REFRESH_COOLDOWN')
  ATTEMPTS[key]=time.time()
  try:result=build(ticker,agent)
  except FilingUnavailable as exc:
   if previous:return cached(exc.reason)
   raise
  stamp=time.time()
  result={**result,'retrieved_at':datetime.fromtimestamp(stamp,timezone.utc).isoformat()}
  CACHE[key]=(stamp,result)
  try:financial_sources.atomic_json(cache_path,{'cache_version':2,'timestamp':stamp,'result':result})
  except OSError:
   return {**result,'cache_status':'LIVE','cache_persisted':False}
  return {**result,'cache_status':'LIVE','cache_persisted':True}
