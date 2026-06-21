# POLYBOT Paper Runtime Execution Chain Repair Report

## 1. Purpose

Repair the missing unified PAPER runtime execution chain:

`paper-capable decision -> PaperIntentGate -> PaperExecutionAdapter -> paper order -> paper fill -> paper position -> paper PnL`

This repair keeps POLYBOT as one autonomous trading system. PAPER is only the current execution adapter. LIVE remains blocked.

## 2. Correct Architecture Vision

The correct model is:

`candidate/opportunity -> unified decision engine -> ENTER/WATCH/BLOCK/EXIT -> execution adapter`

Adapters:

- `PAPER`: simulated execution and Postgres paper ledger.
- `LIVE`: future real order adapter, blocked in this stage.
- `DISABLED`: system off.

Paper mode must not create a separate trading brain. It uses the same market, source, trigger, Mesh, score, risk, capital, exit, and lifecycle truth, then routes approved decisions through the PAPER adapter only.

## 3. Internal Questions And Answers

1. `polybot.ps1 on -mode paper` previously stored paper intent in control metadata and `paper_simulation.enabled`, but the governor remained effectively `DATA_ONLY`.
2. The supervisor saw `DATA_ONLY` semantics because control startup forced safe monitoring mode.
3. The governor did not treat PAPER as first-class for supervisor execution hooks.
4. Paper hooks were controlled by supervisor paper cycle checks and `PaperSimulationControlService`.
5. Runtime reported DATA_ONLY because `ControlCenterActionService._ensure_safe_monitoring_mode()` forced `RuntimeMode.DATA_ONLY`.
6. Mesh-reviewed PAPER_OBSERVATION rows are stored mainly in `proactive_seed_mesh_results` and Stage 7 policy rows in `paper_observation_policy_reviews`.
7. They were not converted into canonical runtime decisions.
8. No unified ENTER/WATCH/BLOCK table existed for this path.
9. Closest previous objects were `paper_observation_policy_reviews` and legacy `paper_eligibility_candidates`.
10. PaperIntentGate should consume unified PAPER runtime decisions derived from policy-reviewed Mesh results.
11. PaperIntentGate ran during supervisor cycles only when paper mode was enabled.
12. It only consumed legacy paper eligibility candidates.
13. It rejected old rows using strict paper actionability/lifecycle checks.
14. The top Stage 7 rows were blocked because they never reached the intent gate as PAPER runtime decisions.
15. The legacy path effectively required Full Paper-style strictness.
16. It ignored PAPER learning decisions from proactive seed Mesh results.
17. It ignored proactive seed Mesh outputs except through older eligibility surfaces.
18. The paper adapter exists as `PaperExecutionService`.
19. The adapter is located at the execution boundary after paper intents.
20. It was reachable only after a paper intent existed.
21. It requires canonical `paper_intents` with market, side, intended price, quantity, orderbook snapshot, and safe flags.
22. It can simulate order, fill, and position creation.
23. It writes paper orders, fills, positions, and PnL/ledger state.
24. New candidates were blocked by not being bridged from `DATA_ONLY_RESEARCH` lineage into PAPER mode.
25. `DATA_ONLY_RESEARCH` should block LIVE, but may enter PAPER through the PAPER adapter with warnings when minimum truth is present.
26. PAPER vs LIVE is separated by governor mode, adapter state, `paper_only=true`, `live=false`, and `execution_allowed=false`.
27. LIVE remains blocked by mode permissions, false execution flags, and no live adapter routing.
28. Paper chain status belongs in system overview and CLI report.
29. System overview now exposes paper runtime decisions and top blockers.
30. CLI report now shows the paper execution chain.

## 4. Previous State

The broader runtime was moving:

- Markets: about 1,004 in memory.
- Events, triggers, proactive seeds, and Mesh reviews increased under SYSTEM ON.
- LIVE and SHADOW stayed blocked.

But no new paper intents, orders, fills, or positions were created because the paper-capable Mesh/policy rows were not mapped into the intent gate.

## 5. Root Cause Analysis

Root cause:

1. PAPER mode was mostly metadata around a DATA_ONLY runtime.
2. The supervisor start path forced DATA_ONLY and did not make PAPER mode first-class.
3. Stage 7 policy-reviewed PAPER_OBSERVATION rows had no canonical runtime decision bridge.
4. `PaperIntentGate` consumed legacy `paper_eligibility_candidates`, not proactive seed Mesh policy rows.
5. Runtime-decision candidates were still treated as DATA_ONLY research and did not receive PAPER-mode learning policy.
6. Paper execution adapter was present, but starved of valid runtime-generated paper intents.

