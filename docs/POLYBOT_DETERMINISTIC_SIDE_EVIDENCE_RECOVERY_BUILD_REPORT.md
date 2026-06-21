# POLYBOT Deterministic Side Evidence Recovery Build Report

## Purpose

Recover and persist deterministic `matched_side=YES|NO` from real market/token evidence, then allow existing Candidate Eligibility Recovery to consume that side without forcing risk, exit, eligibility, paper execution, or live behavior.

## Current Reality Found

Before implementation, runtime had deterministic token metadata but did not persist side:

- `markets_v2` had `market_id`, `condition_id`, `yes_token_id`, `no_token_id`, `outcome_tokens_json`, and `raw_market_json`.
- `orderbook_snapshots` had `market_id`, `token_id`, and `side`.
- `signal_market_links` and `neuron_signal_bindings` had market/link truth but no populated `matched_side`.
- `neuron_signals.evidence_json.details.sample_token_id` contained token evidence for current runtime rows.
- `paper_eligibility_candidates.side=0`.
- `coordinator_decisions` explicit YES/NO side count was 0.
- `brain_outputs` explicit YES/NO side count was 0.

## Why matched_side Was Zero

The runtime created trusted signal-market links and bindings, but there was no deterministic token-side persistence layer between refreshed evidence and Candidate Eligibility Recovery. Candidates could have a market, token, and orderbook, but no persisted `matched_side` for eligibility to consume.

## Deterministic Mapping Rules Implemented

- `token_id == yes_token_id` maps to `YES`.
- `token_id == no_token_id` maps to `NO`.
- Token evidence is extracted only from structured runtime evidence payloads.
- Ambiguous YES+NO token evidence is rejected.
- Missing token mapping is rejected.
- Weak or stale lineage is rejected.
- Candidate side propagates only through trusted lineage.

## Invalid Sources Rejected

- title sentiment
- fuzzy text
- default YES
- default NO
- weak binding
- stale binding
- ambiguous mapping

## Files Created

- `app/services/side_evidence.py`
- `app/db/migrations/0092_deterministic_side_evidence_recovery.sql`
- `tests/test_deterministic_side_evidence_service.py`
- `tests/test_dashboard_side_evidence_truth.py`
- `tests/test_side_recovery_runtime.py`
- `tests/test_side_to_eligibility_consumption.py`
- `docs/POLYBOT_DETERMINISTIC_SIDE_EVIDENCE_RECOVERY.md`
- `docs/POLYBOT_DETERMINISTIC_SIDE_EVIDENCE_RECOVERY_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`
- `app/repositories/signal_market_binding_repository.py`

## DB Migration

`0092_deterministic_side_evidence_recovery.sql` adds:

- side evidence columns to `signal_market_links`
- side evidence columns to `neuron_signal_bindings`
- indexes for matched side and resolution timestamps
- `side_evidence_recovery_runs`

## Runtime Integration Point

`MarketService.refresh()` now runs deterministic side recovery after Evidence Refresh and before Downstream Evidence Recompute / Candidate Eligibility Recovery.

## API / Dashboard Changes

Added:

- `GET /dashboard/api/v2/side-evidence`

The endpoint uses DB/runtime truth only and returns `mock_data=false`.

## Tests Added

- SYSTEM OFF blocks side recovery.
- YES token maps to YES.
- NO token maps to NO.
- Ambiguous token evidence is rejected.
- Missing token mapping is rejected.
- Weak/text-only evidence is rejected.
- Candidate side propagates only with trusted lineage.
- Runtime order places side recovery before downstream recompute and eligibility recovery.
- Dashboard reports real side evidence truth.
- Recovered side can be consumed by Candidate Eligibility Recovery in controlled fixtures.

## Tests Run

- `docker compose --profile test run --rm test python -m pytest tests/test_deterministic_side_evidence_service.py tests/test_dashboard_side_evidence_truth.py tests/test_side_recovery_runtime.py tests/test_side_to_eligibility_consumption.py -q`
  - `9 passed in 51.66s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_market_binding_service.py tests/test_v2_signal_market_binding_repository.py tests/test_evidence_refresh_service.py tests/test_downstream_evidence_recompute_service.py tests/test_candidate_eligibility_recovery_service.py tests/test_paper_execution_service.py -q`
  - `29 passed in 176.75s`
- `docker compose --profile test run --rm test python -m pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py tests/test_brain_mesh_activation_service.py tests/test_brain_mesh_activation_scheduler.py tests/test_dashboard_brain_mesh_activation_truth.py tests/test_evidence_refresh_scheduler.py tests/test_dashboard_evidence_refresh_truth.py tests/test_downstream_evidence_recompute_scheduler.py tests/test_dashboard_downstream_recompute_truth.py tests/test_candidate_eligibility_recovery_service.py tests/test_dashboard_eligibility_recovery_truth.py tests/test_paper_execution_safety.py tests/test_paper_exit_safety.py tests/test_runtime_modes.py tests/test_state_governor.py -q`
  - `41 passed, 1 warning in 194.39s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py tests/test_v2_orderbook_snapshot_service.py tests/test_v2_signal_market_binding_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_paper_intent_service.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py -q`
  - `82 passed, 1 warning in 294.47s`

