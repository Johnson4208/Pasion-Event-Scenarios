# A16 — API and frontend boundary integration

The existing Pasion endpoints remain the canonical boundary:

| Route | Contract and authority |
| --- | --- |
| GET /api/research/company/:ticker?period=TTM | Member; accepted facts, gated ratios, evidence IDs |
| POST /api/research/valuation | Member; owner assumptions, method-specific eligibility |
| POST /api/trades/feasibility | Member; server-loaded owner account and instrument rules |
| GET /api/portfolio/snapshot | Member; own manual holdings/cash, as-of and coverage |
| POST /api/admin/distribution/shadow | Admin; alias for candidate admission; withheld allocation |
| GET /api/admin/distribution | Admin; review records and separate audit-only capacity ledger |

No new share-capacity write endpoint is introduced. Existing document routes,
hash navigation, preferences, saved layouts and styles remain in place.

`src/researchApi.js` is a small runtime boundary used by company/comparison reads
and trade feasibility. Adjacent TypeScript declarations document availability,
metric and feasibility interfaces; the existing JSX app is not converted to
TypeScript. HTTP/version failures surface unavailable states. Numeric presence
never supplies READY status. Metric rendering preserves zero and exact source
text, requires units/currency, and suppresses invalid/nonfinite values. Planner
rendering rejects invalid expiry, quantity/lot, currency and amounts, and
suppresses stale/withheld quantities. Existing request cancellation prevents
old symbol/draft responses from replacing current state.

Persistence remains separated by domain: finance facts/report contexts and
observations, immutable assumptions/runs, reviewed market snapshots/models,
private portfolio state/manual events, and admin Distribution audit tables.
Additive CREATE TABLE initialization preserves existing records; no destructive
rewrite or SolvAI database import is introduced. This change is not a complete
production schema-migration framework or conversion of every feature adapter.

Validation includes runtime adapter tests, backend owner/admin boundaries,
existing finance/portfolio persistence tests, frontend build, and focused browser
flows for company research, draft planning, portfolio and admin Distribution.
The existing large-bundle build warning remains.

Recorded validation: 11 frontend unit tests, 24 focused backend tests, six
A14/A15 tests, and production build passed. Three Distribution tests passed
again after adding authenticated alias validation. The combined browser run
did not complete reliably: finance navigation timed out on page load, while
comparison and draft-planning checks passed in the retry. Finance navigation
now waits for DOM readiness; the final combined rerun was stopped during slow
browser startup. Full browser acceptance is therefore not claimed.
