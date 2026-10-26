"""Conservative, offline financial table indexing after document extraction.

This module only produces candidates, never accepted accounting facts.
Every candidate must have an exact source table cell, a supported definition,
an explicit year column and an unambiguous numeric value. Other text stays
searchable but is not silently interpreted as a financial fact.
"""
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
import financial_locale
import financial_report_context
import financial_table_layout

VERSION="financial-index-v1"
LABELS={
 "revenue":("revenue","net revenue","total revenue","net sales","doanh thu thuan"),
 "net_income":("net income","net profit","profit for the year","profit after tax","loi nhuan sau thue","loi nhuan rong"),
 "net_income_common":("net income attributable to shareholders","net income attributable to ordinary shareholders","profit attributable to owners of the parent","loi nhuan sau thue cua co dong cong ty me"),
 "operating_profit":("operating profit","operating income","loi nhuan thuan tu hoat dong kinh doanh"),
 "cfo":("net cash from operating activities","net cash provided by operating activities","cash flows from operating activities","luu chuyen tien thuan tu hoat dong kinh doanh"),
 "capex":("purchase of property plant and equipment","payments to acquire property plant and equipment","tien chi mua sam xay dung tai san co dinh"),
 "assets":("total assets","tong cong tai san","tong tai san"),
 "liabilities":("total liabilities","tong no phai tra","no phai tra"),
 "equity":("total equity","total shareholders equity","total stockholders equity","von chu so huu"),
 "current_assets":("total current assets","current assets","tai san ngan han"),
 "current_liabilities":("total current liabilities","current liabilities","no ngan han"),
 "cash":("cash and cash equivalents","tien va cac khoan tuong duong tien"),
 "debt":("total borrowings","total interest bearing debt","vay va no thue tai chinh"),
 "receivables":("trade receivables","accounts receivable net","cac khoan phai thu khach hang"),
}
STOCK={"assets","liabilities","equity","current_assets","current_liabilities","cash","debt","receivables"}
ALIASES={}

def normalized(s):
 s=unicodedata.normalize("NFKD",str(s or "")).casefold()
 s="".join(c for c in s if not unicodedata.combining(c))
 return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())

for metric,names in LABELS.items():
 for name in names:
  key=normalized(name)
  if key in ALIASES and ALIASES[key]!=metric:raise RuntimeError("Overlapping financial labels")
  ALIASES[key]=metric

def exact_metric(cell):
 text=normalized(cell)
 text=re.sub(r"^\d{1,3}\s+", "",text)  # statement line numbers, never financial values
 return ALIASES.get(text)

def year_column(cell):
 text=str(cell or "").strip()
 if re.fullmatch(r"20\d{2}",text):return text
 match=re.fullmatch(r"(?:year ended|fiscal year|fy|as at|as of|year)\s*(?:on|at|:)?\s*(?:31[/.-]12[/.-])?(20\d{2})",text,re.I)
 if match:return match[1]
 match=re.fullmatch(r"(?:31[/.-]12[/.-])(20\d{2})",text)
 return match[1] if match else None

def number(cell):
 value=str(cell or "").strip().replace("\u00a0"," ")
 if not value or value in ("-","—","N/A","n/a","*"):return None
 negative=value.startswith("(") and value.endswith(")")
 if negative:value=value[1:-1].strip()
 # commas are allowed only as thousands separators; dot is a decimal point.
 # Reject footnotes, embedded currencies, shorthand, OCR substitutions.
 if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?",value):return None
 try:
  result=Decimal(value.replace(",",""))
  if negative:result=-result
  if result.is_finite() and abs(result)<Decimal("1e25"):return str(result)
 except InvalidOperation:pass
 return None

def scan(document):
 if document.get("status") not in (None,"ready","processing"):return {"version":VERSION,"status":"UNAVAILABLE","candidates":[],"warnings":["DOCUMENT_NOT_READY"]}
 candidates=[]
 report_profile=financial_report_context.detect_profile(document)
 catalog=financial_locale.source_catalog(document)
 for section in (document.get("sections") or [])[:2000]:
  grid=section.get("table")
  if not isinstance(grid,list) or len(grid)<2:continue
  unit=financial_locale.identify(document,section,catalog)
  statement_type=financial_report_context.statement_type(section)
  columns,header_row,header_issues=financial_table_layout.headers(grid)
  if header_row is None:continue
  for row_idx,row in enumerate(grid[header_row+1:],start=header_row+1):
   if not isinstance(row,list) or not row:continue
   metric=exact_metric(row[0])
   if metric is None:continue
   for col,period in columns.items():
    year=period['year']
    if col>=len(row):continue
    raw=str(row[col] or "").strip()
    value=financial_locale.parse_number(raw,unit['locale']) if unit['locale'] else number(raw)
    if value is None:continue
    key=":".join([str(section.get("id")),str(row_idx),str(col),metric,year])
    candidates.append({"id":hashlib.sha256(key.encode()).hexdigest()[:24],
      "definition_id":metric,"value":value,"source_text":raw,
      "currency":unit['currency'],"scale":unit['scale'],"unit_status":unit['status'],"unit_evidence":unit['evidence'],
      "normalized_value":str(Decimal(value)*Decimal(unit['scale'])) if unit['scale'] is not None else None,
      "year":year,"period_type":"INSTANT" if metric in STOCK else period['period_type'],
      "period_candidate":period,"statement_type":statement_type,
      "layout_warnings":header_issues,
      "unit":"currency","section_id":section.get("id"),"page":section.get("page"),
      "table":str(section.get("title") or "Financial table")[:200],
      "row":row_idx,"column":col,"row_label":str(row[0])[:160],
      "column_label":str(grid[header_row][col])[:100],
      "classification":"CANDIDATE_REQUIRES_CONTEXT_AND_HUMAN_REVIEW"})
 # Duplicate definitions for same year may be comparisons/scopes. Never choose one.
 groups={}
 for c in candidates:groups.setdefault((c["year"],c["definition_id"]),[]).append(c)
 for entries in groups.values():
  for c in entries:c["ambiguous"]=len(entries)>1
 candidates=candidates[:500]
 return {"version":VERSION,"status":"CANDIDATES_FOUND" if candidates else "NO_EXPLICIT_FINANCIAL_TABLE_CANDIDATES",
  "candidates":candidates,"candidate_count":len(candidates),"report_profile":report_profile,
  "warnings":[ "No accepted facts have been created. Confirm issuer, fiscal calendar, currency, scale, accounting perimeter, source cells and publication time.",
               "OCR/text outside a year-headed table is not automatically promoted to a financial fact.",
               "Year headers do not prove a fiscal year ends on December 31.",
               "VND/USD and denomination are only suggested from explicit source declarations; missing or conflicting units must be reviewed.",
               "Potential duplicates are withheld from automatic staging."]}
