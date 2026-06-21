# POLYBOT Downstream Evidence Consumption

Phase: Step 3.5 of POLYBOT Life Injection

## Purpose

Downstream Evidence Consumption makes the decision organs consume refreshed evidence after Brain Mesh Activation and Live Evidence Refresh have run.

This phase safely recomputes:

- thesis profiles, so fresh orderbooks and trusted bindings can attach to current coordinator outputs
- risk decisions
- exit plans
- paper eligibility candidates
- no-trade records

This phase does not create paper intents, order intents, paper orders, live orders, fills, positions, shadow actions, or live actions.

## Runtime Contract

SYSTEM OFF blocks downstream recompute completely. No risk, exit, eligibility, or no-trade recompute runs while OFF.

SYSTEM ON allows `DownstreamEvidenceRecomputeService` to run after:

1. Brain Mesh Activation
2. Live Evidence Refresh

The recompute remains data-only and non-executing.

## Service Contract

`DownstreamEvidenceRecomputeService` coordinates existing non-executing services:

- `ThesisProfileService.build_profiles(...)`
- `RiskCoreService.evaluate_risk(...)`
- `ExitFoundationService.build_exit_plans(...)`
- `PaperEligibilityService.evaluate_candidates(...)`
- `PaperIntentGateService.build_intents(write_intents=false, write_no_trade=true)`

Paper intents are explicitly skipped in this phase. No-Trade records are refreshed for blocked candidates.

## Dashboard Truth

`GET /dashboard/api/v2/downstream-recompute` returns:

- `mock_data=false`
- allowed and active state
- latest run status and timestamp
- risk, exit, eligibility, and no-trade checked/updated counts
- before/after blocker counts
- eligible before/after
- latest downstream timestamps
- top current blockers
- execution deltas, all expected to be zero

## Safety

This phase preserves:

- SYSTEM OFF as a hard autonomous runtime block
- DATA_ONLY runtime mode
- paper/shadow/live disabled
- no paper intent creation
- no order/fill/position mutation
- no weak binding promotion
- no stale orderbook treated as fresh
- no side defaulting
- no forced risk approval, exit readiness, or eligibility

Remaining blockers are valid when evidence is still missing, weak, ambiguous, or not yet consumable by the candidate.
