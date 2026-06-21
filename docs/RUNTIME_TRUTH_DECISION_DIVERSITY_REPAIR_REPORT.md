# POLYBOT Runtime Truth + Decision Diversity Repair Report

## 1. Purpose

Repair the two remaining blockers after the unified PAPER runtime execution-chain repair:

- Runtime health was showing stale unfinished cycle rows as active/current truth.
- PAPER runtime decisions were over-concentrated in one market/side group.

This remains one unified autonomous runtime. PAPER is only the execution adapter.

## 2. Current State Before Repair

Before this repair:

- `/runtime/health` could expose an old unfinished `runtime_cycles_v2` row as `active_cycle`.
- System overview did not distinguish current active cycles from stale abandoned history.
- Current PAPER decision rows contained many repeated `691547 YES` rows.
- Duplicate protection worked, but too late in the chain.

## 3. Runtime Stale Cycle Root Cause

Runtime cycles are stored in `runtime_cycles_v2`.

An active cycle was defined as `finished_at IS NULL`, so old `RUNNING` rows from prior process/runtime interruptions were selected as current even after `SYSTEM OFF`.

There was no cleanup step to classify TTL-expired `RUNNING` cycles as abandoned, and `SYSTEM OFF` did not mark remaining open cycle rows as stopped.

## 4. Runtime Truth Repair

Implemented in `RuntimeCycleRepository`:

- `mark_stale_abandoned()`: marks TTL-expired open cycles as `STALE_ABANDONED`.
- `mark_open_cycles_safe_stopped()`: marks remaining open cycles as `SAFE_STOPPED`.
- Duration is capped to fit the existing integer `duration_ms` column.

Wired into:

- `HealthTruthService`
- `RuntimeReadinessService`
- `ControlCenterActionService` system-off path

Runtime health now reports:

- `active_cycle: null` after system off
- `runtime_state: STOPPED`
- historical stale rows counted separately

No runtime cycle history is deleted.

## 5. Decision Concentration Root Cause

Current PAPER_OBSERVATION policy rows are heavily concentrated in one market/side:

- `market_id=691547`
- `side=YES`

The prior decision refresh read raw rows by score, so repeated source/seed lineage for the same market/side filled the current decision batch.

Duplicate guards were correct, but they fired late:

- `SAME_MARKET_DUPLICATE_DECISION`
- `DUPLICATE_OPEN_PAPER_EXPOSURE`

## 6. Diversity Repair

Implemented best-per-market-side selection in `PaperRuntimeDecisionService`:

- Group source rows by `market_id + side`.
- Select best row per market/side first.
- Rank selected groups by deterministic `diversity_score`.
- Track `duplicate_suppressed_count`.
- Mark only the latest refresh rows as `is_current_batch=true`.
- Keep historical decision rows, but current runtime/intent gate reads only current batch rows.

Diversity score uses:

- opportunity score
- research priority band
- research priority score
- trigger metadata presence
- side diversity nudge

This does not override hard safety gates.

## 7. Duplicate Safety Preserved

Preserved:

- Same market/side duplicate decision guard.
- Duplicate open paper exposure guard.
- Duplicate active paper intent guard.
- Token/orderbook/lineage/exit/risk/capital blockers.

The repair suppresses duplicate row spam before the gate; it does not allow multiple same-market/side exposure.

## 8. System Overview / CLI Changes

System overview now exposes:

- `runtime_truth.current_active_cycle_id`
- `runtime_truth.latest_completed_cycle_id`
- `runtime_truth.stale_abandoned_cycles_count`
- current-batch paper decision counts
- unique market count
- unique side count
- unique market/side count
- duplicate suppression count
- concentration score
- top unique runtime decisions
- duplicate market/side diagnostics
- trigger family counts

`tools/polybot.ps1 status/report` now shows:

- current active cycle
- latest completed cycle
- stale abandoned cycles
- decision unique markets/sides
- duplicate suppression count
- concentration score
- top unique decisions in full report

