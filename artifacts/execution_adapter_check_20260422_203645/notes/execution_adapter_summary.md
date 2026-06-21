## Execution Adapter Check

- Runtime path: canonical `scripts/migrate_runtime.ps1`, `scripts/start_runtime.ps1`, `scripts/smoke_runtime.ps1`
- Focus: verify the real paper runtime now executes through a canonical execution contract and adapter seam

## Structural Outcome

- `SignalPaperService` now emits a canonical `execution_intent` payload for ranked candidates.
- `ExecutionAwarePaperService` now builds `ExecutionIntent` objects and submits them through a configured `ExecutionAdapter`.
- `PaperExecutionAdapter` handles the current paper execution behavior and returns a canonical `ExecutionResult`.
- `LiveExecutionAdapter` exists as a safe disabled seam and does not submit live orders.

## Real Runtime Proof

- Canonical runtime started successfully and served the dashboard/API surfaces.
- Three spaced runtime samples all returned `200` for:
  - `/dashboard/api/health`
  - `/dashboard/api/kpi-quality`
  - `/dashboard/api/positions-orders`
  - `/dashboard/api/audit`
  - `POST /telegram/command`
- KPI remained live during the run:
  - `paper_orders_created=5`
  - `paper_orders_filled=5`
  - `paper_positions_opened=5`

## Contract Proof

- `api/db_execution_contract_snapshot.json` shows recent real paper orders carrying:
  - `payload_json.execution_contract`
  - `payload_json.execution_result`
- The persisted contract/result include:
  - `backend_target=paper`
  - `execution_mode=paper`
  - `order_type=LIMIT`
  - `result_status=FILLED`
  - `raw_result_json.adapter=paper`

## Alignment Summary

- The runtime paper path now runs through:
  - `ExecutionIntent -> PaperExecutionAdapter -> ExecutionResult`
- Persistence, dashboard, KPI, and audit layers remain unchanged above that seam.
- Future live enablement is now structurally an adapter/config swap rather than a second execution architecture.
