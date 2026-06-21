# POLYBOT Post-Side Risk + Exit Readiness

## Purpose

Post-side Risk + Exit Readiness Recovery runs after deterministic side recovery and downstream recompute. Its job is to let existing Risk, Exit, and Eligibility gates consume current side, trusted binding, fresh orderbook, mid price, and thesis evidence.

It does not force approval, exit readiness, eligibility, paper intents, paper orders, fills, positions, or live execution.

## Runtime Contract

Under SYSTEM ON, the runtime order includes:

1. Data / Market Refresh
2. Brain Mesh Activation
3. Evidence Refresh
4. Deterministic Side Evidence Recovery
5. Downstream Evidence Recompute
6. Post-Side Risk + Exit Readiness Recovery
7. Candidate Eligibility Recovery
8. Paper Intent Gate
9. Safe Paper Execution + Position Ledger
10. Paper Exit Loop + PnL Ledger

Under SYSTEM OFF, recovery is blocked and no post-side recovery rows are created.

## Recovery Rules

The service only clears stale thesis blockers when real current evidence exists:

- side is YES or NO
- trusted signal-market binding matches side
- fresh OK orderbook exists
- mid price exists
- source signal and brain trace exist
- confidence is sufficient

If those requirements are not met, candidates remain blocked with precise missing evidence.

## Evidence Consumption Fixes

Risk, Exit, and Eligibility input repositories now prioritize recently updated evidence:

- Risk reads thesis profiles by `updated_at`
- Exit reads risk decisions by `updated_at`
- Eligibility reads exit plans by `updated_at`

This prevents fresh recovered evidence from being hidden behind newer blocked inserts.

## Dashboard

`GET /dashboard/api/v2/risk-exit-readiness` returns DB-backed truth:

- latest recovery status
- candidates with side
- Risk before/after
- Exit before/after
- Eligibility before/after
- Paper Intent before/after
- top blockers
- 10-candidate trace
- live and real order safety fields

`mock_data=false`.

## Safety

The phase keeps:

- live orders at 0
- real orders unchanged
- canonical positions unchanged
- no direct Paper Intent or Paper Execution call from the recovery service
- existing StateGovernor and SystemPower gates intact
