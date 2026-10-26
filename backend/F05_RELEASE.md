F05 guarded stock analytics
==========================

Stock Analytics retains the market-context frame and four session horizons. Fixed
FPT up percentages, synthetic down percentages, bullish factors and the confidence
meter are removed. Price/chart context is explicitly illustrative. Financial metrics
default to F03 reviewed facts; supplied indicator fixtures require sample selection.

GET /api/market/stock/:ticker/analysis requires a current session and returns four
horizon-specific states, calibrated p_up/p_down or null, directional abstention,
frozen model/calibration versions, baseline Brier/skill, sample size, calibration
curve, last-valid origin, expiry and observed features. Coverage, company-health
scores and scenario weights cannot become confidence or probabilities. The down
class is explicitly a nonpositive return (including unchanged close).

Independent server service
--------------------------
POST /api/admin/market/models/freeze takes {ticker,horizon_sessions,source,
provider_verified:true,bars}. POST /api/admin/market/models/evaluate takes
{model_id,bars}. Both require current admin roles; no client probability fields
are accepted as model outputs. A trusted point-in-time provider must independently
establish source authenticity, venue calendar, corrections and complete sessions.
The provider_verified flag is an administrator assertion, not independent proof.

Bars contain offset-aware as_of/known_at, explicit consecutive session_number,
complete:true, open/high/low/close and volume. Invalid/future/incomplete bars are
rejected; negative volume is invalid and genuine zero volume is distinct.

The fixed research policy fits standardized returns1/5, SMA20 distance and vol20
with regularized logistic regression. Expanding walk-forward diagnostics use a
horizon purge. A separate later out-of-sample window fits a Platt calibrator using
the unchanged trained model. These historical diagnostics never authorize release
by themselves. Model/scaler/calibrator/policy/data snapshot freeze in SQLite with
an immutable version and hash. No final refit consumes holdout data.

After freeze, only newly completed sessions whose origins are later than the real
freeze timestamp enter the future test cohort. Their outcomes must have resolved;
the prediction origin must precede the target session. Training/calibration prefix
changes (including revisions) require a new candidate. Future outcomes cannot
alter the frozen coefficients or calibrator. The minimum test count is 80, both
classes must occur, Brier skill must exceed the frozen training base-rate baseline,
and calibration error must be <=0.10. These fixed research gates are not a claim
of sufficient production investment evidence. Labels within the future cohort may
overlap; the report discloses that they are not independent trials.

Weak/insufficient evidence yields UNCERTAIN with null probabilities. Missing or
expired models/predictions yield UNAVAILABLE. Model lifetime is bounded at 730 days;
prediction freshness is 24 hours from its completed bar, not ingestion/revision
time. UP/DOWN thresholds 0.58/0.42 apply only after reliability gates. UI polls every
30 seconds and checks expiry each second, suppressing stale percentages itself.

No actual OHLCV provider, frozen model or future-cohort dataset was supplied in
this implementation. Public forecast states therefore remain UNAVAILABLE until
those dependencies pass. Deterministic fixtures are test-only and make no model
performance claim. Financial forecasting and company valuation remain separate.

Validation: seven F05 backend model/API tests and all eight focused F01-F05 browser tests pass. The production build passes with the existing bundle-size warning. Synthetic reliability-gate fixtures are not a model-performance result. Broader historical UI regression gaps recorded in F01 remain outside these focused checks.
