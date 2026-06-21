# POLYBOT V3.4 Coordinator Evolution Build Report

## Phase

Mission: V3.4 Coordinator Evolution, Mesh Decision Judge

Status: GREEN

Can move to Position-Aware Reactions / Capital Brain Upstream: YES, after required ChatGPT review.

## Current Reality Found

Existing coordinator concepts:

- `RuntimeCoordinatorDecisionService` is the active runtime coordinator path for legacy `brain_outputs` -> `coordinator_decisions`.
- `BrainCoordinatorService` already contains legacy consensus/conflict concepts for canonical brain outputs.
- Legacy `coordinator_decisions` currently mostly remain single-brain decisions.
- V3.3 mesh tables exist: `mesh_brain_opinions`, `mesh_brain_consumption_sources`, and `mesh_coordinator_input_bundles`.
- Mesh input bundles existed but did not yet produce final mesh decisions.

Runtime DB inspection before V3.4 smoke:

- `mesh_coordinator_input_bundles`: 3
- `mesh_brain_opinions`: 15
- `coordinator_decisions`: 10636
- `brain_outputs`: 10672
- legacy `source_brain_count` distribution: mostly 1, with a small count of 4
- legacy `conflict_count` distribution: mostly 0
- mesh bundle source brain count: 4 for existing bundles

## Files Created

- `app/db/migrations/0105_v3_coordinator_evolution.sql`
- `app/mesh_coordinator/__init__.py`
- `app/mesh_coordinator/types.py`
- `app/mesh_coordinator/repository.py`
- `app/mesh_coordinator/service.py`
- `tests/test_v3_mesh_coordinator_evolution.py`
- `docs/POLYBOT_COORDINATOR_EVOLUTION.md`
- `docs/POLYBOT_COORDINATOR_EVOLUTION_BUILD_REPORT.md`

## Files Changed

