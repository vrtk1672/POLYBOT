# V2 Neural Mesh Part 4C-O: Thesis Profile Foundation

## Purpose

Thesis Profile Foundation creates a formal, auditable thesis layer between runtime Coordinator Decisions and any future Paper eligibility. A thesis explains why a market is being considered, which side is known, what evidence exists, what evidence is missing, what invalidates the idea, and what risk notes must be handled before Paper.

This phase is non-executing. It does not enable Paper, create order intents, create orders, create fills, create positions, approve risk, create exits, or call AI.

## Runtime Thesis Contract

The new runtime thesis layer is stored in `thesis_profiles`. It is separate from legacy `position_thesis_profiles`, which remains available for position-oriented thesis contracts.

Allowed thesis statuses:

- `COMPLETE`
- `INCOMPLETE`
- `BLOCKED`
- `WEAK`
- `ERROR`

Allowed thesis types:

- `RUNTIME_COORDINATOR_THESIS`
- `BLOCKED_NO_TRADE_THESIS`
- `HOLD_FOR_MORE_EVIDENCE`
- `WEAK_SIGNAL_THESIS`

Hard rules:

- `COMPLETE` requires `market_id`.
- Missing market, fresh orderbook, signal-market binding, source trace, lineage, or provenance keeps a thesis incomplete or blocked.
- `paper_candidate_allowed=false` for every 4C-O thesis.
- `risk_required=true` and `exit_required=true` for every thesis.
- Dry-run Coordinator Decisions are ignored for runtime thesis creation.

## Evidence Rules

Runtime thesis profiles are derived from runtime Coordinator Decisions only:

- `metadata_json.generated_by=runtime`
- `metadata_json.producer_name=runtime_coordinator_adapter`
- `metadata_json.is_runtime_generated=true`
- `metadata_json.is_dry_run_generated=false`
- `execution_allowed=false`

Complete thesis profiles require:

- runtime Coordinator Decision
- non-dry-run provenance
- `market_id`
- source Brain/Signal trace
- fresh `orderbook_snapshots` row for the market
- signal-market binding when source Signals are present

`NO_TRADE` Coordinator Decisions create `BLOCKED_NO_TRADE_THESIS` profiles. `PAPER_CANDIDATE_BLOCKED` and missing-evidence cases create incomplete or blocked profiles, never Paper-ready candidates.

## APIs

- `POST /thesis/profiles/build`
- `GET /thesis/profiles/recent`
- `GET /dashboard/api/v2/thesis`

Dashboard mesh includes:

- `layers.thesis_profiles`
- `flow.thesis_profiles`
- `readiness.thesis_summary`

## Safety

Thesis profiles are explanatory evidence only. They are not Paper eligibility candidates, intents, orders, fills, positions, risk approvals, exit plans, or execution actions. `paper_ready=false` remains mandatory.

## Current Runtime Result

Runtime verification created `100` thesis profiles from `100` runtime Coordinator Decisions. All `100` are blocked thesis profiles because the current runtime Coordinator truth is `NO_TRADE`, with missing binding/orderbook/market evidence still visible.

`NO_THESIS_PROFILES` is resolved because real runtime thesis profiles now exist. Thesis completeness blockers remain active, alongside `NO_RISK_CORE`, `NO_EXIT_FOUNDATION`, `NO_PAPER_ELIGIBLE_SIGNALS`, and execution blockers.

## Next Phase

Recommended next phase: Risk Core Foundation or freshness/binding recovery needed before any Paper Eligibility Gate. Risk and Exit remain mandatory before Paper candidates.
