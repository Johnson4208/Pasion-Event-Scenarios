F06 thin causal technical diagnostics
====================================

GET /api/market/:ticker/indicators requires a current session and returns completed
OHLCV, status/coverage, source/adjustment policy/hash, indicators, causal events,
tentative phase evidence and trap observations. POST /api/admin/market/ohlcv requires
admin and reviewed provider/corporate-action assertions. Snapshots are immutable;
late/revised data known after a replay origin cannot enter that origin.

Input includes ticker, source, venue, calendar, currency, timezone,
provider_verified:true, adjustments_verified:true, adjustment_policy
(split_adjusted, total_return_adjusted, unadjusted_no_actions), and bars with
open/high/low/close, volume (null is missing), session_number, as_of/known_at and
complete. Source/calendar/corporate-action authenticity requires independent review;
the flags themselves are not provider certification. No feed was connected here.

RVOL is current volume divided by prior 20 volumes, excluding current volume.
Missing, zero/no-trades and invalid-negative volume are distinct. RSI14/ATR14 use
Wilder smoothing; MACD uses SMA-seeded EMA12/26 and signal9. OBV, CMF20, MFI14,
SMA20/60/200 and prior-only support/resistance have explicit coverage states.
Flat RSI/MFI is neutral; zero CMF denominator is unavailable. Partial bars never
produce indicators or markers. Missing session history blocks diagnostics.

Spring/upthrust/selling-climax/strength are tentative causal rule candidates, not
calibrated signals. Strength requires available SMA200 context. Every marker has
stable ID, source bar, context inputs, bar time, observed-at and reason codes.
Follow-through is a distinct later-bar event, never an upgrade backdated onto the
candidate. No stock is forced into a full Wyckoff phase and no trap percentage is
manufactured. Chart/MA overlays, legend, event table and radar remain in the native
screen, with the previous fictional demonstration behind explicit sample selection.

VSA trade ideas use the F07 /api/trades/feasibility boundary. No quantity is returned
without a complete user draft and reviewed account/lot/cost/fresh-quote checks.
Five backend technical tests passed. The earlier approval-review failure cleared
during F08 work; F06 browser verification and the combined build now pass. API
activation is performed with the F08 restart. No real OHLCV was certified by tests.