Total executed test pass events: 161. Some suites intentionally overlap.

## Runtime Smoke

Runtime was rebuilt/recreated safely, migration applied, and `/healthz` returned OK.

OFF check:

- `GET /dashboard/api/v2/side-evidence`: route live, `mock_data=false`, status `EMPTY`.
- SYSTEM OFF blocked runtime work.
- After one scheduler interval: `side_evidence_recovery_runs=0`, `links_with_matched_side=0`, `candidates_with_side=0`, paper/live/real execution counts unchanged.

ON check:

- `POST /system/power/on` returned SYSTEM ON with live disabled.
- Scheduler automatically ran side recovery.
- Two scheduler cycles ran while the smoke and report were being collected.
- Latest run: `status=OK`, `links_checked=100`, `sides_recovered=100`, `candidates_with_side_before=100`, `candidates_with_side_after=197`, `eligible_after=0`, `paper_intents_after=0`, `paper_positions_delta=0`, `live_orders_delta=0`, `real_orders_delta=0`.
- Final DB count: `candidates_with_side` increased from 0 to 195 after the runtime settled.
- `eligible_candidates` stayed 0 because risk/thesis/exit blockers remain.
- `paper_intents=0`, `paper_orders=0`, `paper_fills=0`, `paper_positions=0`, `live_orders=0`.

## Before / After Counts

| Metric | Before | After |
| --- | ---: | ---: |
| signal_market_links | 2255 | 2261 |
| links with matched_side | 0 | 200 |
| neuron_signal_bindings | 6231 | 6255 |
| bindings with matched_side | 0 | 200 |
| coordinator explicit side | 0 | 0 |
| brain output explicit side | 0 | 0 |
| candidates with side | 0 | 195 |
| eligible candidates | 0 | 0 |
| paper_intents | 0 | 0 |
| executable paper_intents | 0 | 0 |
| paper_orders | 0 | 0 |
| paper_fills | 0 | 0 |
| paper_positions | 0 | 0 |
| open paper positions | 0 | 0 |
| live_orders | 0 | 0 |
| orders_v2 | 1 | 1 |
| fills_v2 | 1 | 1 |
| positions | 0 | 0 |

## Before / After Blockers

| Blocker | Before | After |
| --- | ---: | ---: |
| MISSING_SIDE | 5930 | 5912 |
| SIDE_CONFLICT | 0 | 0 |
| MISSING_SIGNAL_MARKET_BINDING | 3744 | 3754 |
| MISSING_FRESH_ORDERBOOK | 3744 | 3754 |
| RISK_NOT_APPROVED | 5930 | 5946 |
| EXIT_NOT_READY | 5930 | 5946 |
| THESIS_BLOCKED | 0 | 0 |
| THESIS_NOT_COMPLETE | 5930 | 5946 |
| NO_VALID_PAPER_INTENTS | 0 | 0 |

Counts rose for some blockers because the live scheduler created additional candidates during the smoke. Side recovery still reduced the blocker on candidates with deterministic token evidence; their next blocker became `RISK_NOT_APPROVED`.

## 10-Candidate Trace Summary

Latest trace showed mixed candidate truth:

- Candidates linked to market `824952` with token `111128191581505463501777127559667396812474366956707382672202929745167742497287` matched `yes_token_id` and now carry `side=YES`.
- Their eligibility blockers no longer include `MISSING_SIDE`; next blocker is `RISK_NOT_APPROVED`, with `EXIT_NOT_READY` and `THESIS_NOT_COMPLETE` still present.
- Candidates without deterministic token evidence, missing market metadata, or missing binding remain `MISSING_SIDE`.
- No traced candidate created a paper intent.

## Paper Intent Result

No paper intents were created. This is expected because eligibility remained blocked by risk/thesis/exit evidence.

## Paper Execution Result

No paper orders, paper fills, or paper positions were created.

## Safety Confirmation

- SYSTEM OFF blocked side recovery.
- SYSTEM ON ran side recovery automatically.
- No side was defaulted or inferred from weak text.
- No eligibility was forced.
- No risk/exit gates were bypassed.
- `paper_intents=0`.
- `paper_orders=0`.
- `paper_fills=0`.
- `paper_positions=0`.
- `live_orders=0`.
- `orders_v2=1` historical unchanged.
- `fills_v2=1` historical unchanged.
- `positions=0`.

## Remaining Risks

- Only runtime rows with deterministic token evidence can recover side.
- Coordinator and brain outputs still have no explicit structured side fields.
- Many candidates still lack market/binding/orderbook evidence.
- Risk remains blocked and was not changed by this phase.

## Next Recommended Step

Proceed to Paper Dashboard + Regression + Soak Readiness after review, with special attention to why risk/thesis/exit remain blocked after side recovery.

## Status

GREEN: deterministic side recovery runs automatically under SYSTEM ON, SYSTEM OFF blocks it, matched side is persisted from real token evidence, candidates with side increased, dashboard truth exists, tests pass, and execution safety remained locked.
