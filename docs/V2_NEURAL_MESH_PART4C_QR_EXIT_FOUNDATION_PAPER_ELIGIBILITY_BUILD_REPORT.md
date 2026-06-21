# V2 Neural Mesh Part 4C-Q/R Build Report

## Purpose

Implement the combined controlled Paper-readiness safety phase: Exit Foundation plus Paper Eligibility Gate. Exit Foundation was already present from 4C-Q; this pass preserved it and added 4C-R Paper Eligibility.

## Current Reality Found

- `exit_plans` existed with 100 rows.
- `exit_plan_runs` and `exit_plan_rules` existed.
- Exit Foundation service/repository/contract existed.
- Paper Eligibility tables were absent before migration 0083.
- `paper_candidates` and `paper_ready_candidates` were absent.
- Existing exit configs/rules existed through Exit Foundation and legacy Exit Cortex V2 tables.
- `thesis_profiles=100`.
- `risk_decisions=100`.
- Risk split: APPROVE=0, REJECT=0, BLOCK=100.
- `risk_decisions.market_id` present on 76.
- `risk_decisions.orderbook_snapshot_id` present on 0.
- `risk_approved=true` count=0.
- thesis side count=0.
- risk/thesis side count=0.
- fresh `orderbook_snapshots` count=22, but current risk decisions do not reference them.

## Audit Findings

Minimum exit evidence: runtime risk decision, thesis, market_id, side, fresh linked orderbook, risk not blocked, deterministic target/stop/time/invalidation/emergency/liquidity rules.

Minimum Paper Eligibility evidence: runtime signal, brain output, coordinator decision, trusted signal-market binding, fresh orderbook, thesis, risk decision approved, complete exit plan, trusted lineage, and non-dry-run provenance.

Blocked risk creates blocked exit. Blocked/incomplete exit creates blocked or incomplete eligibility. `NO_EXIT_FOUNDATION` resolves with real exit plans only. `NO_PAPER_ELIGIBLE_SIGNALS` resolves with real eligible candidates only.

## Files Created

- `app/db/migrations/0083_v2_neural_mesh_paper_eligibility_gate.sql`
- `app/neural_mesh/paper_eligibility.py`
- `app/repositories/paper_eligibility_repository.py`
- `app/services/paper_eligibility.py`
- `tests/paper_eligibility_fixtures.py`
- `tests/test_v2_paper_eligibility_contract.py`
- `tests/test_v2_paper_eligibility_repository.py`
- `tests/test_v2_paper_eligibility_service.py`
- `tests/test_v2_paper_eligibility_api.py`
- `tests/test_v2_dashboard_paper_eligibility.py`
- `tests/test_v2_paper_eligibility_safety.py`
- `tests/test_v2_exit_foundation_safety_qr.py`
- `docs/V2_NEURAL_MESH_PART4C_QR_EXIT_FOUNDATION_PAPER_ELIGIBILITY.md`
- `docs/V2_NEURAL_MESH_PART4C_QR_EXIT_FOUNDATION_PAPER_ELIGIBILITY_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/mesh_dashboard.py`
- `app/services/mesh_blockers.py`

## DB Migrations

Applied to runtime DB:

- `0083_v2_neural_mesh_paper_eligibility_gate.sql`

Created:

- `paper_eligibility_candidates`
- `paper_eligibility_runs`

The schema enforces `paper_intent_allowed=false` and `execution_allowed=false`.

## API Routes

- `POST /exit/plans/build`
- `GET /exit/plans/recent`
- `GET /dashboard/api/v2/exit-foundation`
- `POST /paper/eligibility/evaluate`
- `GET /paper/eligibility/recent`
- `GET /dashboard/api/v2/paper-eligibility`

## Dashboard Changes

- Mesh includes `layers.paper_eligibility`.
- Mesh flow includes `paper_eligibility`.
- Readiness includes `paper_eligibility_summary`.
- Dashboard eligibility response includes counts, blockers, missing requirements, safety counters, and `paper_ready=false`.

## Exit Foundation Contract

Preserved from 4C-Q. Exit plans remain risk-derived, non-executing, and blocked/incomplete unless all protective evidence exists.

## Exit Rules

Target/stop/time/invalidation/emergency/liquidity rules are deterministic. Current runtime has no complete exits because all risk decisions are blocked or missing required side/orderbook/risk approval evidence.

## Paper Eligibility Contract

Paper Eligibility reads Exit Foundation truth and persists candidate classifications only. It cannot create Paper intents, order intents, orders, fills, positions, or execution permission.

