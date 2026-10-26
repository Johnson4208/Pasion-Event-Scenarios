F08 private manual portfolio ledger
===================================

Portfolio Monitor defaults to an authenticated server ledger. Overview, Holdings,
Watchlist and Alerts remain in the native portfolio layout with industry grouping.
No opening holdings, cash reserve or benchmark performance are fabricated. The
old VND demonstration is available only through explicit illustrative-sample mode.
Browser holdings import is explicit and starts unverified, with no inferred cash.

GET /api/portfolio/snapshot reads only the current session owner's data; owner
query parameters and submitted owner fields do not grant cross-user access, even
to another admin. POST /api/portfolio/snapshot writes a full private observation
with expected_revision, currency, cash, reserved_cash, offset-aware as_of, source
(MANUAL_CONFIRMED or IMPORTED_UNVERIFIED), lots, watchlist and research targets.
Cash/reserves may be null when unknown; explicit zero remains zero. Lots retain
separate IDs, ticker, quantity, unit_cost, currency, sector and source. Watchlist
entries and targets never create holdings, orders, fills or cash reservations.

SQLite state/event tables have owner foreign keys, deletion cascades, immutable
revision event snapshots and optimistic compare-and-update. Conflicting revisions
return 409. The event type is MANUAL_SNAPSHOT; edits are not broker transactions.
Editing invalidates F07 reconciliation, clears prior sellability/equity authority
and requires a new explicit account baseline before reviewed sizing can resume.

Marks come from F07's reviewed instrument/quote registry, with as-of/session and
expiry checks. POST /api/admin/portfolio/fx registers reviewed from/to rate, as_of,
expires_at and source; only admins can register these shared inputs. Provider/FX
authenticity remains a deployment/integration review requirement, not inferred
from a client flag. No real quote or FX provider was connected here.

Every lot remains visible with missing-price/FX/cost reasons. Total value and all
weights stay null until all marks and quote FX plus explicit cash are covered.
Known subtotals are labeled known values; unpriced assets are never normalized
away. Concentration and sector/currency exposure use the complete denominator,
including entered cash. Cost basis in account currency is retained per lot; foreign
costs require historical acquisition FX before actual account-currency unrealized
P&L can be shown. Today's FX is not silently used as historical cost FX.

Risk contributions require complete weights, at least 60 aligned same-currency
completed-session returns for every holding and finite covariance. The diagnostic
uses a declared 50% diagonal-target shrinkage policy; contributions sum to daily
portfolio volatility. Missing FX/return coverage blocks risk rather than dropping
an asset or redistributing its weight. This is a risk estimate, not market probability.

TWR/MWR and realized performance remain unavailable because manual snapshots do
not establish reconciled transactions, deposits, withdrawals, fills or cash-flow
history. Corporate-action/transaction/FX-history v2 and verified benchmark curves
remain future work. No order management is added to the manual MVP.

Checks:
python -m unittest discover -s backend -p 'test_portfolio*.py'
npm run test:ui -- tests/f06.spec.js tests/f07.spec.js tests/f08.spec.js
npm run build

Validation: all 143 backend tests, all 11 focused F01–F08 browser tests and the
production build pass. The existing bundle-size warning remains. F06/F07 pending
browser checks were completed and the API was restarted with F06–F08 active.
Broader historical UI regression gaps documented in F01 are outside these focused
checks. Real marks/FX/transaction histories were not certified by test fixtures.