## 6. Top 20 Candidate Blocker Audit

The top paper-capable rows were concentrated in market `691547`, side `YES`, token verified, orderbook fresh, candidate scoped, lineage complete, score about `61.99`.

Common states:

- Edge: `EDGE_SUPPORTED`
- Thesis: `THESIS_SUPPORTED`
- Risk: `RISK_OK`
- Capital: `CAPITAL_WATCH`
- Exit: `EXIT_READY`
- Lifecycle: `DATA_ONLY_RESEARCH`
- Policy: `OBSERVATION_POLICY_ELIGIBLE`
- Decision band: `PAPER_OBSERVATION`
- Hard blockers: none on the best row
- Soft blockers: `capital_watch_not_full_paper_ready`, `reward_evidence_weak_or_missing`

Before repair, exact blocker was architectural: `PAPER_OBSERVATION_POLICY_ROW_NOT_BRIDGED_TO_PAPER_INTENT_GATE`.

After repair, one row became `ENTER`; duplicate rows for the same market/side were blocked by:

- `SAME_MARKET_DUPLICATE_DECISION`
- `DUPLICATE_OPEN_PAPER_EXPOSURE`

## 7. Fixes Made

- Added canonical `paper_runtime_decisions`.
- Added `PaperRuntimeDecisionService`.
- Made PAPER mode first-class in control and supervisor paths.
- Allowed PaperIntentGate to consume unified PAPER runtime decisions.
- Added PAPER-mode policy that permits learning decisions with warnings for `CAPITAL_WATCH` or `DATA_ONLY_RESEARCH`, while preserving hard blockers.
- Kept LIVE disabled and all runtime paper decisions non-live.
- Allowed runtime paper intents through the existing paper execution adapter without legacy Full Paper lifecycle authorization.
- Added system overview and CLI visibility for paper runtime decisions and blockers.

## 8. Execution Mode Changes

`ControlCenterActionService` and `PaperSimulationControlService` now preserve requested `execution_mode=PAPER` and transition governor/runtime state to `RuntimeMode.PAPER`.

`RuntimeSupervisorService` now allows `DATA_ONLY` and `PAPER`, records runtime mode in cycle metadata, and marks paper hooks active only when PAPER adapter mode is enabled and system power is ON.

## 9. Supervisor/Governor PAPER Mode Result

Controlled runtime showed:

- System ON accepted.
- Runtime state `PAPER`.
- Execution mode `PAPER`.
- Paper adapter `ENABLED`.
- Live adapter `BLOCKED`.
- Supervisor `RUNNING`.

After SYSTEM OFF:

- System power `OFF`.
- Runtime state `DATA_ONLY`.
- Execution mode `DISABLED`.
- Paper adapter `DISABLED`.
- Live adapter `BLOCKED`.
- Supervisor `STOPPED`.

Residual observability note: `/runtime/health` still shows one stale active cycle row from an older `market_service.refresh` cycle. The last successful supervisor cycle completed and paper hooks stopped.

## 10. Unified Decision Object / Mapping

New canonical decision record:

- `decision_id`
- `candidate_source`
- `source_review_id`
- `proactive_candidate_seed_id`
- `seed_mesh_inquiry_id`
- `adapter_payload_id`
- `market_id`
- `condition_id`
- `side`
- `token_id`
- `decision`
- `decision_mode`
- `execution_mode`
- Edge/thesis/score/risk/capital/exit/lifecycle states
- orderbook/token/scope/lineage states
- warnings, blockers, required-to-pass
- `paper_enter_allowed`
- `live_enter_allowed=false`

## 11. PaperIntentGate Result

PaperIntentGate now:

- Refreshes PAPER runtime decisions.
- Prepends PAPER runtime decisions to legacy candidates.
- Allows PAPER-enter decisions that pass minimum truth.
- Records exact blockers for hard-blocked decisions.
- Does not require Full Paper certification for PAPER learning mode.
- Does not create live orders.

## 12. PaperExecutionAdapter Result

PaperExecutionService now recognizes runtime-decision intents and uses PAPER execution governance:

- Requires system power ON.
- Requires PAPER adapter enabled.
- Requires intent status created.
- Requires fresh enough orderbook and duplicate exposure checks.
- Preserves `paper_only=true`, `live=false`, `execution_allowed=false`.
- Creates only paper order/fill/position rows.

