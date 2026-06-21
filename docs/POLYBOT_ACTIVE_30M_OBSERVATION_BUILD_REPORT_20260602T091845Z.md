# POLYBOT Active 30m Observation Build Report

- run_id: active_30m_observation_20260602T091845Z
- status: GREEN
- executor: Codex
- task_mode: CONTROLLED_RUNTIME_RUN + FULL_SYSTEM_ON + PAPER_SAFE_INTELLIGENCE_RUN
- started_at_utc: 2026-06-02T09:18:45.199898+00:00
- finished_at_utc: 2026-06-02T09:48:49.837301+00:00
- samples: 9
- report: docs/POLYBOT_ACTIVE_30M_OBSERVATION_REPORT_20260602T091845Z.md
- log: logs/observation/active_30m_observation_20260602T091845Z.log

## Current Reality

Preflight was SAFE-YELLOW only because AI had safe degraded provider history:

- Ollama: OLLAMA_ERROR/OLLAMA_TIMEOUT
- OpenAI: OPENAI_QUOTA_EXCEEDED
- Anthropic: OK / COMPLETED
- AI required: false for observation

No unsafe preflight blocker was present.

## Fix Applied

The active observation runner's secret detector was hardened before the run. The prior string scan treated normal identifiers such as `smoke-risk-organ` as a possible `sk-` secret because `risk-` contains `sk-`. The detector now checks structured payload values and realistic secret/token shapes, while still flagging explicit sensitive fields and real-looking key material.

## Files Created

- scripts/run_active_30m_observation.py
- tests/test_active_30m_observation_runner.py
- docs/POLYBOT_ACTIVE_30M_OBSERVATION_REPORT_20260602T091845Z.md
- docs/POLYBOT_ACTIVE_30M_OBSERVATION_BUILD_REPORT_20260602T091845Z.md
- logs/observation/active_30m_observation_20260602T091845Z.log

## Files Changed

- scripts/run_active_30m_observation.py
- tests/test_active_30m_observation_runner.py
- tests/test_ai_context_router.py

## Runtime Result

The runner turned SYSTEM ON in PAPER mode, executed bounded source-to-neuron and guarded paper-safe checks, then turned SYSTEM OFF cleanly.

Final cumulative deltas during the run:

- neural_events: +64
- mesh_sessions: +11
- shared_awareness: +11
- brain_opinions: +44
- mesh_coordinator_decisions: +11
- capital_evaluations: +11
- AI_CONTEXT_UPDATED: +9
- AI_CONTEXT_UNAVAILABLE: +0
- NEWS_DETECTED: +18
- ORDERBOOK_REFRESHED: +9
- WHALE_DETECTED: +1

Trading and paper deltas during the run:

- live_orders: +0
- real_orders_current: +0
- orders_v2: +0
- fills_v2: +0
- canonical_positions: +0
- paper_intents: +0
- paper_orders: +0
- paper_fills: +0
- paper_positions: +0
- paper_trade_ledger: +0

Final paper state:

- paper_lineage: OK
- capital_reconciliation: OK
- open_positions: 0
- active_positions_without_fills: 0
- realized_pnl: 23.55
- unrealized_pnl: 0.0
- available_balance: 1000.0
- locked_balance: 0.0
- open_exposure: 0.0

## AI Provider Result

Ollama continued to time out during runtime context generation. OpenAI remained quota-limited from the prior verification state. Anthropic succeeded as fallback, and the AI router reported `latest_status=OK`, `selected_provider=anthropic`, `success_count=10`, `unavailable_count=2` after the run.

## Safety Checklist

- SYSTEM OFF after run: yes
- live enabled: false
- shadow enabled: false
- live orders: 0
- real order delta: 0
- orders_v2 delta: 0
- fills_v2 delta: 0
- canonical positions delta: 0
- paper lineage: OK
- capital reconciliation: OK
- mock dashboard data: false
- secrets exposed: false
- fake AI context: not detected
- hard stop triggered: no

## Tests

Command:

```powershell
docker compose --profile test run --rm --no-deps test python -m pytest tests/test_active_30m_observation_runner.py tests/test_ai_context_router.py tests/test_v3_source_to_neuron_ingestion_wiring.py tests/test_overnight_observation_runner.py tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py tests/test_v2_21_source_status.py -q
```

Result:

```text
58 passed, 1 warning in 356.19s
```

## Remaining Risks

- Ollama remains slow/degraded and should be tuned separately.
- OpenAI quota is still exhausted or rate-limited.
- The run produced intelligence and coordinator/capital activity but no new paper trade entry because eligibility blockers remained active, mainly missing trusted orderbook and already-executed intents.

## Phase Status

GREEN. The 30-minute full SYSTEM ON paper-safe intelligence observation completed safely, produced source-backed intelligence activity, and did not mutate trading surfaces.
