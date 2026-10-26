# SEC financials in the existing Investment Research UI

## What changed

The Investment Research page automatically requests `GET /api/research/sec/{TICKER}` for the selected US-listed issuer. On an issuer without accepted financial observations, its existing **Key Financial Indicators**, Summary and provenance panel can display a machine-read FY SEC companyfacts result. This does not create a separate calculations page and never writes to the application's accepted `finance.sqlite3`.

The server uses SEC `company_tickers.json` and `api/xbrl/companyfacts/CIK....json`; values are mapped only when there is an explicit 10-K accession, fiscal year end/start, FY and US-GAAP tag. Quarterly 10-Q boundaries are checked, and no value is inferred from an absent or conflicting tag. Results are cached for six hours **in memory** and discarded when the Python server restarts. The initial Apple fixture is available when no SEC User-Agent has been set, clearly labeled as manually transcribed and *not* a live scan.

The original uploaded-PDF workflow remains: admin upload -> background PDF/DOCX extraction -> stage observations with page/table/period/ownership -> human approval -> accepted facts -> public research cards. The existing system does **not** yet autonomously turn arbitrary, multilingual uploaded PDF filings into accepted accounting facts. For non-SEC issuers (including Vietnamese tickers), source adapters and reviewer mappings are still required.

## Configure SEC access locally

Before starting the backend, set an informative User-Agent identifying your application and contact. Use your **own** contact email. Windows PowerShell:

```powershell
$env:PASION_SEC_USER_AGENT="Pasion Research contact-your-email@example.com"
npm.cmd run dev:full
```

Windows Command Prompt:

```cmd
set "PASION_SEC_USER_AGENT=Pasion Research contact-your-email@example.com"
npm.cmd run dev:full
```

SEC requests require outbound HTTPS and are subject to SEC rate limits and access rules. If the SEC is blocked or unreachable, the page shows an unavailable status; do not silently substitute made-up data. API success is not a guarantee that every financial metric is comparable or that a valuation is eligible.

## Existing valuation cards

The existing DCF/FCFF, P/E, DDM, Gordon and asset-based cards remain **WITHHELD** without sufficient reviewer-accepted company facts, approved forecasting assumptions, sector policy, relevant quote and unit context. Raw SEC XBRL is a lower-trust preview only and **must never become an approved BUY or fair-value calculation automatically**.

## Reproducible tests

```powershell
python -m unittest discover -s backend -p test_sec_filings.py -v
python backend/examples/apple_sec_2025_case.py
```

No real account credentials, API tokens, or portfolio state are sent to SEC. Public SEC data is not a broker-confirmed price source.

## Next integration work

- Complete a full SEC filing acceptance review workflow, including restatements, tags with dimensions, taxonomy drift and fiscal calendars.
- Validate primary source facts against the filed 10-K, especially filing accessions, shared scales, diluted/common equity concepts and period end dates.
- Build region-specific adapters for non-US XBRL/iXBRL and PDF reports.
- Register eligible capital-market assumptions and sector-specific valuation policy before enabling any model's estimate.
- Add a side-by-side provenance drawer that identifies each individual input and its status.
