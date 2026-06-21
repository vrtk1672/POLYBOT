# POLYBOT V2 Neural Mesh Part 4A: Mesh Dashboard Truth

## 1. Purpose

Part 4A adds one unified read-only dashboard endpoint:

- `GET /dashboard/api/v2/mesh`

The endpoint gives POLYBOT one consolidated Neural Mesh truth surface across runtime, sources, neurons, signals, lineage, impact graph, brain outputs, coordinator decisions, thesis profiles, and existing operator dashboard surfaces where present.

This phase is observability only. It does not create orders, order intents, positions, AI calls, paper trades, shadow trades, or live trades.

## 2. Why Mesh Dashboard Is System Consciousness

Dashboard is not decoration in POLYBOT. A dashboard endpoint with `mock_data=false` must report what the system actually knows from DB/runtime truth.

The Mesh Dashboard answers whether the system is alive, whether signals are flowing, which layers are silent or degraded, and what blocks Paper readiness. Empty stores are reported as empty. Missing optional or future layers are reported honestly. Nothing is invented to make the system look active.

## 3. Aggregated Layers

The endpoint aggregates these implemented layers:

- Runtime health and persisted runtime mode.
- Source status from the persisted `source_status` table.
- Neuron Registry and health summary.
- Signal Store summary.
- Signal lineage summary.
- Impact Graph summary.
- Brain Output summary.
- Brain Coordinator summary.
- Position Thesis summary.
- Existing operator dashboard opportunity, no-trade, exit, AI, and risk surfaces when available.

## 4. Response Contract

Top-level fields:

- `status`
- `mock_data`
- `updated_at`
- `runtime`
- `mesh_summary`
- `layers`
- `flow`
- `alerts`
- `readiness`

`mock_data` is always `false`.

`runtime` includes:

- `current_mode`
- `runtime_health`
- `healthy`
- `live_enabled`
- `env_mode`
- `persisted_mode`
- `kill_switch_env`
- `kill_switch_persisted`
- mode and kill-switch mismatch flags

`mesh_summary` includes:

- active source count
- active neuron count
- signals per minute
- signals in the last 24 hours
- unlinked signal count
- brain outputs in the last 24 hours
- coordinator decisions in the last 24 hours
- impact link count
- thesis profile count
- coordinator `execution_allowed_count`

`layers` includes:

- `sources`
- `neurons`
- `signals`
- `lineage`
- `impact_graph`
- `brain_outputs`
- `coordinator`
- `thesis`
- `opportunities`
- `no_trade`
- `exit`
- `ai`
- `risk`

`flow` includes recent and grouped truth:

- signals by neuron
- signals by market
- latest signals
- unlinked signals
- latest brain outputs
- recent conflicts
- recent coordinator decisions
- latest impact links
- latest thesis profiles

## 5. Status Calculation

Layer status is passed through when the underlying service already reports one. If a layer has errors, it reports `ERROR`. If it has no active rows and no errors, it can report `EMPTY`. Optional operator surfaces report `OK`, `EMPTY`, `DEGRADED`, `ERROR`, or `DISABLED` based on existing payload truth.

Overall status:

- `OK`: no alerts or mesh errors.
- `DEGRADED`: implemented layer warnings, degraded layers, unlinked signals, or other non-fatal mesh blockers.
- `ERROR`: the mesh endpoint cannot read critical truth or a critical layer returns an error.

Current live runtime verification returned `DEGRADED`, which is truthful because the neuron layer is degraded and the impact graph reports unlinked signals.

## 6. Readiness Rules

`data_ready` can be true when:

- runtime is healthy
- source status is reachable or empty/degraded without crashing
- signal summary is readable

`mesh_ready` can be true when:

- data is ready
- Neuron Registry exists
- coordinator truth exists
- `execution_allowed_count` is zero
- the mesh endpoint has no critical errors

`paper_ready` is conservative and remains `false` in this phase. Part 4A does not certify Paper trading.

Current blockers surfaced by the endpoint include:

- `orderbook_snapshots_zero`
- `production_brain_outputs_24h_zero`
- `unlinked_signals_present`
- `env_mode_differs_from_persisted_mode`
- `env_kill_switch_differs_from_persisted_kill_switch`
- `paper_full_evidence_loop_not_proven_in_part4a`

## 7. Missing/Partial Layer Handling

Missing optional or future layers must not crash `/dashboard/api/v2/mesh`. They are represented as empty, missing, degraded, disabled, or error states depending on what the underlying repository/service can prove.

The endpoint does not invent opportunity, no-trade, exit, AI, or risk data. It reads existing operator dashboard surfaces and marks them honestly.

## 8. Safety Rules

The Mesh Dashboard is read-only.

It must not:

- create orders
- create order intents
- open or close positions
- cancel orders
- sign requests
- call AI models
- enable Paper, Shadow, or Live trading
- mutate runtime mode
- mutate State Governor or Risk Governor state
- expose secrets
- present mock data as real

Readiness flags are informational only. They do not approve trading and do not route to execution.

## 9. API Route

`GET /dashboard/api/v2/mesh`

Query parameters:

- `limit`: optional, default `20`, minimum `1`, maximum `100`

The route is implemented in the existing API router and backed by `MeshDashboardService`.

## 10. Dashboard Fields

The endpoint exposes:

- runtime mode and health
- source counts and errors
- neuron counts and signal flow
- signal freshness, stale, and unprocessed counts
- lineage bound/unbound metrics
- impact graph link counts
- brain output and conflict summaries
- coordinator decisions and execution safety count
- thesis profile readiness counts
- optional opportunity/no-trade/exit/AI/risk surfaces
- alerts
- readiness flags and blockers

## 11. Examples

Current live response summary:

```json
{
  "status": "DEGRADED",
  "mock_data": false,
  "mesh_summary": {
    "active_sources": 6,
    "active_neurons": 4,
    "signals_per_minute": 3.8,
    "signals_24h": 95,
    "unlinked_signals": 131,
    "brain_outputs_24h": 0,
    "coordinator_decisions_24h": 0,
    "impact_links_total": 0,
    "thesis_profiles_total": 0,
    "execution_allowed_count": 0
  },
  "readiness": {
    "data_ready": true,
    "mesh_ready": true,
    "paper_ready": false
  }
}
```

This is a dashboard truth state, not a trading approval.

## 12. What Is Explicitly Not Included

Part 4A does not include:

- Paper trading
- Shadow Live
- Small Live
- order intents
- orders
- position mutation
- AI model calls
- Opportunity Cortex implementation
- Risk decisions
- Exit decisions
- No-Trade engine implementation
- new background schedulers
- DB migrations
- fake dashboard data

## 13. Next Phase Recommendation

Recommended next phase:

V2 Neural Mesh Activation Part 4B: Mesh Flow Remediation / Paper Readiness Evidence Loop.

Suggested focus:

- reduce unlinked signals through non-executing graph links
- produce controlled non-executing brain outputs from existing signals
- keep coordinator decisions non-executing with `execution_allowed=false`
- maintain thesis validation truth
- build a paper-readiness evidence checklist without enabling Paper execution
