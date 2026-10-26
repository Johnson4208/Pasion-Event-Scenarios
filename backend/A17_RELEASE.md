# A17 — release evidence and abstention

The admin health response now includes an explicit per-feature release manifest.
`release_governance.py` evaluates contract, source, temporal, security, feature,
version reproducibility and provider stability gates plus domain-specific gates.
Each gate requires current PASS evidence, source IDs, report ID, calculation
version, snapshot ID and a release owner. Missing, failed, future-known or stale
evidence keeps that feature REVIEW_ONLY; unrelated features evaluate separately.
Rollback triggers include stale/revised sources, security/contract failure,
version mismatch, model drift/expiry and capacity reconciliation.

The status vocabulary is SAMPLE → REVIEW_ONLY → RESEARCH_READY →
SHADOW_VALIDATED → EXECUTION_ELIGIBLE. Execution promotion has no implemented
path. Model release specifically requires nested walk-forward, a frozen champion,
future cohort, calibration/drift and untouched-holdout evidence. Existing model
validation is not relabeled as nested policy tuning. ATR/threshold/target/Kelly
tuning on an untouched holdout is not certified by this manifest.

No governed evidence-admission/release-owner workflow exists yet, so the live
manifest deliberately returns REVIEW_ONLY for every feature. The evaluator is a
testable policy primitive, not a bypass of current runtime eligibility gates.
Historical 58.1 summaries and local test passes cannot promote capabilities.

Run `.venv/Scripts/python.exe scripts/validate_release.py` to execute all backend
fixtures, frontend units and a production build. Add `--browser` for a bounded
browser suite. Each run creates a unique local `artifacts/release-validation/`
directory with suite logs and an exclusive-write JSON manifest, source SHA-256,
unchanged-code check and explicit not-run states. Logs are local artifacts;
the admin API does not expose files or logs. These are not signed/tamper-proof
external attestations. Acceptance PowerShell also now runs frontend unit tests.

Remaining gates include real provider verification, governed admission/signoff,
full reconciled portfolio/FX/corporate-action histories, validated model tuning
and operational reconciliation. No claim of live routing or production release
is made. Browser acceptance from A16 remains incomplete unless separately rerun.

Validation recorded for A17: 12 focused governance/health/Distribution tests
passed; frontend unit tests passed (11); production build passed with the
existing bundle-size warning. Complete backend discovery reached its 600-second
limit without a final summary, so its archived outcome is TIMEOUT, not PASS.
Browser validation was NOT_RUN. A separate `--focused` runner option records
GOVERNANCE_ONLY scope and does not substitute for complete acceptance. The first
archive was written before a Windows console Unicode path-print error; console
output now uses a relative ASCII path. No release promotion follows these runs.
