# V2.20A Build Report - Neural Mesh Readiness Audit

## Summary

V2.20A completed an audit-only readiness pass. POLYBOT was evaluated as a neural mesh across nodes, edges, AI/model readiness, data sources, runtime readiness, dashboard truth, and tests.

No trading features were added. No live trading was enabled. No orders, order intents, live exits, or external balance mutations were added.

## Files Created

- `app/tools/v2_20a_neural_mesh_audit.py`
- `scripts/audit_v2_20_neural_mesh.ps1`
- `scripts/verify_v2_20_ai_models.ps1`
- `scripts/verify_v2_20_mesh_edges.ps1`
- `scripts/verify_v2_20_runtime_readiness.ps1`
- `tests/test_v2_20a_neural_mesh_readiness.py`
- `docs/V2_20A_NEURAL_MESH_READINESS_AUDIT.md`
- `docs/V2_20A_BUILD_REPORT.md`

## Files Changed

- `app/tools/v2_20a_neural_mesh_audit.py` was corrected to read SQL migrations and use actual repo schema names.
- `docs/POLYBOT_CONTEXT_INDEX.md` was updated with V2.20A status.

## Scripts Created

- `audit_v2_20_neural_mesh.ps1`
- `verify_v2_20_ai_models.ps1`
- `verify_v2_20_mesh_edges.ps1`
- `verify_v2_20_runtime_readiness.ps1`

Existing V2.20 verification scripts remain available:

- `verify_v2_20_dashboard_truth.ps1`
- `verify_v2_20_no_live_mutation.ps1`

## Tests Run

Targeted V2.20A:

```powershell
python -m uv run pytest tests/test_v2_20a_neural_mesh_readiness.py -q
```

Result: `4 passed in 13.67s`.

Runtime regression:

```powershell
$files = Get-ChildItem tests\test_runtime_*.py | ForEach-Object { $_.FullName }; python -m uv run pytest $files -q
```

Result: `8 passed, 19 skipped in 21.41s`.

V2.19 regression:

```powershell
$files = Get-ChildItem tests\test_v2_19_*.py | ForEach-Object { $_.FullName }; python -m uv run pytest $files -q
```

Result: `21 passed, 8 skipped in 36.21s`.

V2.18 regression:

```powershell
$files = Get-ChildItem tests\test_v2_18_*.py | ForEach-Object { $_.FullName }; python -m uv run pytest $files -q
```

Result: `5 passed, 3 skipped in 15.85s`.

## Audit Scripts Run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\audit_v2_20_neural_mesh.ps1
```

Result: generated `run_reports\v2_20a\neural_mesh_readiness_audit.json` with 24 nodes and 20 edges.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_v2_20_ai_models.ps1
```

Result: Ollama missing, local models not detectable, `ANTHROPIC_API_KEY` absent, fallback behavior documented.

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; $env:PHASE1_PERSISTENCE_ENABLED='true'; powershell -ExecutionPolicy Bypass -File .\scripts\verify_v2_20_runtime_readiness.ps1
```

Result: Postgres OK, migrations applied count 57, Docker check timed out, runtime scripts present.

## Runtime Checks

Migration command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1
```

Result: `No pending migrations.`

Runtime startup attempt:

- Started direct hidden runtime process with live disabled and DATA_ONLY environment.
- Runtime reported `STARTED 3812`.
- Endpoint checks then timed out for `/healthz`, `/runtime/state`, `/runtime/health`, `/dashboard/api/v2/overview`, `/dashboard/api/v2/learning`, `/ai/health`, `/events/lag`, `/risk/health`, `/execution/health`, `/exits/health`, `/no-trade/health`.
- Temporary runtime process was stopped.

This is a HIGH blocker for V2.20 long-run readiness.

## Node Matrix Summary

- Static nodes audited: 24.
- Static result: 24 GREEN after schema-name correction.
- Runtime caveat: runtime health could not be verified because endpoints timed out.

## Edge Matrix Summary

- Major mesh edges audited: 20.
- Static result: 20 CONNECTED.
- Runtime caveat: actual data movement still needs smoke evidence.

## AI / Model Readiness Summary

- Expected local models: `qwen3:8b`, `qwen3:14b`, `deepseek-r1:14b`.
- `ollama`: missing.
- Installed local models: none detectable.
- `ANTHROPIC_API_KEY`: absent.
- Hybrid AI fallback exists; legacy/lite Anthropic paths may fail if invoked without key.

## Data Source Readiness Summary

- Market/orderbook/news/social/whale freshness: unknown until runtime health is stable.
- Rules source: static code/schema present.
- AI source: partial; can degrade but full AI run is not ready without models/key decision.

## Runtime Readiness Summary

- Postgres: OK when env is set.
- Migrations: current.
- Docker: timed out.
- Runtime endpoints: timed out after startup.
- Redis: not detected/not required.

## Dashboard Truth Summary

- Dashboard V2 routes exist and V2.18 tests pass.
- Runtime dashboard truth could not be verified because dashboard endpoints timed out.
- No mock-data acceptance path was added.

## Blockers

Critical: none in static safety surfaces.

High:

- Runtime endpoint responsiveness after startup.
- Missing local AI runtime/models if full AI mesh is required.
- Data/orderbook freshness unknown until runtime starts cleanly.

Medium:

- Docker readiness unclear.
- Dashboard runtime truth not verified.
- Static mesh edges need row/event evidence.
- Legacy paper-position exit-plan linkage remains partial.

Low:

- PowerShell wildcard issue for pytest.

## Recommended Fix Order

1. Capture runtime startup logs and fix endpoint timeout.
2. Re-run runtime readiness with `/healthz`, `/runtime/state`, dashboard, and module health endpoints.
3. Decide AI mode: install local models or explicitly run degraded no-AI smoke.
4. Verify market/orderbook/news/social/whale source freshness.
5. Run 30m DATA_ONLY smoke.
6. Run 30m PAPER smoke.
7. Continue to 24h/72h/7d staged runs only after smoke is clean.

## Phase Status

YELLOW.

The audit completed and produced clear blockers. It is safe to proceed to V2.20B fixes, not to V2.20 long-run execution.
