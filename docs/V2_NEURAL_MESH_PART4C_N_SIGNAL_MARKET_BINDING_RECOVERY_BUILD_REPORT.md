# V2 Neural Mesh Part 4C-N Signal / Market Binding Recovery Build Report

## Purpose

Implement evidence-based Signal to market binding recovery using local DB/runtime truth only. The phase adds deterministic candidate classification, safe high-confidence auto-link support, review-only suggestions, dashboard truth, mesh integration, and safety tests.

## Current Reality Found

- `neuron_signals=147`
- source-runtime Signals from evidence JSON: `8`
- `signal_market_links=20`
- unlinked Signals before runtime recovery: `127`
- unlinked source-runtime Signals: `8`
- `signal_suggested_market_links=3`
- link coverage: `linked_signals=20`, `unlinked_signals=88`, `link_coverage_ratio=0.1361`
- latest strict runtime recovery found `stale_skipped=109`, `weak_evidence_skipped=18`, `safe_links_created=0`
- `paper_ready=false`
- `paper_orders=0`, `shadow_orders=0`, `live_orders=0`
- `order_intents=absent`
- `positions=0`
- `fills_v2=1` historical row unchanged
- `execution_allowed_true=0`

## Audit Findings

Existing `signal_market_links` existed and had `20` rows, but lacked full binding recovery audit metadata. Existing link coverage had three safe-looking suggestions, but current strict runtime recovery did not apply them because stale evidence is blocked by default. Local market truth exists in `markets_v2`, and deterministic evidence can be derived from explicit `market_id`, token IDs, condition IDs, and exact slugs.

## Files Created

- `app/neural_mesh/signal_market_binding.py`
- `app/repositories/signal_market_binding_repository.py`
- `app/services/signal_market_binding.py`
- `app/db/migrations/0079_v2_neural_mesh_signal_market_binding_recovery.sql`
- `tests/test_v2_signal_market_binding_contract.py`
- `tests/test_v2_signal_market_binding_repository.py`
- `tests/test_v2_signal_market_binding_service.py`
- `tests/test_v2_signal_market_binding_api.py`
- `tests/test_v2_dashboard_market_binding.py`
- `tests/test_v2_signal_market_binding_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_N_SIGNAL_MARKET_BINDING_RECOVERY.md`
- `docs/V2_NEURAL_MESH_PART4C_N_SIGNAL_MARKET_BINDING_RECOVERY_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/mesh_dashboard.py`

## DB Migrations

- `0079_v2_neural_mesh_signal_market_binding_recovery.sql`

The migration extends `signal_market_links` with confidence/reason/evidence/method/audit columns and creates `signal_market_binding_recovery_runs` plus `signal_market_binding_candidates`.

## API Routes

- `POST /signals/market-binding/recover`
- `GET /dashboard/api/v2/market-binding`

## Dashboard Changes

- Added `layers.market_binding` to `/dashboard/api/v2/mesh`
- Added `flow.market_binding`
- Added `readiness.market_binding_summary`
- Market binding dashboard returns `mock_data=false`, link counts, runtime linked/unlinked counts, latest run, candidate blockers, and safety counters.

## Signal / Market Binding Contract

The contract is deterministic and non-AI. Safe auto-links require local market truth and high confidence. Suggestions and blocked candidates remain separate from actual `signal_market_links`.

## Evidence Rules

- `0.95`: explicit local `market_id`
- `0.90`: unique local `token_id`
- `0.85`: unique local `condition_id`
- `0.80`: exact local slug/ref
- ambiguous: blocked, never auto-linked
- weak: blocked or review-only, never auto-linked
- stale: skipped unless explicitly included
- dry-run: skipped unless explicitly included

## Signals Checked

Runtime verification checked `127` unlinked Signals with strict defaults. It counted `8` source-runtime Signals from source/evidence provenance.

## Links Before / After

Runtime verification:

- before: `20`
- after: `20`

No new links were applied because strict recovery blocked stale and weak evidence.

## Safe Links Created

`0` in runtime verification. The phase supports safe auto-linking and tests prove explicit market, token, and slug evidence paths.

## Suggestions Created

`0` in the strict runtime verification run. Existing link coverage suggestions remain `3`.

## Remained Unlinked

`127` remained unlinked in strict runtime verification.

## Unlinked Reasons

Latest runtime recovery:

- `BLOCKED_STALE`: `109`
- `BLOCKED_WEAK_EVIDENCE`: `18`

## Stale / Dry-Run Skipped

- stale skipped: `109`
- dry-run skipped: `0`

## Mesh Blockers Before / After

`SIGNAL_LINKING_TOO_LOW` remains active because link coverage ratio is `0.1361`, below Paper-readiness threshold. `NO_RISK_CORE`, `NO_EXIT_FOUNDATION`, `NO_PAPER_ELIGIBLE_SIGNALS`, `SIGNAL_LINEAGE_COVERAGE_LOW`, and `SIGNAL_QUALITY_GATE_BLOCKED` remain active. `paper_ready=false`.

## Tests Added

