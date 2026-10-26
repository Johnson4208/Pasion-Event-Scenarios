"""Public Apple FY2025 10-K financial sample. Curated transcription, not automatic OCR or reviewed investment advice."""
import sys,json,tempfile
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import finance_core as f
URL="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
years={
"2024":("2023-10-01","2024-09-28",["2023-12-30","2024-03-30","2024-06-29","2024-09-28"],{"revenue":"391035","net_income":"93736","net_income_common":"93736","cfo":"118254","operating_profit":"123216","weighted_average_shares":"15343783"},{"assets":"364980","current_assets":"152987","current_liabilities":"176392","liabilities":"308030","equity":"56950"}),
"2025":("2024-09-29","2025-09-27",["2024-12-28","2025-03-29","2025-06-28","2025-09-27"],{"revenue":"416161","net_income":"112010","net_income_common":"112010","cfo":"111482","operating_profit":"133050","weighted_average_shares":"14948500"},{"assets":"359241","current_assets":"147957","current_liabilities":"165631","liabilities":"285508","equity":"73733"})
}
def make(year):
 start,end,quarters,flows,balances=years[year]; rid="SEC-AAPL-2025-10K-"+year; facts=[]
 for kind,items in (("FY",flows),("INSTANT",balances)):
  for metric,value in items.items():
   facts.append({"id":rid+"-"+metric,"definition_id":metric,"value":value,"scale":"1000" if metric=="weighted_average_shares" else "1000000","period_start":end if kind=="INSTANT" else start,"period_end":end,"period_type":kind,"currency":"USD","unit":"shares" if metric=="weighted_average_shares" else "currency","scope":"consolidated","accounting_basis":"US_GAAP","restatement_basis":"2025_10K_COMPARATIVE","ownership":"consolidated_apple_group","revision":"2025-10K","report_id":rid,"reviewed":True,"source_line_label":metric,"evidence":{"page":36 if metric in ("net_income_common","weighted_average_shares") else 33 if metric=="cfo" else 31 if kind=="INSTANT" else 29,"table":"SEC published consolidated statements or EPS note","tag":metric}})
 return {"issuer":{"ticker":"AAPL","name":"Apple Inc."},"calendar":{"year":year,"start":start,"end":end,"quarter_ends":quarters},"reports":[{"id":rid,"document_id":"SEC-0000320193-25-000079","published_at":"2025-10-31T12:00:00Z","indexed_at":"2025-11-01T00:00:00Z","source_url":URL,"source_kind":"MANUAL_TRANSCRIPTION_SEC_10K"}],"facts":facts}
def run(root):
 for year in ("2024","2025"):f.ingest(root,make(year),"PUBLIC_CASE_NOT_ADMIN_APPROVED")
 r=f.company(root,"AAPL","FY","2025-09-27"); m=r["metrics"]
 assert m["revenue"]["value"]=="416161000000"
 assert m["net_income"]["value"]=="112010000000"
 assert m["ebitda"]["status"]=="UNAVAILABLE"
 assert m["eps"]["status"]=="READY"
 assert f.evidence(root,m["revenue"]["source_ids"][0])["source_url"]==URL
 print(json.dumps({"source":URL,"period":"FY2025","status":"CURATED_PUBLIC_FILING_CASE","metrics":{k:{"value":m[k]["value"],"status":m[k]["status"],"unit":m[k]["unit"]} for k in ("revenue","net_income","cfo","net_margin","cfo_margin","roa","current_ratio","eps","ebitda","roe")}},indent=2))
if __name__=="__main__":
 with tempfile.TemporaryDirectory(prefix="pasion-sec-") as d:run(Path(d))
