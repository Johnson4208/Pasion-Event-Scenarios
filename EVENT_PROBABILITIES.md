# Event Scenarios: complete outcome comparisons

The screenshot with “prior 50%, uncalibrated” is the historical experimental
interface. Its 54% is not validated. This version never turns headline tone,
story counts, evidence balance, or a missing source into a probability.

Every model-defined outcome appears together, with its resolution rule,
probability estimate, 95% interval and gap to the largest estimate. The default
order follows the definitions; probability sorting is optional. Estimates
within 3 percentage points are identified as close, without declaring a
winner. Values are rounded independently, so rounding does not systematically
give one outcome an extra tenth of a percentage point.

Two probability questions are supported:

- `END_STATE`: the state at the end of the selected calendar horizon. Outcomes
  must be mutually exclusive and exhaustive; the unrounded probabilities sum
  to one. Include a properly defined residual outcome when needed.
- `OCCURRENCE`: whether each event occurs at least once during the horizon.
  Events can coexist. Each receives its own marginal probability; the sum is
  deliberately not forced to one. Joint probabilities are not inferred.

The number, IDs, titles and rules come from a versioned model family rather
than the ten overlapping research-path templates. Each context currently
supports 2–100 outcomes and one active family per basis. Changing the outcome
definition requires rebuilding and checking the whole model. A new outcome
cannot simply be assigned zero or renormalized out of the existing model.
Research pathways remain visible together as a separate evidence measure;
their scores do not become probabilities for the model's outcome family.

## What is available now

The primary application now also offers automatic source-backed research estimates
for explicitly supported quantitative questions. See
[EVENT_SERIES_RESEARCH.md](EVENT_SERIES_RESEARCH.md) for collection, measurable
end states, retrospective holdout checks, uncertainty and prospective tracking.
These estimates do not claim future calibration or numerical conditioning on news.

The reviewed model catalog reader, historical estimator, offline builder,
validation gates, eight public-observation collection profiles and automated
regressions are implemented. [EVENT_OUTCOME_SOURCES.md](EVENT_OUTCOME_SOURCES.md)
records their coverage, live-access blocker and remaining source gaps. **No real model
catalog or adjudicated historical event dataset is bundled.** Outside supported
automatic research questions, a reviewed catalog must cover the selected factor,
region, horizon and basis before a family is displayed. The app does not fill missing
probabilities with 50%, equal shares, or headline-derived percentages.

The implemented estimator is a **historical reference-class baseline**. It
does not condition on today's news or promise that a future event behaves like
the historical sample. A calibrated, news-conditioned forecast requires a
separate model, point-in-time features, genuinely later evaluation and ongoing
prospective monitoring. It has not been implemented or validated by this
catalog path. Generic Vietnam conflict-risk forecasting remains unsupported until
its measurable definitions, sources and outcome history are established.

## Historical data and model definitions

Keep private data in `backend/private-event-models/` (ignored by Git). Keep the
original source dataset for reproducing the artifact's SHA-256 digest. Each
input model needs the following JSON structure; replace every placeholder
with a reviewed definition and real records:

```json
{
  "schema_version": 1,
  "models": [{
    "model_version": "your-model-version",
    "family_id": "your-family-id",
    "definition_version": "your-definition-version",
    "question": "Your measurable event question",
    "sampling_policy": "Population, inclusion rules, exclusions, independence assumptions and revision policy",
    "context": {
      "category": "Economy",
      "factor": "Inflation",
      "focus": "Vietnam",
      "horizon": "30 days",
      "basis": "END_STATE"
    },
    "scenarios": [
      {"id": "first", "title": "Your first outcome", "resolution_rule": "Source, unit, threshold, baseline and maturity rule"},
      {"id": "second", "title": "Your complementary outcome", "resolution_rule": "A complementary, exhaustive measurable rule"}
    ],
    "validation_start": "REPLACE_WITH_A_TIMEZONE_AWARE_ISO_TIMESTAMP",
    "expires_at": "REPLACE_WITH_A_TIMEZONE_AWARE_ISO_TIMESTAMP",
    "cases": [{
      "id": "unique-real-case-id",
      "group_id": "independent-observation-group",
      "reviewed": true,
      "origin_at": "REPLACE_WITH_A_TIMEZONE_AWARE_ISO_TIMESTAMP",
      "maturity_at": "REPLACE_WITH_ORIGIN_PLUS_30_CALENDAR_DAYS",
      "resolved_at": "REPLACE_WITH_WHEN_THE_RESULT_WAS_KNOWN",
      "source_url": "https://your-source.example/actual-resolution",
      "outcome_id": "first"
    }]
  }]
}
```