## 13. Position/PnL Result

Controlled runtime created and then closed one paper position:

- Market: `691547`
- Side: `YES`
- Entry price: `0.390000`
- Quantity: `10.000000`
- Position status after exit management: `CLOSED`
- Latest daily PnL row for 2026-06-18: realized/net `-0.60000000`

## 14. System Overview / Terminal Report Result

Updated:

- `GET /dashboard/api/v2/control/system-overview`
- `tools/polybot.ps1 status`
- `tools/polybot.ps1 report`

The CLI report now shows:

- Runtime PAPER decisions
- Paper-enter decisions
- Top blockers
- Top runtime decisions
- Paper intents/orders/fills/positions
- Open paper positions
- Live/shadow/real order counts

CLI HTTP timeout was increased to 120 seconds for active-runtime reports.

## 15. Tests Run

Focused:

`.venv\Scripts\python.exe -m pytest tests/test_paper_runtime_execution_chain.py tests/test_paper_mode_supervisor_governor.py tests/test_paper_decision_to_intent_gate.py tests/test_paper_execution_adapter_runtime.py tests/test_system_overview_paper_chain.py -q`

Result: `9 passed in 245.86s`.

Related:

`.venv\Scripts\python.exe -m pytest tests/test_unified_runtime_audit.py tests/test_execution_mode_paper_adapter.py tests/test_paper_intent_gate_hard_boundary.py tests/test_paper_actionability_strict_qualification.py tests/test_paper_observation_policy_review.py -q`

Result: `18 passed in 20.62s`.

Broad:

`.venv\Scripts\python.exe -m pytest tests -q -k "paper_runtime or paper_mode or paper_adapter or paper_intent or system_overview or runtime or supervisor or governor or execution_mode"`

Result: timed out after about 604 seconds before reporting final pass/fail.

Compile:

`.venv\Scripts\python.exe -m compileall app tests`

Result: passed.

## 16. Controlled Runtime Verification

Before:

- Paper runtime decisions: `0`
- Paper intents: `21`
- Paper orders: `12`
- Paper fills: `9`
- Paper positions: `12`
- Open paper positions: `0`
- Live orders: `0`
- Shadow orders: `0`

Action:

1. `.\tools\polybot.ps1 status`
2. `.\tools\polybot.ps1 on -mode paper -interval 30`
3. Waited multiple supervisor cycles.
4. `.\tools\polybot.ps1 report`
5. `.\tools\polybot.ps1 off`

After:

- Paper runtime decisions: `73`
- Paper-enter decisions: `1`
- Blocked runtime decisions: `72`
- Paper intents: `22`
- Paper orders: `13`
- Paper fills: `10`
- Paper positions: `13`
- Open paper positions: `0`
- Paper daily PnL rows: `7`
- Live orders: `0`
- Shadow orders: `0`

The normal supervisor cycle produced:

- `paper_intents_created=1`
- `orders_created=1`
- `fills_created=1`
- `positions_created=1`

No fake trades were inserted.

## 17. Paper Ledger Counts

Before/after:

- Paper intents: `21 -> 22`
- Paper orders: `12 -> 13`
- Paper fills: `9 -> 10`
- Paper positions: `12 -> 13`
- Open paper positions: `0 -> 0` after exit management closed the new position.

## 18. Live/Shadow Safety Result

- Live orders: `0 -> 0`
- Shadow orders: `0 -> 0`
- Existing `orders_v2` count remained unchanged at `1`.
- LIVE adapter stayed blocked.
- SHADOW stayed disabled.

## 19. Remaining Blockers

1. Candidate supply is currently concentrated around repeated market `691547` YES rows, so most runtime decisions are duplicate/exposure blocks.
2. `/runtime/health` still reports a stale active cycle row from an older `market_service.refresh` cycle even though supervisor is stopped and last successful supervisor cycle completed.
3. Later PAPER-mode policy can be tuned to broaden eligible decisions, but this repair intentionally did not loosen risk/capital/exit/lifecycle hard gates.

## 20. Status

Execution-chain repair status: `GREEN`.

Overall autonomous PAPER runtime status: `PARTIAL` until stale-cycle observability and duplicate candidate concentration are cleaned up.

## 21. Recommended Next Action

Clean up stale active cycle truth in runtime health, then broaden decision diversity by reducing duplicate proactive seed rows per market/side before PaperIntentGate.
