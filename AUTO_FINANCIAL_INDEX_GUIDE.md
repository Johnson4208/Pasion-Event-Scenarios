# PASION automatic document financial index (offline / no SEC required)

This change **does not connect to SEC**. Uploaded PDF/DOCX/PNG/JPEG/WebP files are processed by the existing bounded extraction worker, and the extracted tables are subsequently classified into financial *candidate cells*. Source references retain table/row/column, fiscal year header and source label. Candidates are stored with the extracted document and displayed inside **Admin → Documents → Financial observation review**. The existing data review form can preload a selected candidate's metric, table coordinates and value. The administrator must still specify and verify issuer, fiscal year/calendar boundaries, reporting period start/end, scale (ones/thousands/millions), currency, reporting perimeter, accounting basis, revision, publication timestamp and ownership.

**Important:** Candidate status is `CANDIDATE_REQUIRES_CONTEXT_AND_HUMAN_REVIEW`. OCR text, ambiguous duplicates, unverified fiscal calendars and units never become accepted financial facts automatically. To populate existing Investment Research key indicators, click **Stage mapped observation**, review the source cell, then **Accept reviewed context** in the immutable staging queue. The normal `finance_core.company` research API will derive eligible ratios from accepted evidence. The frontend remains unchanged apart from an admin source-candidate review list; there is no new user calculation page.

The classifier currently handles only selected English/Vietnamese exact financial labels and table headers with explicit four-digit annual years; it intentionally ignores free-text and non-explicit year/period tables. It is not a full international, multilingual financial statement parser, and cannot auto-approve forecast or valuation assumptions. Scan limits remain 10 MB per file, 50 PDF pages, 20 OCR pages, and 100 stored documents.

Existing files already uploaded **before this change** do not automatically get the new candidate index. Upload them again to run indexing or build a separate backfill/reindex job. Scanner failures preserve the original file for retry.

## Smoke test

1. Update your local checkout with `git pull origin main` (use your working VPN proxy when required).
2. `python -m unittest discover -s backend -p test_financial_auto_index.py -v`
3. `npm.cmd run dev:full`
4. Open Admin → Documents and upload a financial statement with a readable table headed `2025`, `2024` and rows `Revenue`, `Net income` etc.
5. Wait for `ready` and expand Financial observation review. Check candidate source/number and choose **Inspect source cell**. Do not approve figures until confirmed against the original.
6. After staged facts are accepted, select that company's ticker in Investment Research and reload. Only mathematically eligible figures appear.

## Next steps

- Configurable multilingual label dictionaries and robust layout/period/scale recognition.
- Candidate batch-review screen with reviewer-edited values and evidence coordinates.
- PDF document semantic classification with issuer mapping and restatement handling.
- Reviewer-approved financial snapshots and versioned valuation policy.
- Full integration, security, OCR, user acceptance and performance tests.

No main-database mutation is performed by `financial_auto_index.scan`; only existing financial approval workflow writes accepted facts.


## United States and Vietnam monetary-unit support (v1)

The auto-index now recognizes **explicit monetary unit declarations** in extracted report text, titles and table headers and suggests **USD/VND** plus factors 1, 1,000, 1,000,000 and 1,000,000,000. Examples:

| Report annotation | Printed source cell | Parsed value | Scale | Canonical value |
| --- | ---: | ---: | ---: | ---: |
| Đơn vị tính: triệu đồng | 1.234,5 | 1234.5 | 1,000,000 | 1,234,500,000 VND |
| (In millions of US dollars) | 1,234.50 | 1234.50 | 1,000,000 | 1,234,500,000 USD |

The Vietnamese parser uses dot grouping and comma decimals, while the US parser uses comma grouping and dot decimals. No market is inferred from the symbol alone. Source evidence, unit status and canonical numeric value are retained per candidate, and the reviewer form pre-fills recognized currency and scale.

**Fail closed:** conflicting or missing unit declarations leave currency/scale empty; financial candidates do not become accepted facts. The human reviewer must verify original context, period and scale, not merely select the suggested number. In particular, US GAAP vs VAS accounting standards are not inferred from the denomination, and no FX conversion is performed.

Run the additional tests with:

```powershell
python -m unittest discover -s backend -p test_financial_locale.py -v
```

The current release focuses on the standard US/Vietnam number conventions. Mixed formats, translations beyond its initial label catalog, quarterly/year-to-date columns, section-specific units, and annual fiscal calendars still need dedicated adapters and tests. These limits do not change the existing human approval requirement.