For `OCCURRENCE`, each case instead supplies an `outcomes` object mapping
**every** outcome ID to `true` or `false`. Missing labels are rejected, never
treated as negative observations. An outcome observed early in the period
still needs a matured period to give all events the same observation window.
`maturity_at` must equal the origin plus the selected calendar-day horizon.
`resolved_at` cannot precede maturity or be in the future.

## Estimation and validation

For end states, estimate every rate from the **same** training sample with a
symmetric Jeffreys half-count: `(outcome_count + 0.5) / (N + K/2)`. The posterior
is Dirichlet. For overlapping events, estimate each marginal with a Beta
posterior: `(occurrence_count + 0.5) / (N + 1)`. The 95% equal-tail credible
intervals are computed from the corresponding beta distributions. These are
intervals for historical rates under the model assumptions, not coverage
guarantees for future events or simultaneous intervals for the whole family.

There is no fixed per-scenario 50% starting probability, 70% ceiling or
keyword-derived likelihood ratio. Symmetric smoothing has a small documented
effect and is **not** evidence that the population itself is balanced.

The builder and runtime checker enforce:

- At least 100 training groups and 100 later holdout groups, with at least five
  observations of every outcome in each partition. Overlapping events also
  require at least five non-occurrences. Rare outcomes therefore need more
  data; the minimum sample size alone is not proof of reliable calibration.
- Unique case and observation-group IDs. Group identifiers are an operator's
  sampling claim; uniqueness alone cannot prove statistical independence.
- Resolved training cases known strictly before the first holdout origin.
  Cases crossing that boundary are embargoed. Training never uses holdout
  labels, and the posterior is not refit using the holdout.
- Out-of-sample Brier score, log loss and per-outcome rate drift. Drift must
  fall within 1.96 pooled standard errors and 10 percentage points; these are
  explicit application policy thresholds, not universal calibration criteria.
  Do not repeatedly tune a definition on the same holdout and continue calling
  it untouched: acquire a new holdout when selecting models from these results.
- Exact context and versioned complete outcome coverage. Multiple active
  models for one context are rejected rather than selected by a favorable
  probability. The local catalog is never writable through a browser endpoint.
- A maximum validity window of 90 days after operator review, with expiry
  checked even when the retrieved news is cached.

Catalog metadata cannot establish source truth or remove selection bias.
Review outcome labels, regional comparability, revisions and structural
changes separately. Record forecast snapshots before maturity and evaluate
their real outcomes prospectively before claiming calibrated future forecasts.

## Build and enable a catalog

On Windows, after preparing real input records:

```cmd
.\.venv\Scripts\python.exe backend/event_forecasts.py --input backend/private-event-models/cases.json --output backend/private-event-models/catalog.json --reviewer "Your reviewer name"
```

The command writes nothing if a family fails its holdout checks. It never
fetches labels, invents cases, sends data externally, or promotes the test
fixtures into live models. Keep real model input and output out of source ZIPs.

In **CMD**, enable that local catalog before starting the application:

```cmd
set PASION_EVENT_MODELS_PATH=C:\absolute\path\to\backend\private-event-models\catalog.json
npm.cmd run dev:full
```

In **PowerShell**, the environment assignment is:

```powershell
$env:PASION_EVENT_MODELS_PATH='C:\absolute\path\to\backend\private-event-models\catalog.json'
npm.cmd run dev:full
```

With no valid file, the application continues as evidence research. A valid
reference baseline remains accessible when current news transport is down;
the missing feeds are disclosed and cannot increase or reduce its estimates.
Saved reports preserve the original complete family, definitions, model
metadata and basis. Opening a snapshot does not silently update its rates.

All numerical fixtures under `tests/fixtures/event-*.json` are explicitly
synthetic regression data. They demonstrate display and arithmetic only and
are never loaded by the live catalog reader.