- `app/multi_brain_consumption/service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Migration applied:

- `0105_v3_coordinator_evolution.sql`

Tables:

- `mesh_coordinator_decisions`
- `mesh_coordinator_decision_sources`
- `mesh_conflict_records`

## Coordinator Model

Mesh coordinator decisions are derived, source-linked, non-executing judgments.

Inputs:

- `mesh_coordinator_input_bundles`
- `mesh_brain_opinions`

Outputs:

- one idempotent `mesh_coordinator_decisions` row per session/bundle
- source links in `mesh_coordinator_decision_sources`
- deterministic conflict rows in `mesh_conflict_records`

## Arbitration Rules

- Risk `BLOCK` wins over support.
- Capital `BLOCK` wins over support.
- Exit `BLOCK` blocks entry interpretation.
- Context support alone cannot approve.
- Most `NO_SIGNAL` means `INSUFFICIENT_DATA`.
- Risk `CAUTION` with protective support resolves to `WATCH`.
- All key protective brains support resolves to `PAPER_CANDIDATE_REVIEW`, not execution.
- Position adverse Risk/Exit context resolves to `EXIT_REVIEW`.

## Conflict Rules

Supported conflict types:

- `support_vs_block`
- `caution_vs_support`

Resolution is deterministic and recorded. V3.4 does not resolve conflicts into execution.

## Runtime Integration

`MultiBrainConsumptionService.consume_session_with_conn()` now runs `MeshCoordinatorDecisionService.judge_session_with_conn()` after the coordinator observer bundle is created, when V3.4 tables are present.

System OFF:

- publishing blocked
- direct mesh coordinator mutation blocked
- dashboard read allowed

System ON:

- real event/session/awareness/opinion/bundle flow can create mesh coordinator decisions

## API Routes

- `GET /dashboard/api/v2/mesh-coordinator`
- `GET /dashboard/api/v2/mesh-coordinator/{decision_id}`
- `GET /dashboard/api/v2/mesh-coordinator/session/{session_id}`

Verified from API container with `curl`; all returned HTTP 200 and `mock_data=false`.

## Dialogue

`BrainDialogueService` now materializes:

- final mesh decision messages from `mesh_coordinator_decisions`
- conflict messages from `mesh_conflict_records`

Sample dialogue:

- `Coordinator: Final mesh decision: WATCH with action WATCH because Brain opinions disagree without a hard BLOCK; coordinator resolves to WATCH.`
- `Coordinator: Conflict detected: RISK_BRAIN CAUTION vs CAPITAL_BRAIN SUPPORT. RISK_BRAIN wins.`

## Tests Added

`tests/test_v3_mesh_coordinator_evolution.py` covers:

- decision creation from bundle
- source brain count preservation
- all `NO_SIGNAL` -> `INSUFFICIENT_DATA`
- Risk `BLOCK` wins
- Capital `BLOCK` wins
- Exit `BLOCK` wins
- all key support -> `PAPER_CANDIDATE_REVIEW`
- position adverse context -> `EXIT_REVIEW`
- conflict recording
- no conflict when aligned
- source links to real opinions
- idempotent rerun
- dashboard summary/detail/session routes
- System OFF publish/direct mutation blocking
- runtime publish integration
- no trading or legacy decision mutation
- dialogue materialization

## Tests Run

1. `docker compose --profile test run --rm test python -m pytest tests/test_v3_mesh_coordinator_evolution.py -q`

Result: `15 passed, 1 warning in 69.00s`

2. `docker compose --profile test run --rm test python -m pytest tests/test_v3_neural_event_bus.py tests/test_v3_mesh_sessions_foundation.py tests/test_v3_shared_awareness_layer.py tests/test_v3_multi_brain_consumption_layer.py tests/test_v3_mesh_coordinator_evolution.py -q`

Result: `56 passed, 1 warning in 258.37s`

3. `docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_brain_adapter_safety.py tests/test_v2_runtime_coordinator_safety.py tests/test_v2_risk_core_safety.py tests/test_v2_exit_foundation_safety.py tests/test_v2_paper_eligibility_safety.py tests/test_v2_paper_intent_safety.py tests/test_paper_no_live_safety.py -q`

Result: `11 passed, 1 warning in 66.62s`

Warnings were Starlette TestClient/httpx deprecation warnings, not phase failures.

## Runtime Smoke

Commands:

- `docker compose build api migrate`
- `docker compose run --rm migrate`
- `docker compose up -d api`
- Python smoke inside `api` container
- API dashboard verification with container-local `curl`

Smoke sequence:

1. System OFF
2. Publish attempt blocked
3. No table counts changed while OFF
4. System ON
5. Published `ORDERBOOK_REFRESHED` with `market_id` and `candidate_id`
6. Published `RISK_CHANGED` with same `market_id` and `candidate_id`
7. Verified sessions, awareness, brain opinions, bundles, mesh decisions, source links, conflict records
8. Verified dashboard routes return `mock_data=false`
9. Verified coordinator dialogue appears
10. Verified no trading mutation
11. System OFF

## Before/After Counts

Before smoke:

- `neural_events`: 7
- `mesh_sessions`: 10
- `mesh_shared_awareness`: 10
- `mesh_brain_opinions`: 15
- `mesh_coordinator_input_bundles`: 3
- `mesh_coordinator_decisions`: 0
- `mesh_coordinator_decision_sources`: 0
- `mesh_conflict_records`: 0
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `paper_intents`: 6
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- `paper_accounts`: 1
- `risk_decisions`: 10332
- `exit_plans`: 10332
- `paper_eligibility_candidates`: 10332
- `coordinator_decisions`: 10636
- `brain_outputs`: 10672

After System ON smoke:

- `neural_events`: 9
- `mesh_sessions`: 12
- `mesh_shared_awareness`: 12
- `mesh_brain_opinions`: 25
- `mesh_coordinator_input_bundles`: 5
- `mesh_coordinator_decisions`: 2
- `mesh_coordinator_decision_sources`: 8
- `mesh_conflict_records`: 2
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `paper_intents`: 6
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- `paper_accounts`: 1
- `risk_decisions`: 10332
- `exit_plans`: 10332
- `paper_eligibility_candidates`: 10332
- `coordinator_decisions`: 10636
- `brain_outputs`: 10672

After System OFF completion:

- trading, paper, risk, exit, eligibility, legacy coordinator, and brain output counts remained unchanged from after System ON smoke.

Derived metrics:

- `avg_source_brain_count`: 4.0
- `conflicts_detected_count`: 2

## Sample Decisions

- `mesh_decision_mesh_session_candidate_session_419255b3203eec63f2b0fb65`
  - final stance: `WATCH`
  - final action: `WATCH`
  - source brain count: 4
  - conflict count: 1
  - safety status: `SAFE_NON_EXECUTING`

- `mesh_decision_mesh_session_threat_session_c05f52c9bb5d9240d8a00ea4`
  - final stance: `WATCH`
  - final action: `WATCH`
  - source brain count: 4
  - conflict count: 1
  - safety status: `SAFE_NON_EXECUTING`

## Sample Conflict Records

- `mesh_conflict_mesh_session_candidate_session_419255b3203eec63f2b0fb65_1`
  - type: `caution_vs_support`
  - `RISK_BRAIN CAUTION` vs `CAPITAL_BRAIN SUPPORT`
  - winner: `RISK_BRAIN`
  - resolution: `Protective caution wins by forcing WATCH.`

- `mesh_conflict_mesh_session_threat_session_c05f52c9bb5d9240d8a00ea4_1`
  - type: `caution_vs_support`
  - `RISK_BRAIN CAUTION` vs `CAPITAL_BRAIN SUPPORT`
  - winner: `RISK_BRAIN`
  - resolution: `Protective caution wins by forcing WATCH.`

## Safety Checklist

- Live trading not enabled.
- Shadow trading not enabled.
- No orders created.
- No fills created.
- No positions created.
- No paper intents created.
- Paper orders/fills/positions unchanged.
- Paper capital account count unchanged.
- Risk decisions unchanged.
- Exit plans unchanged.
- Eligibility outcomes unchanged.
- Legacy `coordinator_decisions` unchanged.
- `brain_outputs` unchanged.
- Mesh decisions are derived and source-linked.

## Remaining Risks

- Runtime data currently lacks enough rich domains for diverse real-world conflict patterns.
- V3.4 conflict detection is intentionally simple and must be expanded carefully in Coordinator Evolution follow-up phases.
- Mesh decisions are not yet consumed by old coordinator, eligibility, or execution gates by design.
- ChatGPT review is still required by phase policy.

## Next Recommended Phase

Position-Aware Reactions / Capital Brain Upstream, after ChatGPT review.
