# Candidate Explanation Ledger Report

Date: 2026-06-14

## Purpose

Phase 4 adds a read-only Candidate Explanation Ledger that explains why each paper eligibility candidate is blocked, eligible, waiting for refresh, ready for intent, or already linked to a paper intent.

The phase does not create trades, paper intents, orders, fills, positions, or position closes.

## Current Reality Found

Current production DB truth:

- Total candidates: 20,162
- Blocked candidates: 17,222
- Eligible candidates: 2,940
- Paper intents: 20
- Eligible without intent: 2,926
- Candidate ledger freshness: STALE
- Candidate readiness: BLOCKED

Top blockers:

- `EXIT_NOT_READY`: 17,219
- `RISK_BLOCKED`: 17,219
- `RISK_NOT_APPROVED`: 17,219
- `THESIS_NOT_COMPLETE`: 17,217
- `MISSING_SIDE`: 15,451
- `MISSING_FRESH_ORDERBOOK`: 12,506
- `MISSING_SIGNAL_MARKET_BINDING`: 12,436
- `MISSING_MARKET_ID`: 11,061

## Existing Sources Reused

- Candidate ledger: `paper_eligibility_candidates`
- Paper intent linkage: `paper_intents`
- No-trade linkage: `no_trade_log`
- Risk result: `risk_decisions`
- Exit result: `exit_plans`
- Thesis result: `thesis_profiles`
- Lifecycle governance: `lifecycle_governance_decisions`
- Orderbook freshness: `orderbook_snapshots`
- Market freshness: `markets_v2`, `market_snapshots_v2`
- Signal binding: `neuron_signal_bindings`
- Paper/system readiness context: existing runtime and paper readiness endpoints

## Candidate Explanation Model

Each candidate item now exposes:

- `candidate_id`, `market_id`, `side`, timestamps, source and creator
- `explanation_state`
- `progress_state`
- `final_outcome`
- `final_blocker`
- normalized `blockers`
- full `blocker_stack`
- evidence for market, signal, orderbook, risk, exit, thesis, governance, eligibility, and intent
- results for risk, exit, thesis, governance, eligibility, and intent
- `missing_data`
- `stale_data`
- `required_to_pass`
- `next_possible_state`
- `operator_summary`

## Files Inspected

- `AGENTS.md`
- `docs/POLYBOT_CONTEXT_INDEX.md`
- `docs/POLYBOT_AGENT_DISPATCH_PROTOCOL.md`
- `docs/POLYBOT_V2_MASTER_CONTEXT.md`
- `docs/POLYBOT_SAFETY_RULES.md`
- `docs/POLYBOT_AGENT_WORKFLOW.md`
- `docs/POLYBOT_ULTIMATE_FORENSIC_AUTOPSY.md`
- `docs/TRUTH_HARDENING_REPORT.md`
- `docs/CURRENT_RUNTIME_READINESS_REPORT.md`
- `docs/CURRENT_PAPER_READINESS_REPORT.md`
- `app/control_center/paper_readiness.py`
- `app/services/paper_eligibility.py`
- `app/services/paper_intents.py`
- `app/api/routes.py`
- Control Center frontend API/cockpit files
- Candidate/paper/no-trade migrations and tests

## Files Changed

