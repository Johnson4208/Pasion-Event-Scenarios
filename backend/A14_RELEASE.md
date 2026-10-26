# A14 — conservative candidate admission

The admin-only Distribution candidate route now delegates context gates to
`distribution/engine.py`. Candidate records carry policy version, research
context and evidence ID, with null allocation weight and quantity and
`calibrated=false`. Shared feasibility continues to gate cash, holdings, lots,
quote age and account/instrument versions. Distribution additionally requires
an explicit IANA quote timezone and reviewed liquidity cap.

The near-equivalent helper rejects mixed utility models, versions, definitions,
statuses or horizons and never adds a worse candidate to force diversity.
It is a research primitive, not an exposed ranking or allocation service.

Release limitation: there is no versioned name/sector/currency exposure policy
evaluator yet. All newly submitted candidates therefore remain WITHHELD with
an explicit unavailable-policy reason, even when admin review checkboxes are
checked. No numeric allocation or real routing is enabled. Existing atomic
shadow-slot simulation and replay protection remain separate from capital.
Pre-A14 candidate records require policy revalidation before a new reservation.

Validation: six A14 and Distribution tests passed, including admin access
isolation, concurrent idempotency, single-shot release and capacity bounds.
