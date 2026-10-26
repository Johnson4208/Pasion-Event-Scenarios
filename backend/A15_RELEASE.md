# A15 — audit-only capacity ledger

`distribution/capacity.py` adds a separate shares ledger. Existing F15 review
slots are not treated as market volume or capital. The admin-only Distribution
GET response includes its capacity audit. No public write route, broker adapter,
candidate allocation or cash reservation is enabled.

Immutable budgets identify venue, symbol, side and window; wildcard parents
allow shared platform/venue budgets. Parent and child side/windows must match.
BUY and SELL loads cannot net. Admission requires explicit reviewed same-window
tape provenance; no ADV percentage default is supplied. This remains an internal
research contract, not independent certification of a market provider.

Offer, Plan, Ordered, PartialFill, Fill, CancelRequested, CancelConfirmed,
Expired, LateFill, Bust and ReconciliationRequired are distinct immutable events
with source IDs. Order replaces offer load. Fills count through their window;
cancel confirmation frees only unfilled shares. TTL releases only unsubmitted
offers/plans, never orders. Late fills retain additional load and corrections
freeze affected shared budgets pending reconciliation. No automatic resolution
or history rewriting is implemented.

Callers must initialize schema then hold BEGIN IMMEDIATE through commit/rollback
on one SQLite host. Revision CAS and exact-payload idempotency protect retries;
shared parent usage is checked in the same transaction. Multi-host operation
requires a shared coordinator. Repeat-weight research is intentionally not wired
to selection without validation. User cash/holdings reservations and broker
reconciliation remain future separately gated work; A14 candidates stay withheld.

Validation covers concurrent 700-share requests under a 1,000-share parent,
retry conflicts, offer replacement, partial fills, cancellation, late fills,
bust holds, revision conflicts, TTL and missing tape verification, alongside
the existing admin access and atomic review-slot tests.
