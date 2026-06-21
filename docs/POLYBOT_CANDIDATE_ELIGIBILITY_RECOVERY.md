# POLYBOT Candidate Eligibility Recovery

Phase: Candidate Eligibility Root Cause Fix: SIDE + RISK + EXIT READINESS RECOVERY

## Purpose

This phase adds a controlled eligibility recovery pass after downstream recompute. Its job is to consume real refreshed evidence and unblock candidates only when the evidence is structurally valid.

The recovery pass is not a trading engine. It does not invent side, force risk approval, force exit readiness, fabricate eligibility, or create live/shadow/real orders.

## Runtime Position

Under SYSTEM ON, the runtime order is now:

1. Market/data refresh
2. Brain Mesh Activation
3. Evidence Refresh
4. Downstream Evidence Recompute
5. Candidate Eligibility Recovery
6. Paper Intent Gate
7. Safe Paper Execution
8. Paper Exit Loop and PnL Ledger

SYSTEM OFF blocks the recovery pass.

## Recovery Contract

`CandidateEligibilityRecoveryService` performs these steps:

1. Check SYSTEM power and State Governor permissions.
2. Inspect current candidate, thesis, risk, exit, binding, orderbook, and side evidence.
3. Recover side only from deterministic trusted sources.
4. Re-run Risk Core, Exit Foundation, Paper Eligibility, Paper Intent Gate, and Safe Paper Execution.
5. Record a run summary in `candidate_eligibility_recovery_runs`.
6. Expose candidate-level root-cause traces through dashboard truth.

## Valid Side Evidence

Side recovery is intentionally narrow. A candidate side may be recovered only from:

- trusted `signal_market_links.link_evidence_json.matched_side` with `YES` or `NO`, sufficient confidence, and no manual review requirement
- explicit coordinator metadata side/direction when it is `YES` or `NO`, runtime-generated, and not dry-run

The service does not default to `YES`.
The service does not default to `NO`.
Ambiguous, weak, stale, or missing evidence keeps `MISSING_SIDE` active.

## Risk / Exit / Eligibility Rules

Risk can improve only if real required evidence is present.

Exit can become ready only if the current risk decision, side, market, fresh orderbook, mid price, and deterministic exit rules are valid.

Paper eligibility can become `ELIGIBLE` only if Risk and Exit are valid and current evidence satisfies the existing eligibility contract.

Paper intents and paper execution remain downstream safety layers. They are not forced by this phase.

## Dashboard Truth

Added:

- `GET /dashboard/api/v2/eligibility-recovery`

The endpoint returns:

- `mock_data=false`
- latest recovery run
- before/after eligibility, risk, exit, side, paper intent, and paper execution counts
- top blockers before/after
- candidate-level trace for the latest blocked candidates
- `no_valid_paper_intents_reason`
- safety deltas for paper, real, and live execution artifacts

## Current Runtime Finding

Runtime recovery ran successfully, but no candidates became eligible because the production DB currently has no deterministic side evidence:

- trusted links with `matched_side`: `0`
- coordinator decisions with explicit side: `0`
- brain outputs with explicit side: `0`
- thesis profiles missing side: all runtime thesis profiles inspected

Therefore the correct current outcome is:

- candidates remain blocked
- `MISSING_SIDE` remains active
- risk remains blocked
- exit remains blocked
- paper intents remain `0`
- paper orders/fills/positions remain `0`

This is a safe YELLOW outcome, not a fake GREEN.

## Safety

The recovery service preserves:

- SYSTEM OFF blocks runtime work
- DATA_ONLY does not enable live trading
- live/shadow/real orders remain disabled
- no forced side
- no forced risk approval
- no forced exit readiness
- no forced eligibility
- no fake paper intents
- no paper or live execution without valid lineage
- no mutation of real orders/fills/positions

## Next Required Fix

The next recovery step should produce deterministic side evidence upstream, preferably by enhancing market binding/evidence refresh to persist `matched_side` from real Polymarket token-side mapping when available.

Do not proceed to soak or paper readiness based on current runtime candidates until side evidence exists.
