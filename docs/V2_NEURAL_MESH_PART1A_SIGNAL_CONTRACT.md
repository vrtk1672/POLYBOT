# POLYBOT V2 Neural Mesh Part 1A Signal Contract

## 1. Purpose

V2 Neural Mesh Part 1A creates the first shared language for POLYBOT neurons: a neutral Signal contract, a Postgres Signal Store, basic read APIs, dashboard truth, and safe adapters from existing source/rules status.

This phase does not create trade decisions. It gives future neurons a common way to say what happened, where it came from, how fresh it is, and how reliable it appears.

## 2. Signal Philosophy

Signals are structured observations. They are not instructions, approvals, rejections, orders, or position advice.

Valid signal language includes source, market/entity context, raw neutral direction, confidence, strength, freshness, reliability, evidence, and status.

Invalid signal language includes buy, sell, enter, exit, approved, rejected, order identity, or any field that turns a neuron observation into an execution decision.

## 3. Neurons Do Not Decide

Neurons produce neutral information. Brains interpret signals later. Governors approve or block later. Execution acts only after approved decisions in later phases.

Part 1A intentionally does not implement Brain Coordinator, Brain Output Contract, Impact Graph, Position Thesis, Opportunity Cortex, Risk decisions, Exit decisions, or live execution.

## 4. Signal Contract Fields

Canonical API field names:

| Field | Purpose |
| --- | --- |
| `signal_id` | Stable public signal identifier. |
| `neuron` | Producing neuron, such as `market`, `orderbook`, `rules`, `news`, `ai`, or `unknown`. |
| `event_type` | Neutral event label, such as `source_status_observed`. |
| `source_name` | Optional source or subsystem name. |
| `market_id` | Optional related market. Signals do not require a market. |
| `correlation_id` | Optional cross-system correlation key. |
| `raw_direction` | Optional objective direction, such as `neutral`, `mixed`, `yes_up`, or `no_down`. |
| `strength` | Optional bounded numeric value from `0` to `1`. |
| `confidence` | Optional bounded numeric value from `0` to `1`. |
| `source_reliability` | Optional bounded numeric value from `0` to `1`. |
| `freshness_seconds` | Optional observed freshness. |
| `status` | Signal status. |
| `evidence` | JSON evidence with decision/order keys rejected. |
| `raw_payload_ref` | Optional pointer to existing payload truth. |
| `entity_count` | Optional attached entity count. |
| `evidence_count` | Optional attached evidence chunk count. |
| `processed_by_brain` | Future-readiness flag; Part 1A does not process brain output. |
| `consumed_at` | Future consumption timestamp. |
| `ttl_seconds` | Optional time-to-live. |
| `expires_at` | Optional expiration timestamp. |
| `stale_after_seconds` | Optional staleness threshold. |
| `created_at` | Creation timestamp. |
| `updated_at` | Update timestamp. |

## 5. Status And Enums

Signal statuses:

`ACTIVE`, `PARTIAL`, `DEGRADED`, `STALE`, `DISABLED`, `MISSING`, `ERROR`

Known neurons:

`market`, `orderbook`, `liquidity`, `rules`, `resolution`, `news`, `social`, `whale`, `time`, `fees`, `ai`, `risk`, `capital`, `position`, `exit`, `unknown`

Raw directions:

`positive`, `negative`, `neutral`, `mixed`, `unknown`, `yes_up`, `yes_down`, `no_up`, `no_down`, `entity_positive`, `entity_negative`

## 6. DB Tables

Migration:

`0059_v2_neural_mesh_signal_contract.sql`

Tables:

| Table | Purpose |
| --- | --- |
| `neuron_signals` | Canonical neutral Signal Store. |
| `neuron_signal_entities` | Optional entities attached to a signal. |
| `neuron_signal_evidence` | Optional structured evidence chunks/references. |

`neuron_signals` includes indexes for created time, neuron, market, status, correlation ID, processed flag, and source name. It also includes database checks for bounded numeric fields, allowed status/direction values, and forbidden evidence keys.

## 7. Repository And Service

Repository:

`app/repositories/neuron_signal_repository.py`

Service:

`app/services/neuron_signals.py`

Implemented capabilities:

- `create_signal`
- `list_recent_signals`
- `list_market_signals`
- `list_neuron_signals`
- `get_signal_summary`
- `mark_processed`
- source status to signal adapter
- rules status to signal adapter

## 8. API Routes

Routes:

- `GET /signals/recent`
- `GET /signals/market/{market_id}`
- `GET /signals/neuron/{neuron_name}`

All responses return DB truth only and include `mock_data=false`. Empty stores return `status=OK`, `count=0`, and an empty `signals` list.

## 9. Dashboard Fields

Dashboard endpoint:

- `GET /dashboard/api/v2/signals`

Overview also includes compact signal summary fields.

Dashboard truth fields:

- `signals_per_minute`
- `total_signals_24h`
- `signals_by_neuron`
- `latest_signals`
- `stale_signals`
- `unprocessed_signals`

No mock signal data is generated. Zero is a valid truth state.

## 10. Initial Adapter Behavior

Source status adapter:

Existing source status checks can emit `source_status_observed` signals. Source types map to neutral neurons such as `market`, `orderbook`, `ai`, `news`, `social`, or `whale`.

Rules adapter:

Existing dashboard rules/resolution truth can emit `rules_resolution_status_observed` signals. The adapter records neutral resolution/source state, confidence, penalty-like strength, and evidence. It does not emit trading recommendations.

Orderbook adapter:

Part 1A does not start orderbook snapshotting or polling. It can represent orderbook source status when existing source status data is present.

## 11. Safety Rules

- Signals are not trade decisions.
- Signal creation does not approve trades.
- Signal creation does not create, cancel, or sign orders.
- Missing data is allowed.
- No private keys are required.
- No secrets are stored in signal evidence.
- Dashboard must show DB truth with `mock_data=false`.
- Live trading remains disabled.
- KILL and runtime governor behavior remain untouched.

## 12. Examples

Source status signal:

```json
{
  "neuron": "orderbook",
  "event_type": "source_status_observed",
  "source_name": "polymarket_clob_orderbook",
  "raw_direction": "neutral",
  "status": "ACTIVE",
  "confidence": 1.0
}
```

Rules signal:

```json
{
  "neuron": "rules",
  "event_type": "rules_resolution_status_observed",
  "market_id": "example-market",
  "raw_direction": "neutral",
  "status": "DEGRADED",
  "confidence": 0.5
}
```

## 13. Explicitly Not Included

- Brain Coordinator
- Brain Output Contract
- Impact Graph
- Position Thesis
- Opportunity Cortex
- Strategy routing
- Capital allocation
- Risk decisions
- Exit decisions
- News/Social/Whale full connectors
- Paper/Shadow/Live trading phases
- Order placement, cancellation, signing, or live mutation

## 14. Next Phase Recommendation

Recommended next phase: V2 Neural Mesh Activation Part 1B.

Scope should be limited to a Neuron Registry and explicit signal producer registration/health metadata, while preserving the rule that neurons emit neutral observations only and brains do not yet coordinate decisions.
