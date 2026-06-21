# POLYBOT V2 Neural Mesh Part 4C-A Signal Quality Contract Build Report

## 1. Purpose

Implement the first Mesh Hardening slice: a Signal Quality Contract that scores Signal readiness, persists latest evaluations, exposes API/dashboard truth, and keeps Paper readiness blocked.

## 2. Current Reality Found

Fresh pre-implementation verification:

- `neuron_signals=139`
- `unprocessed_signals=139`
- `unlinked_signals=119`
- `unbound_signals=36`
- `signal_market_links=20`
- `signal_position_links=0`
- `brain_outputs=48`
- `coordinator_decisions=12`
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `execution_allowed_true=0`
- `/dashboard/api/v2/mesh` exists and returns `mock_data=false`
- `/mesh/dry-runs/recent` exists and returns `mock_data=false`
- persisted runtime mode remains DATA_ONLY
- environment mode remains PAPER
- LIVE remains false
- environment KILL remains true
- persisted kill switch remains false

The known safety mismatch was tracked and not fixed in this phase.

## 3. Files Created

- `app/db/migrations/0068_v2_neural_mesh_signal_quality_contract.sql`
- `app/neural_mesh/signal_quality.py`
- `app/repositories/signal_quality_repository.py`
- `app/services/signal_quality.py`
- `app/api/signal_quality_routes.py`
- `tests/test_v2_signal_quality_contract.py`
- `tests/test_v2_signal_quality_repository.py`
- `tests/test_v2_signal_quality_api.py`
- `tests/test_v2_dashboard_signal_quality.py`
- `docs/V2_NEURAL_MESH_PART4C_A_SIGNAL_QUALITY_CONTRACT.md`
- `docs/V2_NEURAL_MESH_PART4C_A_SIGNAL_QUALITY_CONTRACT_BUILD_REPORT.md`

## 4. Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/services/mesh_dashboard.py`

No trading logic changed.
No execution code changed.
No runtime mode logic changed.

## 5. DB Migration

Migration added and applied:

- `0068_v2_neural_mesh_signal_quality_contract.sql`

Production migration result:

```text
Applied migrations:
- 0068_v2_neural_mesh_signal_quality_contract.sql
```

Test migration result:

```text
Applied migrations:
- 0068_v2_neural_mesh_signal_quality_contract.sql
```

Table:

- `signal_quality_evaluations`

Purpose:

- one latest quality evaluation per Signal
- persisted quality score/status
- missing field reasons
- `can_feed_brain`
- `can_feed_paper`
- dry-run/runtime provenance
- staleness/linkage/lineage/evidence flags

## 6. API Routes

Added:

- `GET /signals/quality/recent`
- `GET /signals/{signal_id}/quality`
- `POST /signals/quality/evaluate/recent`
- `POST /signals/{signal_id}/quality/evaluate`
- `GET /dashboard/api/v2/signal-quality`

All return `mock_data=false`.

## 7. Dashboard Changes

Added signal quality dashboard truth:

- total evaluated
- average quality score
- Signals that can feed Brain Outputs
- Signals that can feed Paper evidence
- quality status distribution
- missing field summary
- dry-run/runtime generated counts
- low-quality Signals
- Paper blocking reasons

Integrated signal quality into:

- `GET /dashboard/api/v2/mesh`

Mesh fields added:

- `layers.signal_quality`
- `mesh_summary.signal_quality_avg`
- `mesh_summary.signals_can_feed_brain`
- `mesh_summary.signals_can_feed_paper`
- `flow.signal_quality`
- readiness blockers for missing signal quality evaluations and zero paper-feed Signals

`paper_ready` remains false.

## 8. Tests Added

- `tests/test_v2_signal_quality_contract.py`
- `tests/test_v2_signal_quality_repository.py`
- `tests/test_v2_signal_quality_api.py`
- `tests/test_v2_dashboard_signal_quality.py`

Coverage includes:

- full metadata scoring
- missing market ID
- missing lineage cap
- missing market link cap
- missing evidence cap
- stale penalty/status
- dry-run cap
- can_feed_brain
- strict can_feed_paper
- score clamping
- persistence of missing fields and readiness reason
- API routes
- dashboard route
- mesh dashboard integration
- no order/live mutation

## 9. Tests Run With Exact Results

Targeted tests:

```text
docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_quality_contract.py -q
9 passed in 0.92s

docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_quality_repository.py -q
3 passed in 17.77s

docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_quality_api.py -q
3 passed in 16.19s

docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_signal_quality.py -q
3 passed in 23.91s
```

Relevant regressions:

