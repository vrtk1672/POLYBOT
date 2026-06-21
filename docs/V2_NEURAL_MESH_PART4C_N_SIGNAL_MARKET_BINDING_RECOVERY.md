# V2 Neural Mesh Part 4C-N: Signal / Market Binding Recovery

## Purpose

Signal / Market Binding Recovery connects Signals to local market truth only when deterministic evidence is strong enough. It improves market binding observability without forced links, fabricated market IDs, Paper enablement, order intents, orders, fills, positions, or live actions.

## Contract

The binding recovery service analyzes unlinked Signals and classifies each candidate into one of:

- `AUTO_LINKED`
- `REVIEW_ONLY`
- `BLOCKED_WEAK_EVIDENCE`
- `BLOCKED_STALE`
- `BLOCKED_DRY_RUN`
- `BLOCKED_MISSING_MARKET`
- `BLOCKED_AMBIGUOUS`
- `ERROR`

Auto-linking is allowed only for strong local evidence:

- explicit `market_id` that exists in `markets_v2`: confidence `0.95`
- `token_id` uniquely matching a local yes/no token: confidence `0.90`
- `condition_id` uniquely matching a local market: confidence `0.85`
- exact slug/reference match: confidence `0.80`

Weak, ambiguous, stale, dry-run-only, and missing-market evidence remains unlinked with a persisted reason. Medium/review-only evidence is separated from production `signal_market_links`.

## Persistence

Migration `0079_v2_neural_mesh_signal_market_binding_recovery.sql` extends `signal_market_links` with audit fields:

- `link_confidence`
- `link_reason`
- `link_evidence_json`
- `link_method`
- `linked_by`
- `is_auto_linked`
- `is_review_required`
- `is_runtime_link`
- `source_signal_id`

It also adds derived audit tables:

- `signal_market_binding_recovery_runs`
- `signal_market_binding_candidates`

These tables store derived analysis and recovery audit truth; they do not replace source Signal, market, or link truth.

## API

New route:

- `POST /signals/market-binding/recover`

New dashboard route:

- `GET /dashboard/api/v2/market-binding`

The mesh dashboard now includes:

- `layers.market_binding`
- `flow.market_binding`
- `readiness.market_binding_summary`

## Safety

This phase is non-executing. Binding recovery never creates orders, order intents, fills, positions, strategy routes, risk approvals, exit plans, or live actions. `paper_ready` remains false and stale/dry-run evidence is blocked from Paper evidence by default.

## Current Runtime Finding

Runtime verification found `147` Signals, `20` existing market links, and `8` source-runtime Signals. With strict defaults (`include_stale=false`, `include_dry_run=false`), no links were auto-applied because current unlinked candidates were stale or weak. Existing link coverage still reports `3` suggested market links, but those remain suggestions until freshness/evidence is safe.

## Next Phase

The next recommended phase is signal freshness and lineage/linking recovery around runtime Signals, or the next planned Paper-readiness foundation phase, while keeping Risk Core and Exit Foundation as hard blockers.
