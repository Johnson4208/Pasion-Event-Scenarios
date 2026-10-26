# PASION — Economic integration and public filing test

Implemented on top of PASION's existing financial engines: selected ticker is propagated to Investment Research, official HTTPS citation URLs are retained and shown in the evidence drawer, quality calculations reject missing ownership context, and negative D&A cannot be treated as a positive EBITDA add-back.

## Reproduce with an actual public filing

Run from `pasion-workspace`:

```powershell
python backend/examples/apple_sec_2025_case.py
```

The fixture manually transcribes selected **Apple 2025 Form 10-K** financial statement values and FY2024 comparative values and calls Pasion's real `finance_core.ingest()` and `finance_core.company()` calculation paths using an isolated temporary database. The published primary source is [SEC filing 0000320193-25-000079](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm). Figures are USD millions before scaling; basic shares in thousands. Reported FY2025 ending date: September 27, 2025. Disclosure/publication evidence is not treated as available on balance sheet date; use only data known by evaluation time.

**Important:** This is a manual, selected-cell public filing transcription, **not automatic PDF/OCR parsing, not an authorized admin acceptance, not a current market quote, and not a production-ready recommendation**. The fixture never modifies your Pasion database or user accounts. Import real data to the application through its existing administrator document staging/review process after verifying page/table/tag references.

Example expected FY2025 outputs:
- Revenue USD 416.161 billion, net income USD 112.010 billion, CFO USD 111.482 billion.
- Net margin ~26.92%, CFO margin ~26.79%, ROA ~30.93%, current ratio ~0.893 and basic EPS ~USD 7.49.
- Standard EBITDA stays unavailable (cash-flow D&A is not automatically an eligible EBIT add-back). ROE remains unavailable absent a matching common equity bridge; valuation assumptions and verified fresh quote remain unavailable.

## Remaining work

The previous full remediation backlog is *not* complete. Distribution remains shadow-only and fail-closed; broker-confirmed data, actual portfolio performance, sector-specific forecast/model policies, and fully reviewed financial filing extraction still need additional implementation and tests.

Test command:

```powershell
python -m unittest discover -s backend -p "test_*.py"
```

The targeted suite was tested locally, but do not interpret that as a full deployment certification.
