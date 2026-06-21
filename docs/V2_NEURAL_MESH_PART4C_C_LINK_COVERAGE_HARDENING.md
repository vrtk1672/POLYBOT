# V2 Neural Mesh Part 4C-C: Link Coverage Hardening

## 1. Purpose

Part 4C-C adds Link Coverage Hardening: a deterministic analyzer that explains why Signals are linked or unlinked, whether they are linkable, and whether any market-link suggestion is strong enough for review.

This phase does not force-link Signals. Weak, stale, dry-run, or missing-evidence Signals remain unlinked with explicit reasons.

## 2. Why Link Coverage Matters

Signals without market or position context cannot become reliable intelligence. Link Coverage makes the missing context visible:

- Does the Signal already have a market link?
- Does it have `market_id`?
- Does it have entity/source/producer/raw payload evidence?
- Is it stale or dry-run-only?
- Is there a deterministic local matcher candidate?
- Is a suggestion safe, review-only, weak, or blocked?

## 3. Link Coverage Contract

Latest analysis is stored in `signal_link_coverage_analysis`, one row per `signal_id`.

Allowed `linkability_status` values:

- `LINKED`
- `LINKABLE`
- `NOT_LINKABLE`
- `NEEDS_MORE_EVIDENCE`
- `STALE`
- `DRY_RUN_ONLY`
- `ERROR`

Allowed `suggested_link_action` values:

- `NONE`
- `REVIEW_ONLY`
- `SAFE_TO_LINK_EXISTING_MARKET_ID`
- `BLOCKED_WEAK_EVIDENCE`
- `BLOCKED_DRY_RUN_ONLY`
- `BLOCKED_STALE`
- `BLOCKED_MISSING_MARKET`
- `BLOCKED_MISSING_ENTITY`
- `BLOCKED_MISSING_SOURCE`
- `BLOCKED_NO_MATCHER`

## 4. Unlinked Reason Classifier

Classifier reasons include:

- `MISSING_MARKET_ID`
- `MISSING_ENTITY`
- `MISSING_SOURCE`
- `MISSING_RULES_CONTEXT`
- `MISSING_PRODUCER`
- `MISSING_RAW_PAYLOAD_REF`
- `NO_MATCHER_AVAILABLE`
- `WEAK_MATCHER_EVIDENCE`
- `DRY_RUN_ONLY`
- `STALE_SIGNAL`
- `ALREADY_LINKED`
- `POSITION_LINK_MISSING`
- `UNKNOWN`

The classifier is conservative. Stale and dry-run-only states block production link application.

## 5. Suggested Market Links

Suggestions are stored separately in `signal_suggested_market_links`.

Suggested links are not actual `signal_market_links`.

Default analyzer behavior:

- create analysis rows
- optionally create suggestion rows
- do not mutate actual market links

Only explicit `apply_safe_links=true` can apply a link, and only when:

- Signal has explicit `market_id`
- market exists in local market truth
- Signal is not stale
- Signal is not dry-run-generated
- suggestion confidence is at least `0.95`

Runtime verification used `apply_safe_links=false`.

## 6. Local Evidence Only

Allowed evidence:

- `neuron_signals.market_id`
- `neuron_signal_entities`
- `event_entities`
- `entity_market_links`
- `signal_market_links`
- `signal_position_links`
- `neuron_signal_bindings`
- `signal_quality_evaluations`
- `signal_processing_states`
- local market truth tables

Not allowed:

- AI calls
- web calls
- fuzzy guessing without evidence
- fabricating market IDs
- treating dry-run links as production Paper evidence

## 7. DB Schema

Migration: `0070_v2_neural_mesh_link_coverage_hardening.sql`

Tables:

- `signal_link_coverage_analysis`
- `signal_suggested_market_links`
- `signal_link_coverage_runs`

## 8. Repository and Service Behavior

Repository:

- Reads Signal, lineage, quality, processing, entity, and link context.
- Checks local market existence.
- Finds entity-market candidates from local entity link tables.
- Upserts latest analysis.
- Upserts separate suggestion rows.
- Applies actual links only through strict safe-apply logic.

Service:

- Analyzes one Signal.
- Analyzes recent Signals.
- Returns link coverage summaries.
- Keeps `paper_ready=false`.
- Defaults to analysis-only behavior.

## 9. API Routes

New routes:

- `GET /signals/link-coverage/recent`
- `GET /signals/{signal_id}/link-coverage`
- `POST /signals/link-coverage/analyze/recent`
- `POST /signals/{signal_id}/link-coverage/analyze`
- `GET /dashboard/api/v2/link-coverage`

All real endpoints return `mock_data=false`.

## 10. Dashboard and Mesh Fields

Dashboard link coverage includes:

- `total_signals`
- `linked_signals`
- `unlinked_signals`
- `link_coverage_ratio`
- `linkable_signals`
- `non_linkable_signals`
- `needs_more_evidence`
- `stale_unlinked`
- `dry_run_only_unlinked`
- `unlinked_by_reason`
- `suggested_market_links_count`
- `safe_to_link_count`
- `applied_suggestions_count`
- `paper_ready=false`

Mesh now includes `layers.link_coverage` and `flow.link_coverage`.

## 11. Readiness Blockers

Mesh readiness can now surface:

- `SIGNAL_LINK_COVERAGE_LOW`
- `SIGNALS_UNLINKED_HIGH`
- `LINKABLE_SIGNALS_PENDING_REVIEW`
- `LINK_COVERAGE_ANALYSIS_MISSING`
- `LINK_SUGGESTIONS_WEAK_EVIDENCE`
- `DRY_RUN_LINKS_BLOCKED_FROM_PAPER`

These are dashboard blockers only. They do not execute anything.

## 12. Safety Rules

- No Paper enablement.
- No Live enablement.
- No orders.
- No order intents.
- No private keys.
- No signing.
- No AI calls.
- No forced links.
- No fake dashboard data.
- `paper_ready` remains false.
- Weak/dry-run/stale suggestions do not become production truth.

## 13. Example

```json
{
  "signal_id": "signal_123",
  "linkability_status": "STALE",
  "primary_unlinked_reason": "STALE_SIGNAL",
  "unlinked_reasons": ["STALE_SIGNAL", "POSITION_LINK_MISSING"],
  "suggested_link_action": "BLOCKED_STALE",
  "can_auto_link": false
}
```

## 14. What Is Explicitly Not Included

- Paper trading
- Live trading
- Market Technical Truth
- News/Social/Whale connectors
- AI matching
- Risk Core
- Exit Foundation
- Opportunity Cortex
- Strategy Router
- Runtime mode mismatch fix

## 15. Next Phase Recommendation

Next recommended phase: `V2 Neural Mesh Part 4C-D: Signal Freshness Recovery + Re-Evaluation Hooks`.

Goal: reduce stale Signal blockage by safely refreshing quality, processing, and link coverage for newly-created Signals and by making freshness/finality explicit without adding execution behavior.
