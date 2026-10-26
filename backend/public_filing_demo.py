"""On-demand, isolated public-filing calculation demonstration.

This is not the user's research database, an admin-accepted filing, or a
real-time valuation. Values are read from a manually transcribed SEC example
and processed through the existing finance_core engine on each request.
"""
import tempfile
from pathlib import Path

import finance_core
from examples.apple_sec_2025_case import URL, make

CASE = "apple-fy2025-form10k"
DISPLAY = [
    ("revenue", "Revenue", "Reported revenue", "USD"),
    ("net_income", "Net income", "Reported net income", "USD"),
    ("cfo", "Operating cash flow", "Reported net cash from operations", "USD"),
    ("net_margin", "Net profit margin", "Net income / revenue x 100", "%"),
    ("cfo_margin", "Operating cash flow margin", "Operating cash flow / revenue x 100", "%"),
    ("roa", "Return on assets", "Net income / average opening and closing assets x 100", "%"),
    ("current_ratio", "Current ratio", "Current assets / current liabilities", "x"),
    ("eps", "Basic EPS", "Net income attributable to common / weighted-average basic shares", "USD/share"),
    ("ebitda", "Standard EBITDA", "Eligible EBIT + verified period D&A add-back", "USD"),
    ("roe", "Return on common equity", "Common net income / average common equity x 100", "%"),
]

def calculate():
    with tempfile.TemporaryDirectory(prefix="pasion-public-filing-") as work:
        root = Path(work)
        for year in ("2024", "2025"):
            finance_core.ingest(root, make(year), "PUBLIC_EXAMPLE_ONLY_NOT_APPLICATION_REVIEW")
        result = finance_core.company(root, "AAPL", "FY", "2025-09-27")
        rows = []
        for metric, label, formula, unit in DISPLAY:
            item = result["metrics"][metric]
            sources = []
            for source_id in item.get("source_ids", []):
                source = finance_core.evidence(root, source_id)
                if source:
                    sources.append({"id": source["id"], "label": source.get("source_line_label") or source["definition_id"],
                                    "period_end": source["period_end"], "page": source["evidence"]["page"],
                                    "table": source["evidence"]["table"], "source_url": source.get("source_url")})
            rows.append({"id": metric, "label": label, "formula": formula, "value": item.get("value"),
                         "unit": item.get("unit") or unit, "status": item["status"],
                         "reason_codes": item.get("reason_codes", []), "inputs": sources})
        return {
            "version": 1, "case": CASE, "ticker": "AAPL", "issuer": "Apple Inc.",
            "period": "FY2025", "period_end": "2025-09-27", "source_url": URL,
            "source_title": "Apple FY2025 Form 10-K (SEC filing 0000320193-25-000079)",
            "source_basis": "MANUALLY_TRANSCRIBED_SELECTED_PUBLIC_FILING_CELLS",
            "execution_mode": "ISOLATED_TEMPORARY_DATABASE_RECOMPUTED_ON_REQUEST",
            "research_status": "EXAMPLE_ONLY_NOT_ADMIN_ACCEPTED",
            "engine": "finance_core.company",
            "currency": "USD", "metrics": rows,
            "disclosure": "Calculations use selected historic filing figures (not an automatic filing parser). "
                          "No broker quote, valuation, investment advice, or live account data are included. "
                          "Unavailable values remain unavailable."
        }
