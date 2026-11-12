# Financial data sources in Investment Research

Open Investment Research and use **Financial data sources** beneath the company snapshot.

## US SEC

An administrator can expand **Configure SEC contact**, enter their application contact email and save. The server sends this email to SEC in its User-Agent header. It is stored locally in `backend/private-financial-sources/config.json`, excluded from Git, and never returned by the source catalog endpoint. Existing `PASION_SEC_USER_AGENT` configuration takes priority and is edited on the server instead.

Select **SEC · US filings** and use **Refresh SEC data**. Existing companyfacts normalization supplies annual US-GAAP 10-K data for supported issuers. The adapter requires compatible issuer, accession, currency and fiscal calendar; it does not cover every SEC filing, custom tag, foreign issuer or quarterly statement. Missing facts stay unavailable. Accepted company data takes priority over machine-read data.

The page now labels annual SEC financial indicators **FY**, rather than TTM. The original filing link and retrieval time are visible. The manually transcribed Apple 2025 reference remains clearly labeled when SEC is not configured; it is not a current download.

Successful normalized responses persist locally for six hours across server restarts. Refresh attempts are limited to once per ticker per minute and outgoing SEC requests are spaced at least 250 ms apart. A stale cached copy can be displayed with a failure reason during an outage but is excluded from indicator calculations. A successful refresh replaces the cache. No reviewed financial database, valuation assumptions or account settings are changed.

## Vietnam

Select **Vietnam · reviewed reports** to open official disclosure sources (SSC and HNX). Download the issuer's original financial statements, then use **Administration → Documents** and the existing financial observation review/approval workflow. These links are discovery aids, not automatic API connectors. Consolidated versus separate statements, currencies/scales, annual versus quarter/YTD periods and revisions must be reviewed before approval. Existing extraction limitations still apply.

FiinGroup is linked as an external service **not connected**; purchasing or configuring a data license is not included. No subscription is created. There is no automatic ingestion of arbitrary disclosure PDFs in this update.

## Verification

`python -m unittest discover -s backend -p 'test_financial_sources*.py' -v`

`python -m unittest discover -s backend -p 'test_sec_filings.py' -v`

`npm run test:ui -- tests/financial-sources.spec.js`

`npm run build`

Tests use synthetic network responses and temporary databases. They verify source permissions, contact privacy, persistent caching, stale exclusion, FY labels and VN/EN controls; they do not certify live SEC access from the deployment. Configure a real contact and verify an actual issuer from the machine hosting Pasion.
