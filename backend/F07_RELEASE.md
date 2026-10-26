F07 shared trade feasibility
===========================

POST /api/trades/feasibility is the single current-session, owner-scoped sizing
adapter for Planner, VSA candidates and future Portfolio/Distribution callers.
Caller labels do not change quantity, cash or lot policy. Client-provided capital,
cash, roles and owner IDs never replace server account state. Saved drafts are not
orders; neither feasibility nor draft saving reserves cash or routes execution.

POST /api/portfolio/baseline saves a manual UNVERIFIED baseline for the session
owner: currency, equity, cash, reserved_cash, sellable:{ticker:quantity}, as_of and
expires_at. A supplied status/owner cannot grant review or change ownership.
POST /api/admin/portfolio/review requires admin and an explicit owner. This is a
manual reconciliation assertion, not broker verification. F08 must later provide
the event ledger, import lineage and cash/holdings reconciliation workflow.

POST /api/admin/trades/instruments registers reviewed ticker/venue/currency, lot,
tick, fee_flat, fee_per_share, fee_rate, sell_tax_rate, slippage_bps, calendar/source
and quote:{price,as_of,session_open,session_close,max_age_seconds}. Costs use currency
amounts/fractions and slippage uses basis points. Calendar/source correctness must
be independently reviewed; this endpoint does not connect a live provider.

Decimal calculations distinguish reviewed equity risk budget from actual cash less
reservations. Whole venue lots are capped by both risk including roundtrip costs
and available cash after entry costs. Sell reductions cannot exceed owner sellable
shares. Prices must match tick increments. Stale/future quotes, invalid/off-session
calendar windows, missing FX and unreviewed/expired accounts withhold quantity.
Unsupported short borrowing/margin and Kelly edge always remain withheld; the
market-up classifier from F05 is not a target-hit probability or a Kelly input.

READY responses contain quantity, costs, cash-after, lot/tick, account/instrument
versions and quote expiry. Missing dependencies yield null quantity; verified
budgets below one lot yield explicit zero/WITHHELD. Target/stop, unresolved-at-entry
and gap/slippage scenarios have net hypothetical P&L and no invented probabilities.
Conditional target-hit rates count resolved paths; unconditional rates also count
unresolved paths. Stress outcomes do not promise stop execution or realized returns.

The existing entry/stop/target and long/short draft workflow, local editing and CSV
remain. Browser quantities use the API and expire; old saved quantities are not
recalculated by whole-share Math.floor or exported as execution instructions.
Kelly buttons are disabled. A setup can still be saved when feasibility is unknown.
Manual draft equity remains visibly a planning assumption. The account/quote
registries start empty, so new real-data sizing remains withheld until reviewed.

F15 atomic reservations and validated short/edge policies are future work. This
release does not claim live execution, borrow availability or automatic broker data.

Validation commands:
python -m unittest discover -s backend -p 'test_feasibility*.py'
npm run test:ui -- tests/f06.spec.js tests/f07.spec.js
npm run build

All eight feasibility calculation/API tests passed. The earlier approval-review
usage-limit failure cleared during F08 work; F07 browser checks and the combined
build now pass. API activation occurs with the F08 restart. No reviewed real
accounts, market quotes or broker execution were certified by these fixtures.