## Eligibility Rules

Blocked by missing or failed exit, risk, thesis, market, side, orderbook, binding, lineage, dry-run provenance, or unsafe coordinator execution flag. `ELIGIBLE` requires all mandatory evidence and still sets intent/execution allowed false.

## Runtime Verification Results

One-off service run against runtime DB:

- risk decisions checked: 100
- exit plans before/after: 100 -> 100
- exit plans created/updated: 0 / 100
- complete/incomplete/blocked exits: 0 / 0 / 100
- eligibility candidates before/after: 0 -> 100
- candidates created/updated: 100 / 0
- eligible/ineligible/blocked/incomplete: 0 / 0 / 100 / 0
- missing market: 24
- missing orderbook: 100
- missing side: exit side missing 100
- missing binding: 100
- missing risk approval: 100
- dry-run blocked: 0

Runtime API note: `GET /healthz` returned HTTP 200, but the running API process was an older build. New Paper Eligibility routes returned 404 until the runtime API is rebuilt/restarted. I did not restart the runtime process to avoid triggering startup refresh side effects.

## Safety Verification

Runtime DB after service run:

- `paper_eligibility_candidates=100`
- `paper_eligibility_eligible=0`
- `paper_intent_allowed_true=0`
- `eligibility_execution_allowed_true=0`
- `exit_paper_intent_allowed_true=0`
- `exit_execution_allowed_true=0`
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `fills_v2=1` historical row unchanged
- `positions=0`
- `paper_positions=0`

Mesh blocker service:

- `NO_EXIT_FOUNDATION` resolved.
- `NO_PAPER_ELIGIBLE_SIGNALS` remains active.
- `PAPER_ELIGIBILITY_ALL_BLOCKED` active.
- `PAPER_ELIGIBILITY_MISSING_BINDING` active.
- `PAPER_ELIGIBILITY_MISSING_ORDERBOOK` active.
- `EXECUTION_NOT_ALLOWED` active.
- `paper_ready=false`.

## Tests Added

Paper Eligibility contract, repository, service, API, dashboard, and safety tests, plus one QR safety regression for Exit Foundation.

## Tests Run and Exact Results

- Paper Eligibility targeted: `14 passed, 1 warning`
- Exit Foundation targeted + QR safety: `16 passed, 1 warning`
- 4C consolidated regression: `46 passed, 1 warning`
- Risk + thesis regressions: `29 passed, 1 warning`
- Orderbook + market binding regressions: `26 passed, 1 warning`
- Runtime producer + runtime brain regressions: `21 passed, 1 warning`
- Runtime coordinator + mesh regressions: `31 passed, 1 warning`
- Link coverage regressions: `19 passed, 1 warning`
- Signal quality + signal processing regressions: `37 passed, 1 warning`
- Lineage + dry-run provenance + producer health regressions: `50 passed, 1 warning`

Two oversized combined regression commands timed out before returning summaries; the same files were rerun in smaller groups and passed.

## Blockers Resolved

- `NO_EXIT_FOUNDATION`

## Blockers Remaining

- `NO_PAPER_ELIGIBLE_SIGNALS`
- `PAPER_ELIGIBILITY_ALL_BLOCKED`
- `PAPER_ELIGIBILITY_MISSING_BINDING`
- `PAPER_ELIGIBILITY_MISSING_ORDERBOOK`
- `EXIT_PLANS_ALL_BLOCKED`
- `EXIT_MISSING_ORDERBOOK`
- `EXIT_MISSING_RISK_APPROVAL`
- `RISK_DECISIONS_ALL_BLOCKED`
- `RISK_CORE_MISSING_DATA`
- thesis, signal quality, linkage, lineage, freshness, producer, dry-run, env/persisted mismatch, kill-switch mismatch, and `EXECUTION_NOT_ALLOWED` blockers.

## Remaining Risks

The gate is implemented, but current candidates are all blocked. Runtime API must be rebuilt/restarted before HTTP route smoke can pass for the new Paper Eligibility endpoints. No Paper Intent Gate or Paper Execution is implemented.

## Next Recommended Phase

ChatGPT review first. Then either evidence recovery for risk/thesis/orderbook/binding/side, or 4C-S Paper Intent Gate only after eligible candidates exist and the operator explicitly authorizes that phase.

## Final Status

GREEN for the controlled Exit Foundation + Paper Eligibility Gate implementation. Paper itself remains blocked.
