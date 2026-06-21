# POLYBOT V2 Neural Mesh Part 4C-A: Signal Quality Contract

## 1. Purpose

Part 4C-A defines how POLYBOT evaluates the readiness of each neutral Signal. It answers whether a Signal is usable, traceable, linked, fresh, evidence-backed, and safe to feed into future Brain Outputs or Paper-readiness evidence.

This phase is observability and quality gating only. It does not enable Paper, Live, AI, external connectors, Opportunity Cortex, Risk/No-Trade Core, Exit Foundation, or execution.

## 2. Why Signal Quality Matters

The Post-Neural-Mesh Activation Audit found that the mesh exists but is not Paper-ready. The main blocker is not missing contracts; it is quality and readiness:

- signals exist but many are unprocessed
- many signals are unlinked or unbound
- lineage coverage is incomplete
- brain/coordinator layers are dry-run-only
- Paper readiness must remain blocked until mesh inputs are quality-gated

Signal Quality is the first Mesh Hardening slice. It lets POLYBOT see which Signals are useful and why others are blocked.

## 3. Signal Quality Contract

Every evaluated Signal receives a latest quality record in `signal_quality_evaluations`.

The evaluation is informational. It does not make decisions, approve trades, open positions, create order intents, or mark global Paper readiness.

Core questions:

- Does the Signal have a market?
- Does it have a source?
- Does it have lineage?
- Does it have correlation and raw payload references?
- Does it have confidence, strength, freshness, and evidence?
- Is it linked to market or position context?
- Has it been used by Brain Outputs or Coordinator Decisions?
- Is it dry-run-generated or runtime-generated?
- Is it stale?
- Can it feed a Brain?
- Can it contribute to future Paper evidence?

## 4. Field Definitions

Boolean fields:

- `has_market_id`: Signal has `market_id`.
- `has_source`: Signal or lineage has a source name.
- `has_lineage`: Signal has a row in `neuron_signal_bindings`.
- `has_correlation_id`: Signal or lineage has a correlation ID.
- `has_raw_payload_ref`: Signal or lineage has a raw payload reference.
- `has_confidence`: Signal has a confidence value.
- `has_strength`: Signal has a strength value.
- `has_freshness`: Signal has freshness, stale, or expiry metadata.
- `has_evidence`: Signal has evidence JSON, evidence count, or evidence rows.
- `linked_to_market`: Signal has a `signal_market_links` row.
- `linked_to_position`: Signal has a `signal_position_links` row.
- `used_by_brain_output`: Signal appears in `brain_output_dependencies`.
- `used_by_coordinator`: Signal dependency reaches coordinator inputs through a Brain Output.
- `is_dry_run_generated`: Signal provenance indicates dry-run generation.
- `is_runtime_generated`: Signal has runtime-created truth and is not dry-run-generated.
- `is_stale`: Signal status, expiry, or stale-after window indicates staleness.

Scoring/readiness fields:

- `quality_score`: 0.0 to 1.0.
- `quality_status`: quality classification.
- `missing_fields`: JSON list of blockers or missing readiness fields.
- `readiness_reason`: human-readable explanation.
- `can_feed_brain`: Signal can inform advisory Brain Outputs.
- `can_feed_paper`: Signal is strict enough for future Paper-readiness evidence.
- `evaluated_at`: latest evaluation time.

## 5. Scoring Rules

Base score starts at 0.0.

Add:

- `has_source`: +0.10
- `has_lineage`: +0.12
- `has_correlation_id`: +0.08
- `has_raw_payload_ref`: +0.08
- `has_confidence`: +0.08
- `has_strength`: +0.08
- `has_freshness`: +0.08
- `has_evidence`: +0.10
- `has_market_id`: +0.10
- `linked_to_market`: +0.12
- `used_by_brain_output`: +0.08
- `used_by_coordinator`: +0.08

Penalties and caps:

- stale signal: -0.20
- dry-run-only signal: max 0.70
- no lineage: max 0.60
- no market link: max 0.65
- no evidence: max 0.75
- no source: max 0.55

Scores are clamped between 0.0 and 1.0. Conservative scoring is intentional.

## 6. Quality Statuses

Allowed statuses:

- `GOOD`: strong quality score and no critical quality blocker.
- `PARTIAL`: usable for Brain Outputs but not Paper evidence.
- `WEAK`: present but low quality.
- `STALE`: signal is stale or expired.
- `UNLINKED`: signal has market context but no market link.
- `UNBOUND`: signal has no lineage binding.
- `DRY_RUN_ONLY`: signal provenance is dry-run-only.
- `BLOCKED`: quality is too low for brain consumption.
- `ERROR`: source Signal status is ERROR.

## 7. can_feed_brain Rules

`can_feed_brain=true` when:

