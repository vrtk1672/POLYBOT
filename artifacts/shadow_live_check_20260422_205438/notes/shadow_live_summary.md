## Shadow Live Check

- Runtime path: canonical `scripts/migrate_runtime.ps1`, `scripts/start_runtime.ps1`, `scripts/smoke_runtime.ps1`
- Backend override for this proof: `POLYBOT_EXECUTION_BACKEND=shadow_live`
- Goal: prove the runtime used the real live execution seam in safe shadow mode

## What Changed Operationally

- Shadow runtime now routes approved candidates through the canonical execution contract.
- `LiveExecutionAdapter` in `shadow_live` mode:
  - accepts `ExecutionIntent`
  - builds the real live-style signed order payload
  - returns `ExecutionResult(result_status='WOULD_SUBMIT')`
  - never performs the final external send

## Runtime Proof

- Three time-separated samples all returned `200` for:
  - `/dashboard/api/health`
  - `/dashboard/api/kpi-quality`
  - `/dashboard/api/positions-orders`
  - `/dashboard/api/audit`
  - `POST /telegram/command`
- Shadow activity grew during the run:
  - sample 1: `shadow_orders_count=4`, `shadow_positions_count=4`
  - sample 2: `shadow_orders_count=5`, `shadow_positions_count=5`
  - sample 3: `shadow_orders_count=6`, `shadow_positions_count=6`

## Truthful Shadow Evidence

- `api/db_after.json` shows recent `shadow_orders` carrying:
  - `raw_intent_json.execution_contract`
  - `raw_policy_json.execution_result`
  - `raw_policy_json.execution_result.raw_result_json.live_request_payload`
- This proves shadow built the real live-style request payload and persisted it for inspection.

## No External Send Proof

- `live_orders` count stayed unchanged:
  - before: `0`
  - after: `0`
- Shadow rows increased:
  - `shadow_orders: 0 -> 6`
  - `shadow_positions: 0 -> 6`
- The persisted `ExecutionResult` shows:
  - `result_status='WOULD_SUBMIT'`
  - `external_order_id=null`
  - `raw_result_json.shadow_mode=true`

## Why This Is True Shadow

- The runtime did not reuse the paper adapter.
- The runtime did not stop at pretty log messages.
- The runtime reached the live adapter seam, built the real request body, persisted the would-submit truth, and stopped exactly before external submission.
