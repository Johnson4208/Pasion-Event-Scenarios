# F09 — macro vintages and commodity context

Implemented in the native Macro Regime Monitor and reviewed Company Research. No macro provider credentials or reviewed observations were supplied. Every scope therefore starts UNAVAILABLE, and old generated curves require explicit sample mode.

## Contracts

- Authenticated GET `/api/research/macro?scope=world|europe|americas|asia|vietnam|unitedStates|japan&origin=<offset timestamp>` returns independent scope coverage, actual observation charts, units, local publication calendar, revision, release_at, known_at, expiry and source.
- Admin POST `/api/admin/macro/observations` registers an immutable series definition and appends reviewed observations. `known_at` is at least the actual acceptance time; source-side historical publication dates cannot backdate internal availability. Read selection uses the latest eligible vintage per observation period. Equal-time ambiguity, missing values and expired coverage suppress current factors and fit. No fallback to another country or previous revision.
- Series fields: `id, name, scope, kind` (cpi/policy_rate/labor/fx/growth), `unit, frequency` (daily/monthly/quarterly/annual/event), `timezone, calendar, provider, source_url` (public HTTPS), `reviewed:true`. Optional immutable `rule:{low,high,meaning}` is in the series' own units and needs explicit reviewer judgment.
- Observation fields: `period_start, period_end, value` (decimal or null), `release_at, known_at, expires_at` (offset timestamps), `revision`. Future published values are rejected. Store: `macro.sqlite3`, immutable definitions and append-only vintage IDs.
- Regime fit is a threshold context heuristic. All five factors must each have exactly one available reviewed rule. It returns WITHIN_ALL_REVIEWED_RANGES or OUTSIDE_REVIEWED_RANGES with series IDs, never direction, weights or probability. Partial coverage cannot produce a complete fit.
- Admin POST `/api/admin/macro/exposures` requires an existing issuer's accepted, nonmissing F03 `fact_ids` and explicit segment economic review. Fields: `ticker, segment, commodity, grade, location, volume_unit, currency, contract_reset, inventory_lag, hedge_scope, period_start, period_end, output_volume, input_volume, output_repricing_fraction, input_repricing_fraction, expires_at, reviewed:true`. Fraction ranges are 0–1; volumes are nonnegative. Fractions describe effective price-reset volume for the stated scenario period. Mapping IDs are immutable; a later review creates a new mapping.
- GET `/api/research/commodity-exposures?ticker=...` exposes reviewed economic mappings, with their source fact IDs and clocks. It never exposes raw admin documents or reviewers. Mappings are shared research evidence, not user portfolio positions.
- POST `/api/research/commodity-stress` requires `exposure_id, currency, volume_unit, output_price_delta, input_price_delta, pass_through, hedge_pnl, incremental_costs` and optional origin. Signed price shocks are in currency/physical unit; other inputs are currency totals for the mapping period. Costs are nonnegative. Pass-through is an incremental signed effect beyond direct repricing; hedge PnL must not be included twice in repricing fractions.

Delta EBIT = output volume × output repricing fraction × output price shock − input volume × input repricing fraction × input price shock + incremental pass-through + hedge PnL − incremental costs. Decimal bridge and complete mapping/assumption lineage appear in Company Research and can be exported. Scenario inputs remain unverified assumptions; the result cannot label fair value or silently modify F04. No FX conversion, commodity execution, hedge orders or automatic commodity-to-stock forecasts.

## Operational limits and review

Admission is an administrator's explicit source/economic assertion; public HTTPS metadata is not automatic provider verification. The operator must review release schedules, regional aggregation methodology, unit/definition semantics, segment contract resets, hedges and evidence before ingestion. There is no universal country rule, seeded market data, or automatic scheduled fetcher. Current registry covers only the native scope choices. UI charts use up to 240 selected observations, with real dates and gaps for missing values; original sample navigation and chart arrangements remain available.

Production identity/storage review from F01 remains required. F09 does not activate brokerage, calibrated macro probabilities or valuation eligibility.

## Validation

F09 core/API checks cover acceptance-time origin gates, revision isolation, missing revision suppression, expiry and ambiguous vintages, country isolation, immutable units, future/nonfinite rejection, five-factor regime gating, adverse producer commodity economics, evidence/currency/origin gates and server roles. Browser checks exercise country navigation, empty coverage and explicit sample mode. See test_macro_evidence.py, test_macro_api.py and tests/f09.spec.js.

Validation completed: 150-test backend regression run passed; after the final regime/evidence tightening, all 8 focused F09 backend/API tests passed. The 11 existing F01–F08 focused browser checks passed, and both F09 browser checks passed (country/sample navigation and Company Research shock form/bridge). Production build passed with the existing large-bundle warning. The local API/frontend were restarted with F09 active. Broader historical browser suite gaps remain as recorded in F01; test fixtures do not certify real provider or issuer economics.
