"""Conservative multi-row annual/quarter/YTD table-header recognition.

Do not forward-fill merged years into adjacent columns without explicit source
coordinates or the original span structure. Return only columns whose header
has one unambiguous fiscal interpretation.
"""
import re
import financial_report_context as context

def _year(text):
 m=re.fullmatch(r"20\d{2}",str(text or "").strip())
 return m[0] if m else None

def _quarter(text):
 s=context.fold(text)
 m=re.fullmatch(r"(?:q|quarter|quy)\s*([1-4])",s)
 return int(m[1]) if m else None

def _ytd(text):
 s=context.fold(text)
 return bool(re.search(r"\b(?:ytd|year to date|luy ke|six months|nine months|6 months|9 months)\b",s))

def headers(grid):
 """Returns ({column index: time candidate}, last header-row index, issues)."""
 if not isinstance(grid,list) or len(grid)<2:return {},None,["NO_TABLE"]
 width=max((len(r) for r in grid[:4] if isinstance(r,list)),default=0)
 if width<2:return {},None,["NO_COLUMNS"]
 columns={};issues=[];last=-1
 for col in range(1,min(width,20)):
  parts=[(i,str(row[col]).strip()) for i,row in enumerate(grid[:4]) if isinstance(row,list) and col<len(row) and str(row[col] or "").strip()]
  candidates=[]
  for index,value in parts:
   period=context.period_header(value)
   if period:candidates.append((index,period))
  # A fiscal year in the upper row and an explicit Q/YTD qualifier in
  # the lower row is a composite header. Do not use a year from another column.
  years={p["year"] for _,p in candidates}
  if len(years)>1:
   issues.append({"column":col,"code":"MULTIPLE_YEARS_IN_COLUMN"});continue
  if not candidates:continue
  year=next(iter(years))
  kinds={p["period_type"] for _,p in candidates if p["period_type"] not in ("YEAR_UNSPECIFIED","PERIOD_END_UNSPECIFIED")}
  qtokens={q for _,v in parts if (q:=_quarter(v)) is not None}
  ytd=any(_ytd(v) for _,v in parts)
  fy=any(context.fold(v) in ("fy","fiscal year","annual") for _,v in parts)
  if len(kinds)>1 or len(qtokens)>1:
   issues.append({"column":col,"code":"CONFLICTING_FISCAL_PERIOD"});continue
  period=dict(candidates[-1][1])
  if len(kinds)==1:
   specified=next(p for _,p in reversed(candidates) if p["period_type"] in kinds)
   period=dict(specified)
  elif qtokens:
   period["period_type"]="Q";period["quarter"]=next(iter(qtokens))
  elif ytd:
   period["period_type"]="YTD"
  elif fy:
   period["period_type"]="FY"
  if fy and (qtokens or ytd):
   issues.append({"column":col,"code":"FY_VS_INTERIM_HEADER"});continue
  if ytd and period["period_type"] not in ("YTD",):
   issues.append({"column":col,"code":"QUARTER_VS_CUMULATIVE_HEADER"});continue
  if qtokens and period.get("quarter") not in (None,next(iter(qtokens))):
   issues.append({"column":col,"code":"QUARTER_CONFLICT"});continue
  if qtokens and period["period_type"]=="YTD":period["quarter"]=next(iter(qtokens))
  period["year"]=year
  period["source_header"]=" / ".join(v for _,v in parts if v)[:160]
  period["status"]="PERIOD_CANDIDATE_REQUIRES_FISCAL_CALENDAR"
  columns[col]=period
  last=max(last,max(idx for idx,_ in candidates))
  if (qtokens or ytd or fy) and parts:
   last=max(last,max(idx for idx,v in parts if _quarter(v) or _ytd(v) or context.fold(v) in ("fy","fiscal year","annual")))
 if not columns:return {},None,issues or ["NO_EXPLICIT_YEAR_COLUMN"]
 # Do not interpret a preceding row of labels as financial numeric data.
 return columns,last,issues