- Contract tests for candidate/run invariants
- Repository tests for persisted evidence/confidence
- Service tests for explicit market, token, slug, ambiguity, stale, dry-run, review-only, and weak evidence
- API/dashboard tests for `mock_data=false` and mesh layer presence
- Safety tests for zero executable artifacts and `paper_ready=false`

## Tests Run and Exact Results

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_market_binding_contract.py tests/test_v2_signal_market_binding_repository.py tests/test_v2_signal_market_binding_service.py tests/test_v2_signal_market_binding_api.py tests/test_v2_dashboard_market_binding.py tests/test_v2_signal_market_binding_safety.py -q` -> `14 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py tests/test_v2_link_coverage_contract.py tests/test_v2_link_coverage_repository.py tests/test_v2_link_coverage_api.py tests/test_v2_dashboard_link_coverage.py tests/test_v2_link_coverage_safety.py tests/test_v2_mesh_blockers_contract.py tests/test_v2_mesh_blockers_service.py tests/test_v2_mesh_blockers_api.py tests/test_v2_dashboard_mesh_blockers.py tests/test_v2_mesh_blockers_safety.py tests/test_v2_dashboard_mesh.py -q` -> `82 passed, 1 warning`
- Earlier full relevant regressions before the final runtime-provenance count tightening:
  - 4C consolidated: `46 passed, 1 warning`
  - orderbook snapshots: `12 passed, 1 warning`
  - runtime producer evidence: `10 passed, 1 warning`
  - runtime brain adapter: `11 passed, 1 warning`
  - runtime coordinator: `14 passed, 1 warning`
  - link coverage: `19 passed, 1 warning`
  - signal quality/processing: `37 passed, 1 warning`
  - lineage/provenance/producer health: `50 passed, 1 warning`
  - mesh blockers/dashboard mesh: `17 passed, 1 warning`
  - brain/coordinator/dry-run mesh: `36 passed, 1 warning`

Host Python could not run pytest: `No module named pytest`, so Docker test profile was used.

## Runtime Verification Results

Runtime endpoints used `http://127.0.0.1:8000`.

- `GET /healthz`: HTTP `200`
- `GET /runtime/health`: HTTP `200`, `overall_status=HEALTHY`
- `POST /signals/market-binding/recover`: HTTP `200`, `mock_data=false`, `status=OK`
- `GET /dashboard/api/v2/market-binding`: HTTP `200`, `mock_data=false`
- `GET /dashboard/api/v2/link-coverage`: HTTP `200`, `mock_data=false`
- `GET /dashboard/api/v2/mesh-blockers`: HTTP `200`, `mock_data=false`
- `GET /dashboard/api/v2/mesh`: HTTP `200`, `mock_data=false`, `layers.market_binding` present

Latest runtime recovery:

- `signals_checked=127`
- `runtime_signals_checked=8`
- `already_linked=0`
- `safe_links_created=0`
- `suggestions_created=0`
- `remained_unlinked=127`
- `stale_skipped=109`
- `dry_run_skipped=0`
- `weak_evidence_skipped=18`
- `signal_market_links_before=20`
- `signal_market_links_after=20`
- `paper_ready_after=false`
- `orders_created=0`
- `order_intents_created=0`
- `fills_created=0`
- `positions_created=0`
- `live_actions_created=0`

Dashboard:

- `total_signals=147`
- `runtime_signals=8`
- `signal_market_links=20`
- `linked_runtime_signals=0`
- `unlinked_runtime_signals=8`
- `link_coverage_ratio=0.1361`
- `paper_ready=false`

Safety counters:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents=absent`
- `fills_v2=1` historical row unchanged
- `positions=0`
- `execution_allowed_true=0`

Note: after container restart, orderbook freshness blockers reappeared because snapshots exceeded the freshness window. This phase did not collect orderbooks or alter orderbook state.

## Safety Verification

No orders, order intents, fills, positions, live actions, risk approvals, exit plans, strategy routes, or Paper readiness flips were created. Weak, ambiguous, stale, and dry-run evidence remains blocked from production link truth by default.

## Blockers Resolved

None in live runtime verification, because current candidate evidence is stale or weak under strict defaults.

## Blockers Remaining

- `SIGNAL_LINKING_TOO_LOW`
- `SIGNALS_STALE_HIGH`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `EXECUTION_NOT_ALLOWED`
- env/persisted mode and kill-switch mismatch blockers
- producer health/dry-run blockers
- orderbook freshness blockers appeared after runtime restart due snapshot staleness

## Remaining Risks

The system can safely auto-link deterministic fresh evidence, but the current live DB mostly contains stale unlinked candidates. Link coverage will not materially improve until runtime Signals are fresher, lineage remains complete, and local market IDs/tokens are present on fresh Signals.

## Next Recommended Phase

Refresh runtime Signal evidence and orderbook freshness, then rerun binding recovery; after that, proceed toward Thesis Profile, Risk Core, and Exit Foundation before any Paper eligibility or intent gate.

## Final Status

GREEN: implementation complete, tests pass, runtime verification completed, safety intact, `paper_ready=false`, no executable artifacts created, and no weak/stale/dry-run evidence was forced into link truth.
