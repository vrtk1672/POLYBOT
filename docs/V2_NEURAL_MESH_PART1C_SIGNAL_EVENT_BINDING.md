# POLYBOT V2 Neural Mesh Part 1C Signal Event Binding

## 1. Purpose

V2 Neural Mesh Part 1C makes Signals traceable. A Signal can now point back to its producer, source, optional event, market, correlation ID, and raw payload reference without duplicating large raw payloads.

This is observability and memory infrastructure only. It does not interpret Signals or create decisions.

## 2. Why Lineage Matters

POLYBOT runs continuously. When a Signal appears in the Signal Store, operators and later brain phases need to know where it came from and whether the chain of custody is intact.

Lineage answers:

- Which neuron produced the Signal.
- Which adapter/service produced it.
- Which source or source-status row caused it.
- Which market it relates to, if known.
- Which event-log row or external event it maps to, if known.
- Which correlation ID ties it to surrounding work.
- Where the raw payload lives or how it can be referenced.

## 3. Definitions

Signal:

Neutral structured information emitted by a neuron.

Producer:

The service, adapter, or component that created the Signal.

Source:

The internal or external source of truth behind the fact, such as source status or rules/resolution truth.

Event:

An event-log row or external event that caused or corresponds to the Signal.

Lineage:

The trace from Signal back to producer, source, event, market, correlation ID, and raw reference.

## 4. DB Schema

Migration:

`0061_v2_neural_mesh_signal_event_binding.sql`

Tables:

| Table | Purpose |
| --- | --- |
| `neuron_producers` | Registry of known Signal producers. |
| `neuron_signal_bindings` | One binding row per Signal for lineage and traceability. |

`neuron_signal_bindings` columns include:

- `signal_id`
- `neuron_name`
- `producer_name`
- `producer_component`
- `producer_version`
- `source_name`
- `source_status_id`
- `event_log_id`
- `source_event_id`
- `market_id`
- `correlation_id`
- `raw_payload_ref`
- `generated_from`
- `lineage_json`
- `created_at`

Seeded producers:

- `source_status_adapter`
- `clob_source_status_adapter`
- `rules_resolution_adapter`
- `future_news_adapter`
- `future_social_adapter`
- `future_whale_adapter`

## 5. Repository And Service Behavior

Repository:

`app/repositories/signal_lineage_repository.py`

Service:

`app/services/signal_lineage.py`

Implemented behavior:

- Attach a binding to a Signal.
- Create a Signal with lineage in one transaction.
- Get lineage by `signal_id`.
- Query by `correlation_id`.
- Query by source.
- Query by producer.
- List unbound Signals.
- Summarize binding health.

## 6. API Routes

Added:

- `GET /signals/{signal_id}/lineage`
- `GET /signals/correlation/{correlation_id}`
- `GET /signals/source/{source_name}`
- `GET /signals/producer/{producer_name}`
- `GET /dashboard/api/v2/signal-lineage`

All are read-only and return `mock_data=false`.

## 7. Dashboard Fields

Signal lineage dashboard summary includes:

- `total_signals_24h`
- `bound_signals_24h`
- `unbound_signals_24h`
- `bound_pct_24h`
- `signals_by_producer`
- `signals_by_source`
- `signals_without_correlation_id`
- `signals_without_raw_payload_ref`
- `latest_unbound_signals`

The Signal dashboard and overview also include compact lineage health.

## 8. Adapter Changes

Source status Signals now carry lineage:

- `producer_name=source_status_adapter` or `clob_source_status_adapter`
- `generated_from=source_status`
- `source_name`
- `source_status_id`, when the source row exists
- `correlation_id`
- `raw_payload_ref`

Rules/resolution Signals now carry lineage:

- `producer_name=rules_resolution_adapter`
- `generated_from=rules_resolution`
- `source_name=rules_resolution_truth`
- `market_id`
- `source_event_id=rules_analysis_id`, when available
- `correlation_id`
- `raw_payload_ref`

## 9. Correlation ID Behavior

When an existing correlation ID is available, it is preserved. If source/rules data does not provide one, the adapter generates a `corr_*` ID using the existing event correlation helper and marks that in lineage metadata.

Generated correlation IDs are observability IDs only. They do not imply causality beyond the local Signal creation path.

## 10. Raw Payload Reference Behavior

This phase stores references, not large raw payloads.

Examples:

- `source_status:polymarket_gamma`
- `source_status:polymarket_clob_orderbook`
- `rules_analysis:<rules_analysis_id>`

The raw payload policy is `reference_only`.

## 11. Safety Rules

- Lineage is observational only.
- Lineage does not approve trades.
- Lineage does not create, cancel, or sign orders.
- Lineage does not use private keys.
- Lineage does not store secrets.
- Missing bindings are allowed and are reported truthfully.
- Dashboard must show real DB/runtime truth only.
- Runtime kill state is not changed in this phase.

## 12. Explicitly Not Included

- Brain Coordinator
- Brain Output Contract
- Impact Graph
- Position Thesis
- Opportunity Cortex changes
- Risk decisions
- Exit decisions
- News/Social/Whale full connectors
- AI Model Router
- Paper/Shadow/Small Live
- Any live mutation path

## 13. Next Phase Recommendation

Recommended next phase: V2 Neural Mesh Activation Part 1D, focused on event-to-signal replay/read models or producer coverage hardening.

Do not implement Brain Coordinator until Signal lineage coverage is stable and older unbound Signals are either accepted as legacy or backfilled by an explicit audit task.
