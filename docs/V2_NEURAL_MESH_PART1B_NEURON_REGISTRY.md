# POLYBOT V2 Neural Mesh Part 1B Neuron Registry

## 1. Purpose

V2 Neural Mesh Part 1B creates the living map of POLYBOT neurons. It records which neurons exist, whether they are enabled, what they are expected to emit, and how healthy they are based on Signal Store activity and source status truth.

This phase is observational only. It does not coordinate brains, interpret opportunities, approve risk, or touch execution.

## 2. Neuron Registry Philosophy

The registry is the mesh inventory. It answers:

- Which neurons are known to POLYBOT.
- Which neurons are active, partial, disabled, missing, degraded, stale, or in error.
- Which neurons are expected to emit Signals.
- Which source or component owns each neuron.
- When each neuron last emitted a Signal.
- Which expected neurons are silent.

## 3. Neurons Do Not Decide

Neurons produce neutral structured information. The registry reports health and availability only. It does not interpret Signal meaning, rank opportunities, route strategies, approve trades, or block trades.

Brains interpret later. Governors approve or block later. Execution acts only after approved decisions in later phases.

## 4. Registry Fields

Canonical registry fields:

| Field | Purpose |
| --- | --- |
| `neuron_name` | Stable lowercase neuron identifier. |
| `display_name` | Human-readable neuron name. |
| `category` | Broad group, such as `market`, `intelligence`, `risk`, `capital`, `execution`, `exit`, `ai`, `memory`, or `system`. |
| `description` | Plain-language purpose. |
| `expected_signal_types` | Signal event types this neuron is expected to emit. |
| `producer_source` | Producer class/source, such as `source_status`, `rules_resolution`, `future_connector`, `manual`, or `unknown`. |
| `is_required_for_paper` | Whether PAPER readiness depends on this neuron. |
| `is_required_for_live` | Whether live readiness depends on this neuron. |
| `default_status` | Status used before current health is known. |
| `enabled` | Whether this neuron is currently enabled. |
| `owner_component` | Source or component that owns the neuron. |
| `created_at` | Creation timestamp. |
| `updated_at` | Update timestamp. |

## 5. Health Fields

Canonical health fields:

| Field | Purpose |
| --- | --- |
| `neuron_name` | Registry key. |
| `runtime_status` | Current runtime status. |
| `health_status` | Current mesh health status. |
| `last_signal_at` | Latest Signal timestamp. |
| `last_success_at` | Latest successful signal/source observation. |
| `last_error_at` | Latest error timestamp, if known. |
| `last_error` | Latest error note, if known. |
| `stale_after_seconds` | Staleness threshold. |
| `is_stale` | Whether last Signal is stale. |
| `expected_to_emit` | Whether this neuron should emit Signals now. |
| `enabled` | Registry enabled flag copied into health. |
| `source_status_name` | Backing source status name, when known. |
| `signal_count_1h` | Signal count in the last hour. |
| `signal_count_24h` | Signal count in the last 24 hours. |
| `error_count_24h` | Recent error count from latest signal/source status. |
| `updated_at` | Health refresh timestamp. |

## 6. Status Definitions

- `ACTIVE`: Enabled and recently emitted active Signals.
- `PARTIAL`: Some source/component support exists, but the neuron is not fully active.
- `DISABLED`: Registry marks the neuron disabled.
- `MISSING`: Expected neuron has no current source/signals and is not intentionally disabled.
- `DEGRADED`: Latest signal or backing source is degraded/missing.
- `STALE`: Latest signal exists but is older than the configured stale threshold.
- `ERROR`: Latest signal/source health has a hard error.

## 7. Runtime Stats

Runtime stats are computed live from `neuron_signals` to avoid duplicate truth:

- `total_signals`
- `signals_1m`
- `signals_5m`
- `signals_1h`
- `signals_24h`
- `last_signal_at`
- `active_market_count`
- `stale_signal_count`
- `unprocessed_signal_count`
- `latest_status`
- `updated_at`

## 8. DB Tables

Migration:

`0060_v2_neural_mesh_neuron_registry.sql`

Tables:

| Table | Purpose |
| --- | --- |
| `neuron_registry` | Canonical inventory of POLYBOT neurons. |
| `neuron_health` | Current on-demand health/status records for registered neurons. |

No `neuron_runtime_stats` table was created. Stats are derived from `neuron_signals` on demand because the Signal Store is the canonical source of signal counts and timestamps.

## 9. Repository And Service

Repository:

`app/repositories/neuron_registry_repository.py`

Service:

`app/services/neuron_registry.py`

Implemented capabilities:

- `ensure_default_neurons`
- `list_neurons`
- `get_neuron`
- `refresh_neuron_health_from_signals`
- `get_neuron_mesh_summary`
- `get_neuron_stats`
- signal-based stats aggregation
- source-status-aware health calculation

## 10. API Routes

Routes:

- `GET /neurons`
- `GET /neurons/{neuron_name}`
- `GET /dashboard/api/v2/neurons`

All responses are read-only and return `mock_data=false`.

## 11. Dashboard Fields

Dashboard Neuron Mesh Health includes:

- `total_neurons`
- `active_neurons`
- `partial_neurons`
- `disabled_neurons`
- `missing_neurons`
- `degraded_neurons`
- `stale_neurons`
- `signals_per_neuron`
- `last_signal_by_neuron`
- `neuron_errors`
- `silent_expected_neurons`
- full neuron registry/health/stats list

Dashboard overview also includes compact neuron summary fields.

## 12. How Status Is Calculated

Status calculation is intentionally simple:

- Disabled registry rows report `DISABLED`.
- Latest signal/source hard error reports `ERROR`.
- Degraded/missing source status or degraded latest signal reports `DEGRADED`.
- Latest signal older than `stale_after_seconds` reports `STALE`.
- Recent active signal reports `ACTIVE`.
- Active backing source without current signal reports `PARTIAL`.
- Expected-to-emit neuron with no source/signals reports its default status, usually `PARTIAL` or `MISSING`.

This does not interpret whether a signal helps or hurts a position.

## 13. Safety Rules

- Registry health does not imply trade approval.
- Registry health does not create orders.
- Registry health does not cancel orders.
- Registry health does not sign requests.
- Registry health does not use private keys.
- Dashboard must show real DB/runtime truth only.
- Missing/stale neurons are allowed and must not crash the API.
- KILL/runtime state behavior is not changed in this phase.

## 14. Explicitly Not Included

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
- Any order/cancel/sign/live mutation path

## 15. Next Phase Recommendation

Recommended next phase: V2 Neural Mesh Activation Part 1C, limited to producer registration hooks and explicit producer-to-registry metadata wiring.

Do not implement Brain Coordinator until registry health and producer ownership are stable.