```text
docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_mesh.py -q
5 passed in 8.31s

docker compose --profile test run --rm test python -m pytest tests/test_v2_mesh_dry_run_contract.py tests/test_v2_mesh_dry_run_flow.py tests/test_v2_dashboard_mesh_dry_run.py -q
6 passed in 40.69s

docker compose --profile test run --rm test python -m pytest tests/test_v2_neuron_signal_contract.py tests/test_v2_dashboard_signals.py -q
11 passed in 6.32s

docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_event_binding_contract.py tests/test_v2_dashboard_signal_lineage.py -q
6 passed in 5.66s

docker compose --profile test run --rm test python -m pytest tests/test_v2_impact_graph_contract.py tests/test_v2_dashboard_impact_graph.py -q
11 passed in 6.25s

docker compose --profile test run --rm test python -m pytest tests/test_v2_brain_output_contract.py tests/test_v2_dashboard_brain_outputs.py -q
19 passed in 5.71s

docker compose --profile test run --rm test python -m pytest tests/test_v2_brain_coordinator_contract.py tests/test_v2_dashboard_coordinator.py -q
11 passed in 5.56s
```

Total recorded test result for this phase:

- 87 passed

## 10. Runtime Verification

Before evaluation:

```text
/healthz 200 ok
/runtime/health 200 HEALTHY
/runtime/state 200
/signals/recent 200 OK mock=False
/signals/quality/recent 200 OK mock=False count=0
/dashboard/api/v2/signal-quality 200 EMPTY mock=False total=0 paper=0
/dashboard/api/v2/mesh 200 DEGRADED mock=False paper_ready=False sq_total=0
```

Safe evaluation command:

```text
POST /signals/quality/evaluate/recent {"limit":100}
```

Result:

```json
{
  "status": "OK",
  "mock_data": false,
  "evaluated": 100,
  "created_or_updated": 100,
  "summary": {
    "total_evaluated": 100,
    "avg_quality_score": 0.6624,
    "can_feed_brain": 12,
    "can_feed_paper": 0
  }
}
```

After evaluation:

```text
/signals/quality/recent 200 OK mock=False count=50
/signals/{signal_id}/quality OK mock=False status=STALE can_feed_paper=False
/dashboard/api/v2/signal-quality 200 DEGRADED mock=False total=100 avg=0.6624 brain=12 paper=0
/dashboard/api/v2/mesh 200 DEGRADED mock=False paper_ready=False sq_total=100 sq_paper=0
```

## 11. Signal Quality Evaluation Result

Production evaluation of 100 recent Signals:

- evaluated: 100
- created_or_updated: 100
- total_evaluated: 100
- avg_quality_score: 0.6624
- can_feed_brain: 12
- can_feed_paper: 0
- quality statuses:
  - STALE: 88
  - PARTIAL: 12
- top missing fields:
  - position_link: 100
  - fresh_signal: 88
  - linked_to_market: 80
  - used_by_brain_output: 80
  - used_by_coordinator: 80
  - market_id: 24
  - production_market_link: 20
  - freshness: 12
  - raw_payload_ref: 5

Interpretation:

Signals can now be scored and blocked truthfully. The current signal set is not Paper-feed-ready. This is expected and safe.

## 12. Safety Verification

Environment:

```text
MODE= PAPER
BACKEND= paper
LIVE= false
KILL= true
```

Runtime:

```text
/runtime/health overall_status=HEALTHY current_mode=DATA_ONLY kill_switch_active=false
```

DB safety:

```text
paper_orders=0
shadow_orders=0
live_orders=0
execution_allowed_true=0
signal_quality_evaluations=100
can_feed_paper=0
order_intents=missing
```

No private keys printed.
No signing path invoked.
No order/cancel/live mutation path touched.
No order intents created.
Global `paper_ready` remained false.

## 13. What Is Complete

- Signal Quality Contract exists.
- Quality evaluations persist.
- Scoring and caps work.
- Missing fields and readiness reasons persist.
- `can_feed_brain` works as informational readiness.
- `can_feed_paper` works as strict informational readiness.
- Signal quality APIs work.
- Dashboard signal-quality endpoint works.
- Mesh dashboard includes signal quality summary.
- Tests pass.
- Runtime remains healthy.
- Safety remains intact.

## 14. What Is Partial

- Only latest-per-signal quality is stored; history/snapshots are intentionally deferred.
- Quality is evaluated on demand, not automatically on every Signal write.
- Signal Processing State is not implemented yet.
- Production market link quality is visible as a blocker but not remediated here.

## 15. Remaining Risks

- Many existing Signals are stale.
- Most evaluated Signals cannot feed Brain Outputs yet.
- No evaluated Signals can feed Paper evidence.
- Dry-run-created market links are not sufficient for Paper evidence.
- Existing env/persisted runtime mode and kill-switch mismatches remain tracked but unresolved.

## 16. Recommended Next Phase

V2 Neural Mesh Part 4C-B: Signal Processing State + Quality Gate Enforcement.

Goal:
Track and enforce whether each Signal has been evaluated, linked, consumed, rejected, or blocked by quality gates, without enabling Paper or creating orders.

## 17. Final Status

GREEN.

The phase is complete, tested, evidence-based, non-executing, and safety remains intact.
