# POLYBOT Green Baseline

## Meaning

This baseline freezes the verified GREEN state for POLYBOT phases 1 through 9.

Validated state:
- Phase 4B regression scope: `8 passed`
- Phase 4 band: `23 passed`
- Full regression phases 1 through 9: `226 passed`
- Runtime startup succeeded
- `/docs` reachable
- `/openapi.json` reachable
- `/dashboard` reachable
- `/dashboard/api/health` reachable
- `/dashboard/api/overview` reachable
- `/dashboard/api/ranking` reachable
- `POST /telegram/command` reachable

## Runtime Summary

- Dashboard URL: `http://127.0.0.1:8000/dashboard`
- Docs URL: `http://127.0.0.1:8000/docs`
- OpenAPI URL: `http://127.0.0.1:8000/openapi.json`
- API base URL: `http://127.0.0.1:8000`
- DB target used during validation: `postgresql://polybot:polybot@127.0.0.1:55432/polybot`
- DB access method: local Docker Postgres container `polybot_phase1_pg`

## Required Environment

- `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
- `PHASE1_PERSISTENCE_ENABLED=true`
- `DATABASE_URL` removed or unset to avoid drift

## Commands

Migration command:

```powershell
python -m uv run app/db/migrate.py
```

Startup command:

```powershell
python -m uv run polybot
```

Phase 4B proof command:

```powershell
python -m uv run pytest tests\test_phase4b_external_event_enrichment.py -q
```

Phase 4 band proof command:

```powershell
python -m uv run pytest tests\test_phase4a_external_intelligence.py tests\test_phase4b_external_event_enrichment.py tests\test_phase4c_external_to_cognition_handoff.py -q
```

Full regression command:

```powershell
python -m uv run pytest tests\test_phase1_cycle_replay.py tests\test_phase1_execution_memory.py tests\test_phase1_closeout.py tests\test_phase2_signal_paper.py tests\test_phase2_execution_aware_paper.py tests\test_phase2_shadow_live.py tests\test_phase3_event_interpreter.py tests\test_phase3b_market_link_candidates.py tests\test_phase3c_resolution_analyzer_lite.py tests\test_phase3d_invalidation_reasoning_lite.py tests\test_phase3e_cognition_summary.py tests\test_phase4a_external_intelligence.py tests\test_phase4b_external_event_enrichment.py tests\test_phase4c_external_to_cognition_handoff.py tests\test_phase5a_whale_scanner.py tests\test_phase5b_whale_profiling.py tests\test_phase5c_whale_categories.py tests\test_phase5d_whale_scoring.py tests\test_phase6a_trade_classification.py tests\test_phase6b_bucket_allocation.py tests\test_phase7a_ranking_v2.py tests\test_phase7b_ranking_policy.py tests\test_phase8a_invalidation_exit_policy.py tests\test_phase8b_exit_advisory.py tests\test_phase8c_advisory_resolution.py tests\test_phase8d_command_intent_staging.py tests\test_phase9_dashboard_telegram.py -q
```

## Evidence

- Test logs: `artifacts/green_closeout_20260422_131820/logs`
- API snapshots: `artifacts/green_closeout_20260422_131820/api`
- Visual snapshots: `artifacts/green_closeout_20260422_131820/screenshots`
- Runtime note: `artifacts/green_closeout_20260422_131820/notes/green_baseline.md`