- quality score is at least 0.50
- Signal has lineage or source
- Signal is not stale

This means the Signal may be useful for advisory interpretation. It does not mean the Signal creates a decision or approval.

## 8. can_feed_paper Rules

`can_feed_paper=true` only when:

- score is at least 0.80
- `has_market_id=true`
- `linked_to_market=true`
- market link is not dry-run-created
- `has_lineage=true`
- `has_source=true`
- `has_evidence=true`
- `is_stale=false`
- `is_runtime_generated=true`
- `is_dry_run_generated=false`

The current production evaluation returned `can_feed_paper=0`.

## 9. Why can_feed_paper Does Not Mean Global paper_ready

`can_feed_paper` is a per-Signal informational flag. Global Paper readiness also requires runtime safety alignment, orderbook coverage, Risk + No-Trade Core, Exit Foundation, thesis coverage, coordinator evidence, Paper Evidence Loop certification, and execution safety.

This phase keeps global `paper_ready=false`.

## 10. DB Schema

Migration:

- `0068_v2_neural_mesh_signal_quality_contract.sql`

Table:

- `signal_quality_evaluations`

The table stores one latest quality evaluation per `signal_id` with a unique constraint on `signal_id`.

Indexes:

- `signal_id`
- `quality_status`
- `quality_score`
- `can_feed_brain`
- `can_feed_paper`
- `evaluated_at`
- `is_dry_run_generated`
- `is_runtime_generated`
- `linked_to_market`
- `has_lineage`

## 11. Repository / Service Behavior

Repository:

- `app/repositories/signal_quality_repository.py`

Service:

- `app/services/signal_quality.py`

Capabilities:

- evaluate one Signal
- evaluate recent Signals
- evaluate unevaluated Signals
- upsert latest evaluation
- get one Signal quality record
- list recent quality records
- summarize quality distribution
- summarize missing fields
- list low-quality Signals

Evaluation reads existing truth from:

- `neuron_signals`
- `neuron_signal_bindings`
- `signal_market_links`
- `signal_position_links`
- `brain_output_dependencies`
- `coordinator_decision_inputs`
- `neuron_signal_evidence`

## 12. API Routes

Added:

- `GET /signals/quality/recent`
- `GET /signals/{signal_id}/quality`
- `POST /signals/quality/evaluate/recent`
- `POST /signals/{signal_id}/quality/evaluate`

Responses return `mock_data=false` and DB truth only.

## 13. Dashboard Fields

Added:

- `GET /dashboard/api/v2/signal-quality`

Dashboard fields:

- `total_evaluated`
- `avg_quality_score`
- `can_feed_brain`
- `can_feed_paper`
- `quality_by_status`
- `missing_fields_summary`
- `dry_run_generated`
- `runtime_generated`
- `low_quality_count`
- `low_quality_signals`
- `paper_blocking_reasons`

Mesh dashboard integration:

- `layers.signal_quality`
- `mesh_summary.signal_quality_avg`
- `mesh_summary.signals_can_feed_brain`
- `mesh_summary.signals_can_feed_paper`
- `flow.signal_quality`
- readiness blockers for zero quality evaluations and zero paper-feed Signals

## 14. Safety Rules

- No Paper enabled.
- No Live enabled.
- No runtime mode changes.
- No private keys used.
- No signed requests.
- No orders created.
- No cancels sent.
- No order intents created.
- `can_feed_paper` remains informational only.
- Global `paper_ready` remains false.
- Dashboard uses real DB/runtime truth only.

## 15. Examples

Partial Signal:

```json
{
  "signal_id": "signal_123",
  "quality_score": 0.62,
  "quality_status": "PARTIAL",
  "missing_fields": ["production_market_link", "position_link"],
  "can_feed_brain": true,
  "can_feed_paper": false
}
```

Blocked Signal:

```json
{
  "signal_id": "signal_456",
  "quality_score": 0.24,
  "quality_status": "BLOCKED",
  "missing_fields": ["source", "lineage", "evidence"],
  "can_feed_brain": false,
  "can_feed_paper": false
}
```

## 16. What Is Explicitly Not Included

- Signal Processing State
- full Mesh Hardening
- Brain Producer Adapters
- Market Technical Truth
- News/Social/Whale connectors
- AI calls
- Risk + No-Trade Core
- Opportunity Cortex
- Exit Foundation
- Paper trading
- Live trading
- order intents
- orders
- signing
- runtime mode mutation
- global Paper readiness

## 17. Next Phase Recommendation

Recommended next phase:

V2 Neural Mesh Part 4C-B: Signal Processing State + Quality Gate Enforcement.

Goal:
Track whether each Signal has been evaluated, linked, consumed, rejected, or blocked by quality gates, without producing orders or enabling Paper.
