# POLYBOT Risk Evidence Mesh + Source-Backed Edge Calibration Build Report

Date: 2026-06-05

Security governance status: `YELLOW_ACCEPTED_BY_OPERATOR`

## Current Reality Found

The latest trade-focused forensic run completed safely but opened no Paper trades. The main blockers were `RISK_BLOCKED`, `RISK_BLOCKED_LINEAGE`, `RISK_BLOCKED_NO_EDGE`, and `STALE_ORDERBOOK`.

Runtime DB inspection before this phase showed:

- `risk_decisions`: 11,572
- `risk_decisions` with `decision='BLOCK'`: 11,224
- no-edge/thesis-like blockers: 11,222
- stale or missing fresh orderbook blockers: 8,672
- `MISSING_MARKET_LINK`: 9,779
- `MISSING_SIGNAL_MARKET_BINDING`: 7,223
- lifecycle plans with risk summary `BLOCK`: 5,544
- lifecycle plans missing fair probability: 9,111
- lifecycle plans missing whale context: 9,211
- lifecycle plans missing memory context: 9,211

Risk Core did not consume payout/odds, exit-hold, capital efficiency, truth state, or lifecycle plans as evidence-quality inputs. It treated thesis/profile chain completeness as the dominant decision source.

## Root Cause Fixed

Risk was acting as a linear chain-completeness checker:

`source -> signal -> market link -> candidate -> thesis -> risk`

The new layer lets Risk distinguish:

- critical missing/stale evidence
- partial but non-critical lineage
- optional missing context
- weak source-backed edge
- no source-backed edge

## Files Created

- `app/db/migrations/0127_risk_evidence_mesh_edge_calibration.sql`
- `app/services/risk_evidence_mesh.py`
- `tests/test_risk_evidence_mesh.py`
- `docs/POLYBOT_RISK_EVIDENCE_MESH_EDGE_CALIBRATION.md`
- `docs/POLYBOT_RISK_EVIDENCE_MESH_EDGE_CALIBRATION_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/lifecycle_governance.py`
- `app/services/trade_lifecycle.py`
- `app/services/paper_trade_forensics.py`

## DB Migration

Added migration `0127_risk_evidence_mesh_edge_calibration.sql`.

Tables:

- `risk_evidence_mesh_evaluations`
- `risk_evidence_mesh_sources`

The migration was applied to runtime Postgres with `psql` because the runtime migrate image was stale and reported no pending migrations. The migration was marked in `schema_migrations`.

## Integrations

Risk Evidence Mesh:

- evaluates lifecycle plans and supported subjects
- records source refs and truth states where available
- exposes dashboard summary/detail
- exposes bounded evaluation endpoint
- appears in Trade Lifecycle risk summaries
- appears in Paper Trade Forensics
- appears in Brain Dialogue as source-backed risk evidence events
- informs Lifecycle Governance

Lifecycle Governance:

- treats `RISK_BLOCK` from Risk Evidence Mesh as hard block
- treats `RISK_WATCH` / `RISK_REVIEW` as non-hard risk states
- preserves legacy hard-block behavior when no Risk Evidence Mesh record exists

## Tests

Targeted new tests:

`powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1 tests/test_risk_evidence_mesh.py -q`

Result:

- 13 passed
- 1 warning

Adjacent regressions:

`powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1 tests/test_lifecycle_governance.py tests/test_trade_lifecycle.py tests/test_paper_execution_service.py -q`

Result:

- 31 passed
- 1 warning

Truth / same-market / no-live regressions:

`powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1 tests/test_truth_state_service.py tests/test_same_market_side_guard.py tests/test_paper_no_live_safety.py -q`

Result:

- 23 passed
- 1 warning

Risk evidence + dialogue regression after dialogue materializer:

`powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1 tests/test_risk_evidence_mesh.py tests/test_brain_dialogue_on_off_safety.py -q`

Result:

- 15 passed
- 1 warning

Host venv test attempt:

`.venv\Scripts\python.exe -m pytest tests/test_risk_evidence_mesh.py -q`

Result:

- 13 skipped because local test DB fixture was unavailable.

## Runtime Smoke

No runtime run was started. SYSTEM remained OFF.

Bounded derived evaluation:

- evaluated 25 recent lifecycle plans
- created 25 `risk_evidence_mesh_evaluations`
- created source rows
- no trading mutation

Smoke output:

- `RISK_BLOCK`: 25
- `RISK_SUPPORT`: 0
- `RISK_WATCH`: 0
- `RISK_REVIEW`: 0
- blocker subtype: `RISK_BLOCKED_STALE_CRITICAL_SOURCE`: 25
- edge source type: `UNKNOWN`: 25
- dashboard summary returned `mock_data=false`

Safety counts remained unchanged:

- `paper_intents`: 20 -> 20
- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12
- `paper_position_closes`: 9 -> 9
- `paper_capital_ledger`: 38 -> 38
- `live_orders`: 0 -> 0
- `orders_v2`: 1 -> 1
- `fills_v2`: 1 -> 1
- canonical `positions`: 0 -> 0

Capital remained unchanged:

- current balance: 996.819322
- available balance: 996.819322
- locked balance: 0
- open exposure: 0
- realized PnL: -3.180678
- unrealized PnL: 0

## Samples

Critical block sample:

- subject: lifecycle plan for market `597964`, side `YES`
- risk decision: `RISK_BLOCK`
- subtype: `RISK_BLOCKED_STALE_CRITICAL_SOURCE`
- critical missing: `TRUSTED_ORDERBOOK_STALE`
- optional missing: `FAIR_PROBABILITY_MISSING`, `MEMORY_CONTEXT_MISSING`, `WHALE_CONTEXT_MISSING`

Optional missing not hard-blocking sample:

- covered by test `test_optional_whale_memory_and_fair_probability_do_not_hard_block`
- fresh orderbook + payout + capital evidence remained non-blocking despite missing whale, memory, and fair probability

Weak/source-backed edge review sample:

- covered by test `test_payout_liquidity_capital_setup_creates_review_without_fake_fair_probability`
- payout/liquidity/capital setup produced `RISK_REVIEW` with `CAPITAL_EFFICIENCY_SETUP`
- `no_fake_probability=true`

## Remaining Risks

- Current production sampled plans still have stale critical orderbook data.
- Runtime API container may need a normal rebuild/redeploy before the new route is available through the live FastAPI process.
- The model does not yet create actionability; it only prevents optional context from becoming a hard Risk block.

## Phase Status

GREEN for implementation and tests.

YELLOW operationally until a fresh runtime cycle creates current orderbook evidence and Risk Evidence Mesh can classify non-stale subjects.

Can run trade-focused 10m validation: YES, after rebuilding/redeploying the runtime API image so the new service/routes are active.
