# PASION US & Vietnam report-recognition upgrade

Scope: privately uploaded PDF/DOCX/PNG/JPEG/WebP financial statements; **SEC connectivity is not required**. This is a conservative classification pipeline, **not a guarantee that arbitrary issuer reports are fully understood**.

## Processing contract
1. Existing bounded upload worker saves original file, runs native PDF text/table extraction, optional OCR, and preserves page/section/table/cell coordinates.
2. `financial_report_context.detect_profile()` looks for **explicit** US GAAP / Vietnamese Accounting Standards declarations, consolidated vs separate (company parent) statements, named statement types, and exchange-prefixed tickers (NASDAQ/NYSE/HOSE/HNX/UPCOM). Conflicts are not silently resolved. A currency never determines the accounting standard.
3. `financial_locale.identify()` recognizes explicit USD/VND monetary units, scale (ones, thousands, millions, billions), and US/VN numeric separators. Source evidence and normalized amounts remain attached; no FX conversion. Inconsistent or absent declarations block conversion.
4. `financial_auto_index.scan()` maps exact supported English/Vietnamese labels in PDF tables to tentative economic metrics, reads explicit annual/quarter/YTD headers, and retains the **source cell, year, period candidate, statement type, accounting profile and uncertainty**. A four-digit year *alone* cannot establish a fiscal period; `FY2025` or `Q2 2025` is still only a candidate needing a fiscal calendar.
5. Admin > Documents > Financial observation review shows candidate cells, source position, currencies/scales and report profile. Human review of issuer identity, fiscal quarter boundaries, period, unit, scale, ownership, accounting basis, source coordinates and publication time is required before staging.
6. Existing staging/approval flow checks economic facts. On acceptance, the existing `finance_core.company` calculates supported metrics and the pre-existing Investment Research / Financial Indicators components display eligible accepted results. Forecast and valuation methods require their own reviewed inputs and assumption policies.

## Limitations and safety
- Automatic *classification* is implemented, not automatic *approval*. Free-text OCR with lost table structure and scanned source documents without reliable table extraction can remain unclassified.
- Comparatives, segment facts, bank/insurance statements, separate vs consolidated mixtures, fiscal calendar mappings and restatements require review. This release does not infer quarter-end dates from labels.
- Tables with date labels not explicitly supported or units ambiguous are withheld. Number formatting can differ inside a single report; never override the source by currency assumptions.
- Default upload limits remain 10 MB, PDF 50 pages, OCR up to 20 pages, 100 documents. Reports outside these limits are not successfully indexed.
- Documents uploaded **before** this change must be uploaded again for the report-profile index.
- Neither a local document nor a candidate row is silently committed to the reviewed financial database; nothing automatically authorizes a BUY or investment valuation.

## Focused regression suites
Run from the project root:

```powershell
python -m unittest discover -s backend -p test_financial_auto_index.py -v
python -m unittest discover -s backend -p test_financial_locale.py -v
python -m unittest discover -s backend -p test_financial_report_context.py -v
python -m unittest discover -s backend -p test_finance_ingestion.py -v
```

These cover US/VN currency multipliers, locale separators, US GAAP/VAS and scope declarations, ambiguity, report tables, FY/Q/YTD classification and immutable reviewed staging. Full integration testing against real annual and interim filings from both countries, OCR table fidelity and browser end-to-end processing is still required. Do not claim accuracy until these production-representative acceptance suites pass.

## Required before a production-grade two-country release
- Representative US/VN fixture corpus (at least a few reports for consolidated/parent annual/quarter/YTD, scanned/image-based and restated), line-level expected outputs, error rates and negative tests.
- Better multi-column/merged-cell extraction and OCR confidence propagation to financial candidates.
- Vietnamese alternative label dictionaries and tabular regional format detection with conflict handling.
- Full fiscal calendar extraction and matching previous quarters, including 52/53-week US annual reporting.
- Evidence-preserving batch reviewer, idempotent revision handling, restatement policy and peer-eligible comparability.
- Versioned acceptance replay tests and user-facing status/provenance consistency.
