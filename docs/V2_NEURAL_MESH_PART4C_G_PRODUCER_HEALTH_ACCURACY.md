# V2 Neural Mesh Part 4C-G: Producer Health Accuracy

## 1. Purpose

Part 4C-G strengthens the Neuron Registry from a static list into runtime truth.

The new Producer Health Accuracy surface answers:

- who is registered
- who is expected
- who actually produced Signals
- who is runtime-active
- who is dry-run-only
- who is silent
- who is missing
- who is degraded
- who is blocked from Paper evidence

This phase is observability only. It does not start producers, fix producers, enable Paper, create orders, create order intents, call AI, or change runtime mode.

## 2. Producer Health Contract

Each producer health row includes:

- `producer_name`
- `neuron_name`
- `registered`
- `expected`
- `observed`
- `signal_count`
- `runtime_signal_count`
- `dry_run_signal_count`
- `recent_signal_count`
- `stale_signal_count`
- `brain_output_count`
- `coordinator_decision_count`
- `lineage_complete_count`
- `lineage_unbound_count`
- `avg_quality_score`
- `health_status`
- `health_reason`
- `dry_run_only`
- `runtime_active`
- `silent_expected`
- `degraded`
- `missing`
- `can_feed_brain`
- `can_feed_paper`
- `evidence`
- `first_seen_at`
- `last_seen_at`
- `analyzed_at`

Allowed `health_status` values:

- `HEALTHY`
- `ACTIVE`
- `DEGRADED`
- `SILENT`
- `MISSING`
- `DRY_RUN_ONLY`
- `REGISTERED_ONLY`
- `UNKNOWN`
- `ERROR`

## 3. Neuron Runtime Truth

The dashboard returns a grouped `neuron_runtime_truth` object:

- `runtime_active`
- `dry_run_only`
- `silent_expected`
- `degraded`
- `missing`
- `unknown`

These groups are derived from DB/runtime evidence. They are not configuration claims.

## 4. Evidence Sources

Producer Health reads:

- `neuron_registry`
- `neuron_producers`
- `neuron_signals`
- `neuron_signal_bindings`
- `signal_quality_evaluations`
- `signal_processing_states`
- `signal_lineage_coverage_analysis`
- `dry_run_provenance_analysis`
- existing runtime dashboard truth

If registry data is unavailable, observed producers can still be reported from signal/provenance evidence, but registry coverage is not invented.

## 5. Classification Rules

Deterministic classification:

- Registered/expected producer with no observed Signals -> `SILENT`
- Expected neuron with no observed evidence -> `MISSING`
- Only dry-run-derived evidence -> `DRY_RUN_ONLY`
- Recent runtime Signals with acceptable quality/lineage -> `HEALTHY`
- Runtime evidence but not fully recent -> `ACTIVE`
- Stale output ratio >= 50 percent -> `DEGRADED` with `STALE_OUTPUT_HIGH`
- Any unbound lineage among observed Signals -> `DEGRADED` with `LINEAGE_INCOMPLETE`
- Average quality score below 0.60 -> `DEGRADED` with `QUALITY_LOW`
- Observed producer not in registry -> reported, not hidden
- Missing producer name -> `UNKNOWN`

Dry-run-only and unknown producers cannot feed Paper evidence.

## 6. API Route

`GET /dashboard/api/v2/producer-health`

Response includes:

- `mock_data=false`
- `overall_status`
- `paper_ready=false`
- `total_producers`
- `registered_producers`
- `observed_producers`
- `runtime_active_producers`
- `dry_run_only_producers`
- `silent_expected_neurons`
- `missing_neurons`
- `degraded_neurons`
- `producer_health`
- `neuron_runtime_truth`
- `last_updated`
- `analysis_status`

## 7. Mesh Dashboard Integration

`GET /dashboard/api/v2/mesh` now includes:

- `layers.producer_health`
- `flow.producer_health`
- `readiness.producer_health_summary`

Existing mesh layers remain intact:

- `signal_quality`
- `signal_processing`
- `link_coverage`
- `lineage_coverage`
- `dry_run_provenance`
- `mesh_blockers`

## 8. Mesh Blockers Integration

Producer-derived blockers are added only when active:

- `PRODUCER_HEALTH_DEGRADED`
- `EXPECTED_NEURONS_SILENT`
- `PRODUCERS_DRY_RUN_ONLY`
- `PRODUCER_RUNTIME_EVIDENCE_MISSING`

These blockers preserve existing Mesh Blocker behavior and continue to keep `paper_ready=false`.

## 9. Safety Rules

Part 4C-G does not:

- enable Paper
- enable Live
- create order intents
- create orders
- sign requests
- call AI
- start missing producers
- fabricate producer activity
- fabricate runtime evidence
- fix env/persisted mismatches

Dry-run-only producers are allowed for observability, not Paper evidence.

## 10. Current Runtime Interpretation

Runtime verification showed:

- `total_producers=34`
- `registered_producers=20`
- `observed_producers=17`
- `runtime_active_producers=0`
- `dry_run_only_producers=5`
- `overall_status=DEGRADED`
- `paper_ready=false`

This means the registry is not yet trusted as runtime producer truth for Paper readiness.

## 11. What Is Explicitly Not Included

This phase does not implement:

- Runtime Brain Producer Adapters
- Market Technical Truth
- orderbook snapshotter
- Risk Core
- Exit Foundation
- Opportunity Cortex
- Strategy Router
- Paper trading
- Live trading

## 12. Next Phase Recommendation

Recommended next phase: V2 Neural Mesh Part 4C-H: Runtime Producer Evidence Loop.

Goal: improve runtime producer evidence without enabling Paper, orders, or execution. The first step should be non-executing producer evidence for existing source/rules/market observations, with strict provenance and quality gates.