- `app/control_center/candidate_explanations.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `tests/test_candidate_explanations.py`
- `tests/test_control_center_read_only_apis.py`
- `docs/CANDIDATE_EXPLANATION_LEDGER_REPORT.md`
- `frontend/control-center/dist/*` via `npm run build`

## APIs Changed

Added:

- `GET /dashboard/api/v2/control/candidate-explanations`
- `GET /dashboard/api/v2/control/candidate-explanations/{candidate_id}`

Supported list filters:

- `limit`
- `offset`
- `status`
- `market_id`
- `side`
- `blocker`
- `final_outcome`
- `freshness_state`
- `include_evidence`
- `include_required_to_pass`

## Frontend Changes

The Control Center cockpit now includes a Candidate Explanation Ledger panel showing:

- candidate counts
- blocked/eligible/ready-for-intent/intent-created/stale counts
- eligible-to-intent gap
- top blockers
- one candidate explanation sample
- final blocker
- required-to-pass items

No new action controls were added.

## Tests Added

Added `tests/test_candidate_explanations.py` with 15 tests covering:

- blocked candidate blocker stack
- missing market ID
- missing side
- stale orderbook
- risk blocked
- exit not ready
- thesis incomplete
- lifecycle governance denied
- eligible candidate without intent
- eligible-to-intent gap
- existing intent linkage
- incomplete evidence
- required-to-pass coverage
- read-only safety
- response shape

## Tests Run And Exact Results

- `POLYBOT_DATABASE_URL=<local test db>; .venv\Scripts\python.exe -m pytest tests/test_candidate_explanations.py -q`
  - Result: `15 passed in 81.72s`
- `POLYBOT_DATABASE_URL=<local test db>; .venv\Scripts\python.exe -m pytest tests/test_paper_readiness.py tests/test_truth_hardening.py tests/test_runtime_readiness.py tests/test_control_center_read_only_apis.py -q`
  - Result: `33 passed in 143.88s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed
- `npm run typecheck`
  - Result: passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed`, `18 tests passed`
- `npm run build`
  - Result: passed; existing Vite large chunk warning remains

## GET Verification Results

Active port 8000 after rebuilding and recreating only `polybot_api`:

- `GET /healthz`: 200, `status=ok`
- `GET /runtime/health`: 200, `overall_status=SAFE_STOPPED`, `runtime_life_state=STOPPED`, `system_power_state=OFF`, `readiness_state=BLOCKED`
- `GET /dashboard/api/v2/control/runtime-readiness`: 200, `status=LOCKED`, `runtime_life_state=STOPPED`, `system_power_state=OFF`
- `GET /dashboard/api/v2/control/paper-readiness`: 200, `paper_readiness_state=BLOCKED`, `runtime_life_state=STOPPED`, `system_power_state=OFF`
- `GET /dashboard/api/v2/control/candidate-explanations`: 200, `status=STALE`, `total_candidates=20162`, `blocked=17222`, `eligible=2940`, `eligible_without_intent=2926`
- `GET /dashboard/api/v2/control/candidate-explanations/{candidate_id}`: 200, `explanation_state=EXPLAINED_BLOCKED`, `final_outcome=BLOCKED`
- `GET /dashboard/api/v2/control/overview`: 200, `status=PARTIAL`

## Candidate Explanation Sample

Candidate:

- `eligibility_exit_risk_thesis_coord_3bfd6e16404c4693b329fe7eed2523dd`

Result:

- `explanation_state=EXPLAINED_BLOCKED`
- `final_outcome=BLOCKED`
- `final_blocker=RISK_BLOCKED`

Blockers returned:

- `EXIT_NOT_READY`
- `RISK_BLOCKED`
- `RISK_NOT_APPROVED`
- `THESIS_NOT_COMPLETE`
- `MISSING_MARKET_LINK`
- `THESIS_BLOCKED`
- `MISSING_RISK_APPROVAL`
- `GOVERNANCE_MISSING`

## Top Blockers

The active endpoint reports top blocker `EXIT_NOT_READY`, followed by risk and thesis blockers. This matches the forensic audit and confirms the ledger is using persisted blocker truth.

## Eligible-To-Intent Gap

Current gap:

- Eligible candidates: 2,940
- Paper intents: 20
- Eligible without intent: 2,926

This phase exposes the gap only. It does not implement the Eligible-to-Intent Bridge.

## Remaining Explanation Risks

- Candidate/source rows are stale because the system is safely stopped.
- Some legacy blockers appear outside the normalized Phase 4 list, such as `MISSING_MARKET_LINK`, `THESIS_BLOCKED`, and `MISSING_RISK_APPROVAL`; they are preserved rather than hidden.
- Some governance evidence is missing for historical candidates and is surfaced as `GOVERNANCE_MISSING`.
- The ledger is read-only and cannot resolve freshness, eligibility, or intent gaps.

## Deployment

Port 8000 owner:

- `polybot_api` publishes `0.0.0.0:8000->8000/tcp`
- Windows listeners are Docker/WSL plumbing: `com.docker.backend` and `wslrelay`

Deployment actions:

- `npm run build`
- `docker compose build api`
- `docker compose up -d --no-deps api`

Only the API container was recreated. No DB migration, DB deletion, volume reset, or POST action endpoint was used.

## Next Recommended Phase

Implement the Eligible-to-Intent Bridge as a separate phase, after explicitly preserving Governor, risk, exit, lifecycle, paper simulation, and freshness gates.

## Safety Checklist

- Live remained disabled: YES
- Shadow remained disabled: YES
- Paper was not activated: YES
- System ON was not activated: YES
- Full Monitor Run was not started: YES
- No POST action endpoints called: YES
- No paper intents created: YES
- No paper orders created: YES
- No paper fills created: YES
- No positions created: YES
- No position closes created: YES
- State Governor was not bypassed: YES
- Risk behavior was not changed: YES
- Exit behavior was not changed: YES
- Capital behavior was not changed: YES
- Execution behavior was not changed: YES
- No secrets printed: YES
- No fake dashboard data introduced: YES
- Active server GET verification completed: YES

## Status

GREEN for Phase 4 visibility:

- Candidate Explanation Ledger is implemented.
- Candidate list and detail endpoints are exposed.
- Top blockers are exposed.
- Eligible-to-intent gap is exposed.
- `required_to_pass` is populated.
- Tests pass.
- Active server on port 8000 returns 200 for the new endpoint.
- No safety behavior changed.

Safe to proceed to next phase: YES, for read-only review or a separately scoped Eligible-to-Intent Bridge.

Safe for PAPER/SHADOW/LIVE activation: NO.
