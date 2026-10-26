"""Evidence-bearing US/Vietnam annual and interim financial report context.

Extract candidates only; never infer issuer, accounting basis or calendar from
file name, ticker suffix, currency, a vague year, or a report's country.
"""
import re
import unicodedata
from datetime import date

VERSION="us-vn-report-profile-v1"

def fold(value):
 s=unicodedata.normalize("NFKD",str(value or "").lower()).replace("đ","d")
 return " ".join(re.sub(r"[^a-z0-9]+"," ",("".join(ch for ch in s if not unicodedata.combining(ch)))).split())

def unique_evidence(matches):
 values={v for v,_ in matches}
 return (next(iter(values)) if len(values)==1 else None,
         "EXPLICIT" if len(values)==1 else "CONFLICT" if values else "UNKNOWN",
         [{"value":v,"source":s} for v,s in matches[:12]])

def detect_profile(document):
 text=[]
 for s in (document.get("sections") or [])[:160]:
  if s.get("kind")=="table":continue
  for line in str(s.get("text") or "").splitlines()[:45]:
   if len(line)<250:text.append((fold(line),str(s.get("id"))))
 statements=[];standards=[];scopes=[];issuers=[]
 for line,source in text:
  if re.search(r"\b(?:us gaap|u s gaap|generally accepted accounting principles in the united states|accounting principles generally accepted in the united states)\b",line):standards.append(("US_GAAP",source))
  if re.search(r"\b(?:vietnamese accounting standards|chuan muc ke toan viet nam|che do ke toan doanh nghiep viet nam|vas)\b",line):standards.append(("VAS",source))
  if re.search(r"\b(?:consolidated financial statements|bao cao tai chinh hop nhat)\b",line):scopes.append(("CONSOLIDATED",source))
  if re.search(r"\b(?:separate financial statements|parent company financial statements|bao cao tai chinh rieng|bao cao tai chinh cong ty me)\b",line):scopes.append(("SEPARATE",source))
  for pattern,market in ((r"\b(?:nasdaq|nyse|nyse american)\s*[: ]\s*([a-z]{1,6}(?:[.-][a-z])?)\b","US"),
                         (r"\b(?:hose|hsx|hnx|upcom)\s*[: ]\s*([a-z]{3,5})\b","VN")):
   m=re.search(pattern,line)
   if m:issuers.append((market+":"+m[1].upper(),source))
 kinds={"income_statement":r"\b(?:income statements?|statements? of (?:operations|profit or loss|comprehensive income)|bao cao ket qua hoat dong kinh doanh)\b",
  "balance_sheet":r"\b(?:balance sheets?|statements? of financial position|bang can doi ke toan)\b",
  "cash_flow":r"\b(?:statements? of cash flows?|bao cao luu chuyen tien te)\b",
  "equity_changes":r"\b(?:statements? of changes in equity|bao cao bien dong von chu so huu)\b"}
 for line,source in text:
  for key,pattern in kinds.items():
   if re.search(pattern,line):statements.append((key,source))
 basis,basis_status,basis_refs=unique_evidence(standards)
 scope,scope_status,scope_refs=unique_evidence(scopes)
 issuer,issuer_status,issuer_refs=unique_evidence(issuers)
 return {"version":VERSION,"standard":{"value":basis,"status":basis_status,"evidence":basis_refs},
   "scope":{"value":scope,"status":scope_status,"evidence":scope_refs},
   "issuer":{"value":issuer,"status":issuer_status,"evidence":issuer_refs},
   "statement_types":sorted({s for s,_ in statements}),
   "status":"REVIEW_REQUIRED"}

def date_end(raw,market=None):
 value=fold(raw)
 # Unambiguous ISO and written month dates only. Numeric dd/mm vs mm/dd is never guessed.
 iso=re.search(r"\b(20\d\d)[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b",raw)
 if iso:
  try:return date(int(iso[1]),int(iso[2]),int(iso[3])).isoformat()
  except ValueError:return None
 months="january february march april may june july august september october november december".split()
 month_names={m:i+1 for i,m in enumerate(months)}
 month_names.update({m[:3]:i+1 for i,m in enumerate(months)})
 words=r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
 m=re.search(r"\b"+words+r"\s+(\d{1,2}),?\s+(20\d{2})\b",value)
 if m:
  try:return date(int(m[3]),month_names.get(m[1][:3]),int(m[2])).isoformat()
  except (ValueError,TypeError):return None
 m=re.search(r"\b(\d{1,2})\s+"+words+r"\s+(20\d{2})\b",value)
 if m:
  try:return date(int(m[3]),month_names.get(m[2][:3]),int(m[1])).isoformat()
  except (ValueError,TypeError):return None
 return None

def period_header(raw):
 """A candidate time window, never a validated issuer fiscal calendar."""
 value=re.sub(r"\bfy(?=20\d{2}\b)","fy ",fold(raw))
 y=re.search(r"\b(20\d{2})\b",value)
 if not y:return None
 year=y[1];end=date_end(raw)
 q=re.search(r"\bq\s*([1-4])\b|\bquarter\s*([1-4])\b|\bquy\s*([1-4])\b",value)
 qnum=next((x for x in (q.groups() if q else []) if x),None)
 cumulative=bool(re.search(r"\b(?:year to date|ytd|luy ke|since beginning|six months ended|nine months ended|six month period|nine month period|6 months ended|9 months ended)\b",value))
 qperiod=bool(re.search(r"\b(?:three months ended|3 months ended|quarter ended|quy)\b",value))
 annual=bool(re.search(r"\b(?:year ended|fiscal year|financial year|fy|nam tai chinh|nam ket thuc)\b",value))
 if cumulative:kind="YTD"
 elif qnum or qperiod:kind="Q"
 elif annual:kind="FY"
 elif re.fullmatch(r"20\d{2}",value):kind="YEAR_UNSPECIFIED"
 elif end:kind="PERIOD_END_UNSPECIFIED"
 else:return None
 return {"year":year,"period_type":kind,"quarter":int(qnum) if qnum else None,
   "period_end_hint":end,"source_header":str(raw)[:120],
   "status":"PERIOD_CANDIDATE_REQUIRES_FISCAL_CALENDAR"}

def statement_type(section):
 heading=fold(str(section.get("title") or ""))
 matches=[]
 for name,pattern in (("income_statement",r"(income statements?|statements? of operations|ket qua hoat dong kinh doanh)"),
                      ("balance_sheet",r"(balance sheet|financial position|bang can doi ke toan)"),
                      ("cash_flow",r"(cash flow|luu chuyen tien te)")):
  if re.search(pattern,heading):matches.append(name)
 return matches[0] if len(matches)==1 else None
