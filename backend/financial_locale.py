"""US/VN monetary unit detection and locale-aware number parsing.

All outputs are review suggestions grounded in explicit source text, never approved facts.
"""
import re
import unicodedata
from decimal import Decimal,InvalidOperation

UNIT_VERSION="us-vn-units-v1"
SCALE={"ones":"1","thousands":"1000","millions":"1000000","billions":"1000000000"}

def folded(value):
    value=unicodedata.normalize("NFKD",str(value or "").lower()).replace("đ","d")
    return "".join(c for c in value if not unicodedata.combining(c))

def _is_declaration(value):
    s=folded(value).strip()
    return bool(re.search(
        r"(?:^|[\s(])(?:don vi(?: tinh)?|dvt|units?(?: of measure)?|in (?:thousands|millions|billions)|"
        r"amounts? (?:in|are stated in)|expressed in|all amounts? (?:are |in )?)\b",s))

def declaration(value):
    """Require a monetary-unit statement; country or language alone is insufficient."""
    if not _is_declaration(value):return None
    s=folded(value)
    has_vnd=bool(re.search(r"\b(?:vnd|vietnamese dong|vn dong|dong)\b",s))
    has_usd=bool(re.search(r"\b(?:usd|us dollars?|u\.?s\.? dollars?|dollars?)\b",s)) or 'us$' in s
    if has_vnd==has_usd:return None
    currency="VND" if has_vnd else "USD"
    scales=[]
    for k,pattern in (("thousands",r"\b(?:thousand|thousands|nghin|ngan)\b"),
                      ("millions",r"\b(?:million|millions|trieu)\b"),
                      ("billions",r"\b(?:billion|billions|ty)\b")):
        if re.search(pattern,s):scales.append(k)
    if len(scales)>1:
        return {"currency":None,"scale":None,"basis":str(value).strip()[:160],"issue":"CONFLICTING_SCALE_WORDS"}
    return {"currency":currency,"scale":SCALE[scales[0] if scales else "ones"],
            "basis":str(value).strip()[:160],"issue":None}

def parse_number(value,locale):
    raw=str(value or "").strip().replace("\u00a0","")
    if not raw or raw in ("—","-","*","N/A","n/a"):return None
    negative=raw.startswith("(") and raw.endswith(")")
    if negative:raw=raw[1:-1].strip()
    if locale=="US":
        valid=r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
        sanitized=raw.replace(",","")
    elif locale=="VN":
        valid=r"[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?"
        sanitized=raw.replace(".","").replace(",",".")
    else:return None
    if not re.fullmatch(valid,raw):return None
    try:
        amount=Decimal(sanitized)
        if negative:amount=-amount
        return str(amount) if amount.is_finite() and abs(amount)<Decimal("1e25") else None
    except InvalidOperation:return None

def source_catalog(document):
    by_page={};all_sources=[]
    for entry in document.get("sections") or []:
        if entry.get("kind")=="table":continue
        for line in str(entry.get("text") or "").splitlines()[:30]:
            if len(line)<180 and _is_declaration(line):
                by_page.setdefault(entry.get("page"),[]).append((line,"same page"))
                all_sources.append((line,"document"))
    return {"by_page":by_page,"document_wide":all_sources}

def identify(document,section,catalog=None):
    """Prefer same-page/table declarations; document-wide only when no local clue."""
    catalog=catalog or source_catalog(document)
    sources=[]
    for row in (section.get("table") or [])[:3]:
        if isinstance(row,list):
            sources.extend((str(cell),"table header") for cell in row if cell and _is_declaration(str(cell)))
    title=section.get("title")
    if title and _is_declaration(title):sources.append((title,"table title"))
    sources += catalog["by_page"].get(section.get("page"),[])
    if not sources:sources=catalog["document_wide"]
    recognized=[]
    for phrase,location in sources:
        unit=declaration(phrase)
        if unit:recognized.append((unit,location))
    if not recognized:return {"currency":None,"scale":None,"locale":None,"evidence":[],"status":"UNIT_NOT_EXPLICIT"}
    unique={(u["currency"],u["scale"]) for u,_ in recognized}
    evidence=[{"text":u["basis"],"location":location} for u,location in recognized[:8]]
    if len(unique)!=1 or any(u["issue"] for u,_ in recognized):
        return {"currency":None,"scale":None,"locale":None,"evidence":evidence,"status":"CONFLICTING_UNIT_DECLARATIONS"}
    currency,scale=next(iter(unique))
    return {"currency":currency,"scale":scale,"locale":"VN" if currency=="VND" else "US",
            "evidence":evidence,"status":"EXPLICIT_UNIT_CANDIDATE_REVIEW_REQUIRED"}
