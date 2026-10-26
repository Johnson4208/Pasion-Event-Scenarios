# Dependency-based implementation and release record

This record maps the user-supplied blueprint to this checkout. Implementation
does not certify a release gate. All P0–P3 packages remain GUARDED; P4+ is
DEFERRED. Current API release manifests remain REVIEW_ONLY. The full backend
run recorded under A17 timed out; browser acceptance is incomplete. Individual
passing suites must not be represented as complete Pasion acceptance.

`backend/release_packages.py` is the machine-readable package inventory, with
dependencies, executable suites and outstanding gates. It is included in the
admin health release manifest. Run a package independently with:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/validate_release.py --package P3.0
```

This runs only that package's backend suites, all frontend unit tests and build.
Dependencies are declared but their tests are not implicitly included. Add
`--browser` for the bounded browser suite. No flag approves promotion. Unique
local reports record source SHA-256, scope, mocks/local fixtures and NOT_RUN
browser status. Full acceptance uses the runner without a scope flag.

Current package validation: P3.0's three backend suites, all 11 frontend unit
tests and build passed in run `20261014T163722Z-68e83a006f86`, with unchanged
source fingerprint. Eight additional package-registry/governance/health tests
passed, including the admin-only health alias. Dependency suites and browser
checks were not included; this does not clear the broader release gates.

| Stage | Delivery | Outstanding exit evidence |
| --- | --- | --- |
| P0.0 | Existing auth/documents/security and sample separation | Complete browser regression, production identity/storage review |
| P0.1 | A01–A03 contracts, accepted facts, clocks and issuer periods | Governed real-source admission |
| P0.2 | A04–A05 metrics, quality diagnostics, comparisons | Reviewed peers and complete anomaly inputs |
| P0.3 | A10 shared lot/cash/fee/quote sizing and outcomes | Verified FX/corporate-action policy |
| P1.0 | F03/F04/F12 API-backed screens and exact evidence | Complete document-review/source drawer UI acceptance |
| P1.1 | A06–A07 driver forecasts, FCFF/FCFE and method eligibility | Verified issuer drivers and sector signoff |
| P1.2 | F08/A11 manual private state, risk and journal | Reconciled event/FX history and actual return acceptance |
| P2.0 | Optional market, macro, news, scenarios, watch and assistant services | Individual provider coverage, nested validation/future cohorts |
| P3.0 | A14–A15 admin gates and atomic shadow shares ledger | Exposure policy, same-window tape and reconciliation |
| P4+ | No live execution delivery | Separate legal/broker/account/risk release, multi-host coordinator |

## First twenty actions: current destinations

| # | Action | Existing destination / remaining limitation |
| --- | --- | --- |
| 1 | Freeze navigation, source/admin regression | Existing hash routes/tests; complete browser run still required |
| 2 | Status enums, decimals, envelope | `backend/finance/contracts.py`, `src/researchApi.js` |
| 3 | Registries | `finance_core.py`, `feasibility.py`, frozen model records; peer registry pending |
| 4 | Clocks/replay | `common/time.py`, `finance/periods.py`; point-in-time fixture tests |
| 5 | Reviewed extraction | `finance_ingestion.py`; accepted observations preserve raw source |
| 6 | Semantic/source gates | Finance context validation and metric evidence API |
| 7 | Q/YTD/FY/TTM | Issuer fiscal calendar and compatible bridges in finance core |
| 8 | EBIT/DA/EBITDA/ratios | `finance/metrics.py`; eligible DA only |
| 9 | Drawer and Summary | `FinancialFacts.jsx`, `ReviewedValuation.jsx` |
| 10 | Comparison API | `/api/research/compare`; incompatible cells marked not comparable |
| 11 | One feasibility adapter | `feasibility.for_owner`; cross-currency without verified FX withheld |
| 12 | Planner sizing/drafts | `useTradeFeasibility.js`; local drafts retained, no orders |
| 13 | Portfolio ledger/industry | `portfolio_ledger.py`, manual lots/cash; journal not reconciled replay |
| 14 | Driver registry/bridges | `valuation.py`, `finance/forecast.py`; aggregate driver baseline |
| 15 | Valuation methods | `finance/valuation.py`; explicit sector eligibility, no forced consensus |
| 16 | Health/release reasons | `operational_health.py`, `release_governance.py`; admin only |
| 17 | Causal RVOL/events | `market/technical.py`, `technical.py`; prior-only volume and completed bars |
| 18 | Validated probability | `stock_models.py`; frozen versions, abstention; nested tuning not certified |
| 19 | Admin Distribution | `distribution/engine.py`, `distribution/capacity.py`; candidates withheld |
| 20 | Replay/security/concurrency | Package suites and release archives; broader rollout remains gated |

## Legacy risk transfer register

R01–R23 are supplied legacy prevention requirements, not assertions of current
Pasion defects. Suite mappings indicate test ownership, not that the entire
requirement has passed. Review documented limitations before adopting old code.

| ID | Prevention gate | Test owner / remaining evidence |
| --- | --- | --- |
| R01 | Prior-only RVOL; retune VSA | `test_a08`; production threshold validation pending |
| R02 | Resolved/unresolved win denominators | `test_a10` |
| R03 | No VSA quantity without shared feasibility | `test_feasibility`, VSA has no executable quantity |
| R04 | Cash after costs/reserves | `test_feasibility` |
| R05 | SMA200 prerequisites | `test_technical` |
| R06 | Heuristic versus calibrated probability | `test_stock_models`, `test_a09` |
| R07 | Period selection context | `test_information_periods`, `test_finance_core`; UI regression pending |
| R08 | Publication/acceptance clocks | `test_contracts`, `test_report_review` |
| R09 | Page/table/tag lineage | `test_report_review`, `test_finance_api` |
| R10 | Issuer calendar, no day-count heuristic | `test_information_periods` |
| R11 | Zero/missing volume distinction | `test_a08` |
| R12 | Explicit timezone/session | `test_market_summary`, `test_a14`; provider certification pending |
| R13 | Method eligibility/source rates | `test_valuation`; issuer review required |
| R14 | FCFF/FCFE/DA bridge | `test_forecast`, `test_valuation` |
| R15 | Same-context anomaly comparison | `test_quality`; real peer reference registry pending |
| R16 | Real FX/portfolio P&L history | `test_a11`; reconciled history and actual performance pending |
| R17 | Macro vintage replay | `test_a12`, `test_macro_evidence` |
| R18 | Future cohort after frozen model | `test_a09`; nested tuning and real cohorts pending |
| R19 | Shared atomic capacity | `test_a15`; multi-host coordinator pending |
| R20 | Offset-aware known_at | `test_contracts`, `test_information_periods` |
| R21 | MFI no-flow policy | `test_technical`; no confidence claim |
| R22 | Preserve reported zero | `test_contracts`, `unit/researchApi.test.js` |
| R23 | Reject negative volume | `test_a08` |

## API, storage and status ownership

The proposed directory tree is a target, not a claim that every listed file
exists. Existing backend services stay in place; small finance/market/
distribution packages delegate without transplanting the SolvAI UI. Current
route ownership is documented in `backend/A16_RELEASE.md`. The proposed
`GET /api/admin/data-health` is an admin-only alias of `/api/admin/health`.
`GET /api/market/:ticker/indicators` already exists; no duplicate is introduced.

Document originals and downloads remain admin-only. Members get permitted
accepted fact excerpts, not original files. Observations are not accepted facts.
Facts preserve context/revision/known_at; assumptions are private and explicitly
assumptions; model artifacts freeze versions/snapshots; account/journal events
are owner-scoped; Distribution events are admin audit only. Schema remains
additive SQLite. Production migrations and a shared multi-host coordinator are
not certified by local tests.

Economic origin ACTUAL/DERIVED/PROXY/ASSUMPTION/FORECAST is separate from
availability READY/STALE/UNAVAILABLE/WITHHELD/ERROR. REVIEW_ONLY permits admin
inspection, not an allocation. Probability, heuristic score, scenario weight
and coverage are not interchangeable. known_at gates point-in-time use; as_of
describes the snapshot; accounting intervals use period_start/period_end.

Parallel work on document/news/macro adapters may proceed after contracts, but
model probability and Distribution cannot bypass clocks, source eligibility or
the declared foundational dependencies. No branch/PR evidence is fabricated:
this checkout has no available Git repository, so work remains local.

## Existing-screen calculation integration

The user requested the previous design and calculations inside existing UI,
with no new screens, cards or input controls. The experimental redesign import
has been removed. Original company research, investment research, comparison,
stock metrics, VSA, macro, newsroom and portfolio layouts are active. Separate
reviewed-page branches, the extra watch-log panel and the separate feasibility
card are no longer rendered in those flows. Existing table cells, charts,
source-details panel, model details and portfolio/assistant controls receive
compatible service results. Reported zero remains zero; missing/ineligible
results have no sample-number fallback.

| Original destination | Applied calculation/data |
| --- | --- |
| Company indicator grids and original research tabs | Canonical TTM facts, profitability, leverage, liquidity and supported quality diagnostics |
| Existing source-details panel | Accepted fact IDs, page/table/tag, revision, known_at and available excerpt |
| Original comparison table, relative bars and export | Canonical results; incompatible cells marked, relative bars suppressed |
| Five original valuation cards and comparison chart | FCFF in the DCF slot; P/E, DDM, Gordon and asset-method eligibility; no averaged fair value |
| Original three-input core-value calculator output | Eligible registered server FCFF result; local edits cannot certify a new operating model |
| Stock probability panel | Frozen model/reliability gates, with explicit abstention |
| Original VSA chart, event table, indicator cells and phase/trap frames | Completed OHLCV, causal events and reviewed indicators; no fixed phase confidence or trap probabilities |
| Original Trade Planner result cells | Shared cash/lot/fee/quote feasibility and net stop/target outcomes; draft saving retained |
| Original portfolio cards/table/allocation | Owner snapshot, entered cash after reserve, retained unpriced lots, compatible cost/P&L; no synthetic cash or return curves |
| Original portfolio holding form/removal | Versioned owner snapshot edits; preserved cash provenance and optimistic revision |
| Existing portfolio alert controls | Reviewed watch intents/evaluations and immutable acknowledgment; no sample-price triggering |
| Existing regional macro cards/sparklines | Unique compatible reviewed series for selected scope; unsupported markets/history unavailable |
| Original newsroom layouts and bookmark controls | Reviewed article excerpts and claim status text, source clocks and owner bookmarks |
| Existing assistant question inputs | Read-only metric/evidence/own-assumption query service |

### Gaps retained rather than filled with new UI

- Original financial grids have no accounting-period selector: their binding is
  explicitly TTM. Other backend Q/YTD/FY selections are not exposed here.
- Original valuation and stock/VSA pages are FPT-specific and have no issuer
  selector. The original DCF slot maps FCFF only; there is no separate FCFE slot.
- The three original calculator knobs do not specify capex, working capital,
  ownership, source lineage, scenario version or reviewed rates. Full operating
  forecasts require registered reviewed assumptions; no new editor is added.
- No original portfolio cash/currency reconciliation or account-baseline form
  exists. Missing baselines stay unavailable; lot edits cannot create cash.
  Existing browser holdings are not silently imported or confirmed.
- Actual TWR/MWR, daily P&L, benchmark curves, FX/corporate-action reconciliation
  and transaction replay lack sufficient verified history. Their existing frames
  remain unavailable instead of using generated curves or zero substitutes.
- The original alert Delete/Reopen actions have no compatible immutable-intent
  deletion/unacknowledgment API. They report this gap; they do not fake a server
  change. No new evaluation scheduler or notification channel is introduced.
- Peer medians, several market multiples, dividends, confidence/health scores,
  unsupported indicator definitions, bond/equity/commodity trend providers and
  ambiguous macro series are not invented to fill original placeholders.
- The original scenario tool lacks event identity/cutoff/maturity and evidence
  adjudication fields. It remains an explicitly illustrative comparison tool;
  the versioned event-review workflow is not presented as integrated or calibrated.
- Commodity driver stress, detailed assumption/review workflows, shadow capacity
  transitions and model-governance administration have no new member UI here.
  Their existing service/admin gates remain; no user tab or field is created.

Some original market-price charts and sample watchlist/company context remain
explicitly illustrative. They must not be treated as reviewed company facts,
live quotes or execution instructions merely because nearby calculations are
connected to services.

Validation: production build and 12 frontend unit tests passed. Six focused
browser checks passed for existing research/source details, comparison,
valuation, VSA, trade planning and portfolio behavior. The nine checked mobile
routes fit a 390px viewport, with no captured JavaScript errors.
