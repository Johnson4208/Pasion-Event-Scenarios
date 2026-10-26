F03 reviewed company economics
==============================

Existing overview cards, full-screen research frame, company search/watchlists and
Compare Companies navigation are preserved. Reviewed filings are the default.
Sample research is available through an explicit Financial data mode selector.
Unsupported supplied VND snapshot labels have been changed from Verified report
to Unreviewed sample; they are not promoted to accepted facts or applied as actual
company accounts. Sample market price history remains labeled separately.

API and persistence
-------------------
GET /api/research/company/:ticker?period=Q|YTD|FY|TTM&end=YYYY-MM-DD&origin=offset-clock
GET /api/research/compare?tickers=AAPL,MSFT&period=FY&end=YYYY-MM-DD
GET /api/research/facts/:id/evidence
POST /api/admin/finance/facts

All reads require a current session. Ingestion requires a current admin role and
ready documents from the existing admin document service.
Ingestion also requires a saved original and records its server-computed SHA-256
and document-service version. Legacy documents without originals must be reuploaded.
Research readers receive accepted financial facts and citation page/table/tag, never original documents,
download paths, reviewer accounts or unreviewed extraction content. Accepted
financial facts are shared issuer research, not personal portfolio data.

finance.sqlite3 contains issuer, immutable issuer-year fiscal calendar, report,
metric-definition and immutable fact registries. Stored raw values and scales are
preserved; canonical values use Python Decimal and serialize as decimal strings.
Definitions distinguish additive flows, instant balances and nonadditive weighted
shares. Facts retain accounting standard, consolidation scope, restatement basis,
revision and publication/indexing/acceptance clocks. Known-at is their maximum.
New revision IDs append history; replay selects only revisions known by its origin.
Competing revisions accepted at the same instant are withheld as ambiguous.

Calculation gates
-----------------
Quarter/YTD/FY intervals must match explicitly registered issuer fiscal boundaries,
including non-calendar years. Standalone quarters are never subtracted twice.
Additive Q2 may be H1 minus Q1; TTM may use four contiguous standalone quarters or
prior FY plus current YTD minus prior comparable YTD. Missing bridge stays unavailable.
Nonadditive shares/EPS are never differenced or annualized from a short period.

Standard EBITDA requires reviewed EBIT and D&A explicitly confirmed to have reduced
EBIT in that interval. Margins and CFO relationships require identical flow dates.
ROA uses income and average opening/closing assets; ROE uses common income and
average common equity. Missing opening balances withhold results. Debt/EBITDA
requires FY/TTM and a positive denominator. EPS requires same-period common profit
and weighted-average shares. Unit, currency, accounting basis, scope and restatement
basis gates apply to every derived result and every comparison row. Zero is preserved;
missing facts, incompatible contexts and invalid denominators have explicit reasons.

Metric drawers expose source report, page/table/tag, unit/currency, exact dates,
revision and clocks. The Summary reports revenue/income, earnings/cash, debt/annual
EBITDA and working-capital/sales relationships. Historical revenue, income, EBITDA
and CFO series use the same period engine. No financial-health probability is added.

Loading reviewed financial data
------------------------------
Upload the original filing through the existing admin Document workspace. After
extraction is ready, an administrator maps and verifies its accounting fields and
posts a reviewed JSON batch to /api/admin/finance/facts with their session cookie.
This is a manual review boundary, not automated financial report extraction.
F12 remains responsible for the future observation/review UI and parser adapters.

Batch shape (example contract only; not real financial data):
{
  "issuer": {"ticker":"EXAMPLE","name":"Example issuer"},
  "calendar": {"year":"2024","start":"2024-01-01","end":"2024-12-31",
    "quarter_ends":["2024-03-31","2024-06-30","2024-09-30","2024-12-31"]},
  "reports": [{"id":"filing-v1","document_id":"existing-admin-document-id",
    "published_at":"2024-04-01T00:00:00Z","indexed_at":"2024-04-02T00:00:00Z"}],
  "facts": [{"id":"revenue-q1-v1","report_id":"filing-v1","definition_id":"revenue",
    "value":"100","scale":"1000000","currency":"USD","unit":"currency",
    "scope":"consolidated","accounting_basis":"US_GAAP","restatement_basis":"original",
    "revision":"1","period_type":"Q","period_start":"2024-01-01",
    "period_end":"2024-03-31","reviewed":true,
    "evidence":{"page":7,"table":"Income statement","tag":"Revenue"}}]
}

For D&A only, add da_eligible:true after reviewing the expense/EBIT bridge.
Balances use period_type INSTANT with equal start/end dates. Opening balances
may be the day before the fiscal year starts. Weighted-average shares use shares
as their unit; other accounting amounts use currency. Submit new report/fact IDs
for each amendment. Existing identities and fiscal calendars are not overwritten.

Release boundary
----------------
No real filings were supplied or accepted during implementation. Reviewed screens
therefore show UNAVAILABLE until authorized review data is loaded. There is no live
financial provider or automatically certified source accuracy. Production identity/
storage review from F01 still applies. Automated extraction, observation review,
financial quality diagnostics and valuation remain F12/F04 work.

Checks: Python financial core/API tests; browser zero/period/evidence/comparison
tests; F01/F02 security regression tests and frontend build. Synthetic fixtures are
used only in tests and do not become production research.

Validation evidence: full Python discovery passed all 106 tests; the focused
financial core/API suite passed 12 tests after the final source-hash check.
All five focused F01–F03 browser tests pass and the production build passes with
the existing bundle-size warning. Broader historical UI regression gaps recorded
in F01 remain; older tests expecting the sample research view by default also need
to distinguish the new reviewed default from explicitly selected sample mode.
