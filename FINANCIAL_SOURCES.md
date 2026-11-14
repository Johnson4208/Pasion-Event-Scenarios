# Automatic financial data in Investment Research

Selecting a company downloads its available financial data and fills the existing indicator table. The original valuation-first layout is restored: summary/chart, five model cards, then indicators, health and summary. There is no source picker to complete first.

## Use

1. Pull `master` in GitHub Desktop and restart `RUN-PASION.cmd`.
2. Open Investment Research. Search a ticker or select a company suggestion. The global search also accepts Enter.
3. For a ticker outside the suggestions, select its market (Vietnam or United States), then **View financials**.
4. The backend downloads and caches source data. Each populated row shows its own period and source. The **Data details & connection settings** section is collapsed by default.

Vietnam works without a provider key. US SEC access requires an administrator to save a contact email once in the details section, or set `PASION_SEC_USER_AGENT`. Saving the email automatically retries the current company. The automatic endpoint never substitutes the bundled historical Apple example when SEC is unconfigured.

## Sources and coverage

- Vietnam: the public JSON feeds used on CafeF financial statement pages. Four fiscal years are requested; the newest matching annual income statement and balance sheet are selected. The source year is kept as `FY YYYY`; an exact fiscal year-end date is not invented. Latest completed annual figures are not called TTM.
- US: the existing SEC companyfacts adapter, supporting eligible issuer-wide US-GAAP annual 10-K filings. SEC coverage is not universal.
- Existing accepted PASION facts override the corresponding metric only. Missing accepted metrics may display public-source data with their own period label. Inputs from these two paths are never mixed to calculate a ratio.

Available Vietnam fields include revenue, net income, annual EPS, assets, equity, operating cash flow, net margin, ROE, ROA, current ratio, borrowings/equity and FCF when its inputs reconcile. CafeF's market snapshot supplies P/E, P/B, market cap and a timestamped price separately from annual statements. Market cap is converted from billions of VND; price is converted from thousands of VND. These snapshots are not verified valuation quotes.

**Financials → All indicators & statements** opens the complete source tables without expanding the main dashboard. It includes balance sheets, income statements and cash-flow statements for four fiscal years, searchable rows, original/million/billion units, and CSV/JSON exports. The FPT regression case contains 195 rows across six tables and 65 financial metrics, including unsupported metrics with explicit reasons. Metrics include gross/operating/pretax margins, liquidity, working capital, leverage, coverage, cash-flow ratios and growth. The detailed income adapter translates the provider's 2026 template migration back to the original historical codes; it never assigns a new property-disposal line to old financial income.

SEC's **XBRL facts** tab retains eligible numeric issuer facts beyond the summarized metric mapping, with separate units and explicit conflicts. It is not a transcription of every note in a filing. Full notes remain in the original reports.

## Original reports and financial tools

Selecting a company also requests `/api/research/reports/{ticker}?market=VN|US`. For Vietnamese issuers it discovers current-year and matching annual filings, then downloads the newest consolidated PDF and matching audited annual PDF into the private local archive. The Reports tab lists sources and provides downloads. FY2025 and Q3 2026 reports for FPT, HPG and VCB were retrieved on 2026-11-14; FPT's broken annual attachment has an issuer-published annual-report fallback containing the audited statements and notes. US reports currently link to original SEC filings (HTML); they are not downloaded as PDF.

Each of the five model cards now has an editable calculator: five-year FCFF DCF, P/E, five-year DDM, Gordon growth and adjusted net assets. Compatible reported EPS, cash, borrowings and owners' equity prefill their fields. Forecast growth, discount rates, current shares and other assumptions require explicit input. Results update the card/chart as **Your scenario**, remain separate from approved valuations and clear when the company changes. DCF requires FCFF; it does not substitute CFO minus capex.

Banks use their own asset/equity labels. Industrial revenue, current ratio, borrowing leverage, EBITDA and FCF formulas are not applied to bank templates. Unsupported sectors or changed source schemas return explicit missing-data reasons.

## Calculation safeguards

- Ratios require matching symbol, fiscal year and provider report-type code. ROA uses average assets; ROE matches profit attributable to owners with average equity attributable to owners.
- Debt/equity uses actual borrowings and finance leases, not total liabilities.
- Missing values do not become zero. Zero capex is accepted only when the investing cash-flow components reconcile. The observed FPT 2025 feed fails that check, so its FCF stays unavailable. HPG 2025 FCF does reconcile.
- Cash-flow depreciation is not automatically treated as eligible EBITDA expense. EBITDA remains unavailable without that reconciliation.
- Source records are unreviewed in PASION. No accepted financial database, valuation assumptions, or buy/sell recommendations are created by fetching them.
- DCF, DDM, Gordon and other valuation estimates still require their model inputs. A financial statement alone does not supply a discount rate, growth scenario or fair value.

## Operations

`GET /api/research/financials/{ticker}?market=VN|US` requires a signed-in session. `&refresh=1` requests an update; repeated requests are throttled. Financial data is cached for six hours in ignored `backend/private-financial-sources/` files. An expired cache during an outage is labeled stale and excluded from displayed indicators. Supplemental source failures preserve available metrics.

The provider endpoints are public website feeds, not a contracted data service. They can change, limit access or contain omissions; the adapter validates schemas and preserves links for checking against original filings.

## Verification

- Live financial retrieval checked for FPT, HPG and VCB on 2026-11-13, and original filings and expanded FPT statements on 2026-11-14; these are runtime downloads, not bundled production data.
- Regression fixtures under `backend/fixtures/public_financials/` are used only by tests.
- Backend tests cover values/units, partial inputs, zero handling, bank templates, cross-issuer/period rejection, cache persistence and outages, authentication and SEC configuration.
- UI tests cover company selection, global search, per-metric reviewed priority, stale/error states, late responses, admin setup and a Vietnamese phone layout.
