# PASION Administrator Trading & Distribution Monitor

## Scope
The existing PASION workspace interface remains intact. The Admin section now has **Trading & Distribution Monitor**, separate from the existing **Shadow Distribution** policy-control desk.

## Read-only integration
- `GET /api/admin/distribution/monitor` -> `backend/admin_distribution_analytics.py`.
- Server permission gate: the existing `Handler.distribution_api()` calls `require_admin()` before any database access.
- Manual BUY/SELL records are read from `portfolio_transactions`; these are observations, **not broker-confirmed fills**.
- Group notional by currency; do not add USD to VND.
- Shadow candidate counts and WITHHELD status come from `distribution_candidates`.
- Shadow slots are derived from current pool and reservation data; **not shares, tape volume, execution or cash**.
- Broker trading volume and top executed traders are explicitly unavailable until verified order/fill data exists.
- Current safety gate `VERIFIED_NAME_SECTOR_CURRENCY_EXPOSURE_POLICY_UNAVAILABLE` remains unchanged.

## Local run
Run backend and frontend following `README.md`; navigate to Admin > Trading & Distribution Monitor. This view requires the actual Python backend. Static GitHub Pages cannot serve the new endpoint.

## Validation
`python -m unittest discover -s backend -p 'test_admin_distribution_analytics.py' -v`

## Next integration steps
1. Versioned and verified per-venue market tape, trading session clocks, execution timestamps.
2. Consent/access controls and separate broker-confirmed order/fill/cancel/bust ledger (do not mutate manual snapshots into fills).
3. Audited account ranking methodology: executed notional by currency/time window, late fills and duplicate ID reconciliation.
4. Concentration policy by instrument/sector/currency/account; candidate comparison only for compatible utilities.
5. Connect the share-based capacity ledger with shadow distribution atomically, then pass concurrency/replay tests before considering controlled rollout.