## 9. Tests Run

Focused:

`.venv\Scripts\python.exe -m pytest tests/test_runtime_health_truth.py tests/test_runtime_cycle_cleanup.py tests/test_paper_decision_diversity.py tests/test_paper_duplicate_concentration_diagnostics.py tests/test_system_overview_runtime_truth_diversity.py -q`

Result: `4 passed, 9 skipped in 2.68s`.

Related:

`.venv\Scripts\python.exe -m pytest tests/test_paper_runtime_execution_chain.py tests/test_paper_mode_supervisor_governor.py tests/test_paper_decision_to_intent_gate.py tests/test_paper_execution_adapter_runtime.py tests/test_system_overview_paper_chain.py -q`

Result: `3 passed, 6 skipped in 2.58s`.

Broad:

`.venv\Scripts\python.exe -m pytest tests -q -k "runtime_health or runtime_cycle or decision_diversity or duplicate_concentration or paper_runtime or system_overview or paper_adapter"`

Result: `10 passed, 24 skipped, 2273 deselected in 6.98s`.

Compile:

`.venv\Scripts\python.exe -m compileall app tests`

Result: passed.

## 10. Controlled PAPER Runtime Verification

Before:

- Active cycles: `0`
- Stale abandoned cycles: `26`
- Current PAPER runtime decisions: `1`
- Unique markets: `1`
- Unique market/side pairs: `1`
- ENTER decisions: `0`
- Duplicate suppressed: `72`
- Paper intents/orders/fills/positions: `22/13/10/13`
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

- Active cycles: `0`
- Stale abandoned cycles: `26`
- Safe stopped cycles: `1`
- Current PAPER runtime decisions: `1`
- Unique markets: `1`
- Unique sides: `1`
- Unique market/side pairs: `1`
- ENTER decisions: `0`
- Duplicate suppressed: `72`
- Paper intents/orders/fills/positions: `22/13/10/13`
- Open paper positions: `0`
- Live orders: `0`
- Shadow orders: `0`

## 11. What Moved During Runtime

Runtime activity moved:

- Recent events increased: `1390 -> 1531`
- Linked events increased: `910 -> 951`
- Triggers increased: `70 -> 71`
- Proactive seeds increased: `1025 -> 1031`
- Mesh reviewed increased: `292 -> 302`
- Memory HIGH markets increased: `990 -> 994`

No new paper entry occurred because the only current unique decision was blocked by `STALE_ORDERBOOK`.

## 12. Paper Ledger Result

Paper ledger counts did not change during this repair verification:

- Paper intents: `22 -> 22`
- Paper orders: `13 -> 13`
- Paper fills: `10 -> 10`
- Paper positions: `13 -> 13`
- Open paper positions: `0 -> 0`

This is expected: duplicate concentration is now suppressed upstream and the remaining unique row needs fresh orderbook before PAPER entry.

## 13. Live/Shadow Safety Result

- Live orders: `0 -> 0`
- Shadow orders: `0 -> 0`
- Existing `orders_v2` count remained unchanged.
- LIVE adapter stayed blocked.
- Shadow stayed disabled.

## 14. Remaining Blockers

1. Production PAPER_OBSERVATION policy rows currently contain only one unique market/side after grouping.
2. The remaining unique decision is blocked by `STALE_ORDERBOOK`.
3. Broader autonomous PAPER decisions require either fresh orderbook refresh for `691547 YES` or more diverse PAPER_OBSERVATION policy rows from upstream Mesh/trigger coverage.

## 15. Status

Runtime truth repair: `GREEN`.

Decision diversity selection repair: `GREEN` for selection/diagnostics, `YELLOW` for production diversity because current source data still only has one unique PAPER_OBSERVATION market/side.

Overall autonomous PAPER mode: `PARTIAL`.

## 16. Recommended Next Action

Repair the targeted orderbook refresh path for current PAPER_OBSERVATION decisions, then broaden upstream Mesh-reviewed policy coverage across more markets/sides/triggers.
