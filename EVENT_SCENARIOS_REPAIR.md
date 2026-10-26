# Event Scenarios repair — 2026-10-24

Analyze now retrieves news and prepares the existing historical forecast independently. A news outage does not suppress a valid historical model. Complete historical families are shown at their actual size, including 3, 5 and 7 outcomes, with probability estimates, 95% rate intervals, sample counts and validation details. Occurrence probabilities remain separate marginals; they are never normalized to sum to 100%.

For the ten overlapping news pathways, the display explicitly separates:

- Experimental estimates: a transparent sensitivity illustration using an assumed 50% prior, not an empirically established event probability. The 25%–75% prior sensitivity range is not a confidence interval. These estimates are not calibrated to the selected duration.
- Evidence balance: signed supporting minus opposing evidence divided by all scope-eligible evidence weight. This determines pathway ranking.
- Relative news share: a normalized allocation of net supporting news, only when the existing concentration checks permit it. It is not an outcome distribution.

Missing estimates display a dash and an explanation, never a fake 0%. Unsupported horizons and insufficient evidence remain unavailable. Historical preparation still depends on an operator-provided reviewed model catalog or supported real historical series (US VIX and mortgage rates); this patch does not invent historical data for unsupported regions or topics.

The experimental update now uses each source's audited signed pathway contribution. The previous distance formula could make a supporting report reduce the odds of a mild positive pathway. Explicit stability can now contribute to the stability estimate. Duplicate clusters and external context remain excluded from influence. Unknown reporting no longer enters the stable/mixed evidence bucket. Expected/projected future claims are not treated as observed events; unemployment direction and calendar-month May handling are corrected.

The browser validates complete model contracts instead of trusting presentation flags. Legacy experimental v1 numbers are rejected. Request timeouts, locked controls and query matching prevent stale results from appearing under new filters. Saved reports retain complete models and can be reopened with their original query and date. The evidence panel shows support/challenge/context roles, scope, provenance and signed contributions.

## Verification

- Python event/API regression suite.
- JavaScript unit tests for model contracts, malformed values and share concentration.
- Chromium interaction tests for historical and experimental displays, missing data, source outages, save/reopen, occurrence probabilities, stale-request protection, translated filter values and mobile overflow.
- Production Vite build.

Tests use explicitly synthetic fixtures. They verify software behavior, not real-world predictive accuracy. Live provider access and the deployment's private historical catalogs were not validated in this environment.
