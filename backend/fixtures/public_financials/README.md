Public CafeF JSON snapshots retrieved 2026-11-13 for regression tests only.
These files are never loaded by the application. Values are in VND; periods and original report type codes are retained.

Endpoints: GetReportSummary (v1), GetReportCDKT (v2), GetReportLCTT (v1) under https://apiweb.cafef.vn/api/ with symbol, pageIndex=1, pageSize=4, reportType=ALL, TypeTime=NAM.

The FPT cash-flow feed has a zero capex line that does not reconcile to investing cash flow. The regression test requires FCF to stay unavailable rather than accepting this zero.

`fpt-income.json` was retrieved on 2026-11-14 from v1/BCTC/GetReportDetail with reportType=KQKD and TypeTime=NAM. It records the provider's new 2026 template with historical values using old codes. Tests verify the explicit historical mapping, all 195 statement rows and EPS without currency scaling.
