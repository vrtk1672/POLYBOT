# POLYBOT Deterministic Side Evidence Recovery

## Purpose

This phase adds deterministic YES/NO side recovery for the Brain Mesh runtime. It persists `matched_side` only when real market/token evidence proves the side, then propagates that side into paper eligibility candidates through trusted lineage.

This phase does not approve risk, force exit readiness, force eligibility, create fake paper intents, or enable live/shadow execution.

## Deterministic Side Contract

Valid sources:

- `token_id == markets_v2.yes_token_id` -> `matched_side=YES`
- `token_id == markets_v2.no_token_id` -> `matched_side=NO`
- Token IDs may come from structured runtime evidence such as `signal_market_links.link_evidence_json`, `neuron_signals.evidence_json`, or `neuron_signal_bindings.lineage_json`.

Invalid sources:

- title sentiment
- fuzzy text only
- positive/negative news sentiment
- default YES
- default NO
- weak binding
- stale binding
- ambiguous token mapping

## Persistence

Side evidence is persisted on:

- `signal_market_links.matched_side`
- `signal_market_links.side_source`
- `signal_market_links.side_source_id`
- `signal_market_links.side_confidence`
- `signal_market_links.side_evidence_json`
- `signal_market_links.side_resolved_at`
- `signal_market_links.side_rejected_reason`
- matching columns on `neuron_signal_bindings`

Run truth is persisted in `side_evidence_recovery_runs`.

## Runtime Order

The runtime order under SYSTEM ON is now:

1. Data / Market Refresh
2. Brain Mesh Activation
3. Evidence Refresh
4. Deterministic Side Evidence Recovery
5. Downstream Evidence Recompute
6. Candidate Eligibility Recovery
7. Paper Intent Gate
8. Safe Paper Execution + Position Ledger
9. Paper Exit Loop + PnL Ledger

SYSTEM OFF blocks side recovery.

## Dashboard Truth

`GET /dashboard/api/v2/side-evidence` reports:

- `mock_data=false`
- side recovery allowed/status
- latest side recovery run
- links checked
- token mappings checked
- sides recovered/rejected
- candidates with side before/after
- trusted links with matched side
- bindings with matched side
- explicit coordinator/brain side counts
- top blockers and candidate trace
- paper/live/real execution safety counts

## Safety

Side is never guessed. Missing, weak, stale, ambiguous, or non-deterministic evidence remains blocked. Recovered side only reduces the `MISSING_SIDE` blocker where lineage is trusted; remaining blockers such as `RISK_NOT_APPROVED`, `EXIT_NOT_READY`, and `THESIS_NOT_COMPLETE` remain intact.
