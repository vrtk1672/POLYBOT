# V2 Neural Mesh Part 4C-D: Lineage Coverage Hardening

## Purpose

Lineage Coverage Hardening makes Signal origin truth explicit. It analyzes every Signal and records whether POLYBOT can explain who created it, where it came from, when it was created, why it exists, and whether the lineage is trustworthy enough for downstream brain or future Paper-readiness evidence.

This is non-executing mesh hardening. It does not create trades, orders, order intents, live approvals, or AI interpretations.

## Why Lineage Matters

Signals are neutral structured information. A Signal that cannot identify its producer, source, correlation id, raw payload reference, or generated-from path is not strong evidence. Missing lineage blocks brain confidence and future Paper readiness because the system cannot audit the Signal back to a producer, event, or payload.

## Contract

The canonical latest analysis lives in `signal_lineage_coverage_analysis`, one row per `signal_id`.

Core fields:
- `lineage_status`
- `lineage_trust_score`
- `is_bound`
- `is_unbound`
- `primary_unbound_reason`
- `unbound_reasons_json`
- `missing_lineage_fields_json`
- `producer`
- `source`
- `correlation_id`
- `raw_payload_ref`
- `generated_from`
- `generated_by`
- `generated_at`
- `signal_created_at`
- provenance booleans for dry-run, runtime, manual, and adapter origin
- traceability booleans for event, payload, and producer
- `can_feed_brain_by_lineage`
- `can_feed_paper_by_lineage`

Run summaries live in `signal_lineage_coverage_runs`.

## Status Definitions

- `COMPLETE`: all required lineage fields exist.
- `RUNTIME_VERIFIED`: complete lineage with runtime provenance and traceable payload/producer.
- `PARTIAL`: producer/source lineage exists, but important fields are missing.
- `UNBOUND`: lineage is too incomplete to trust.
- `DRY_RUN_ONLY`: lineage is from dry-run provenance and cannot count as production Paper evidence.
- `MANUAL`: manual/dashboard generated lineage.
- `ADAPTER`: adapter-generated lineage with partial trust.
- `STALE_OR_UNKNOWN`: origin is not explainable.
- `ERROR`: analyzer failed and recorded the error.

## Unbound Reasons

The classifier records deterministic reasons:
- `MISSING_PRODUCER`
- `MISSING_SOURCE`
- `MISSING_CORRELATION_ID`
- `MISSING_RAW_PAYLOAD_REF`
- `MISSING_GENERATED_FROM`
- `MISSING_GENERATED_AT`
- `DRY_RUN_ONLY`
- `UNKNOWN_ORIGIN`
- `NO_EVENT_TRACE`
- `NO_PAYLOAD_TRACE`
- `NO_PRODUCER_TRACE`
- `ALREADY_BOUND`
- `UNKNOWN`

No missing field is fabricated.

## Trust Score

The score is deterministic and clamped from `0.0` to `1.0`.

Weights:
- producer present: `+0.20`
- source present: `+0.20`
- correlation id present: `+0.15`
- raw payload ref present: `+0.20`
- generated_from present: `+0.10`
- generated_at or created_at present: `+0.05`
- runtime provenance: `+0.10`
- dry-run-only penalty: `-0.25`
- unknown origin penalty: `-0.30`

Dry-run-only lineage cannot feed Paper evidence.

## Provenance

The analyzer classifies:
- dry-run generated
- runtime generated
- manual generated
- adapter generated

Dry-run lineage remains useful for auditability, but it is blocked from production Paper evidence.

## API Routes

- `GET /signals/lineage-coverage/recent`
- `GET /signals/{signal_id}/lineage-coverage`
- `POST /signals/lineage-coverage/analyze/recent`
- `POST /signals/{signal_id}/lineage-coverage/analyze`
- `GET /dashboard/api/v2/lineage-coverage`

All responses use `mock_data=false`.

## Dashboard Fields

The dashboard summary includes:
- total signals
- total analyzed
- bound signals
- unbound signals
- complete lineage
- partial lineage
- dry-run-only signals
- runtime-verified signals
- unbound by reason
- missing lineage fields
- producer coverage
- source coverage
- raw payload coverage
- correlation coverage
- average lineage trust score
- last analysis time
- `paper_ready=false`

The mesh dashboard includes `layers.lineage_coverage` and `flow.lineage_coverage`.

## Safety Rules

- No Paper.
- No Live.
- No orders.
- No order intents.
- No signing.
- No private key use.
- No AI calls.
- No fabricated lineage.
- `can_feed_paper_by_lineage` is informational only.
- Global `paper_ready` remains false.
- Missing lineage blocks readiness.

## Example

```json
{
  "signal_id": "sig_123",
  "lineage_status": "PARTIAL",
  "lineage_trust_score": 0.55,
  "primary_unbound_reason": "MISSING_RAW_PAYLOAD_REF",
  "missing_lineage_fields": ["MISSING_RAW_PAYLOAD_REF"],
  "producer": "rules_resolution_adapter",
  "source": "rules_resolution_truth",
  "can_feed_brain_by_lineage": true,
  "can_feed_paper_by_lineage": false
}
```

## Not Included

This phase does not implement Market Technical Truth, News/Social/Whale connectors, AI entity extraction, Risk Core, Exit Foundation, Opportunity Cortex, Strategy Router, Paper trading, Shadow Live, Small Live, order intents, or live execution.

## Next Phase Recommendation

Proceed to the next Mesh Hardening slice: **Producer/Adapter Lineage Backfill + Signal Creation Hooks**, focused on making future runtime Signals attach complete lineage at creation time without fabricating missing history.
