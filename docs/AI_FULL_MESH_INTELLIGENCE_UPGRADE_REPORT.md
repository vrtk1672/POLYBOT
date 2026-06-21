# AI Full Mesh Intelligence Upgrade Report

## 1. Purpose

This stage upgrades AI from a passive summary layer into a persisted Full Mesh intelligence organ. The organ produces advisory event, recall, thesis, hold-time, exit, invalidation, already-priced-in, why-not, and decision critique records that other POLYBOT surfaces can inspect.

AI remains DATA_ONLY and non-execution-authority.

## 2. Why AI Belongs Inside Full Mesh

POLYBOT is a Full Mesh decision system, not a linear pipeline. AI contributes interpretation and critique, while deterministic organs retain authority over market identity, source truth, token matching, risk, capital, exit, lifecycle, and execution.

## 3. Current AI Audit

Existing AI code was present in `ai_context_router`, `ai_edge_reasoner`, brain modules, and mesh organ adapters, but AI was not producing persisted Mesh-native insights during normal runtime. Full Mesh registry had an AI reasoner concept, but source refresh/runtime did not make AI a first-class advisory evidence producer.

## 4. Local Model Status

Ollama is reachable from the API container through `host.docker.internal:11434`. Available model: `qwen3:4b`.

Runtime result: local model status is available, but generation calls timed out in the API container during verification. The organ degraded safely and persisted fallback why-not/missing-evidence insights with the exact `ReadTimeout` error.

## 5. Architecture

Implemented `AIMarketIntelligenceMeshOrgan` in `app/services/ai_mesh_intelligence.py`.

The organ:

- reads recent policy-reviewed candidates and source events
- calls local Ollama within strict limits where available
- persists AI Mesh insight records
- persists AI run records with local model status, latency, failures, and safety metadata
- exposes control endpoints and system overview/CLI visibility
- runs in the source refresh supervisor cycle with a low runtime limit

## 6. AI Insight Data Model

Added `ai_mesh_insights` and `ai_mesh_intelligence_runs`.

Each insight stores lineage, model provider/name, insight type, summary, reasoning brief, entities/topics, direction hint, thesis type/confidence, hold-time/time-stop, exit/invalidation, already-priced-in state, missing evidence, why-not reasons, recommended Mesh action, and `is_execution_authority=false`.

## 7. AI Event Intelligence

Recent source events now receive EVENT_INTELLIGENCE and MARKET_RECALL records. AI may suggest entities/topics/search concepts, but it does not fabricate market IDs or token IDs.

## 8. AI Market Recall Assistance

Recall assistance is stored as keywords/entities/topics and related market search hints only. Deterministic Market Memory remains responsible for verified market identity.

## 9. AI Trigger Interpretation

The organ reads trigger/candidate context from policy-reviewed Mesh outputs, including multi-trigger lineage. Where a model call cannot complete, the organ still records the trigger context and exact missing evidence.

## 10. AI Thesis Builder

For candidates with `THESIS_MISSING`, `THESIS_WATCH`, weak score, or exit gaps, the organ writes TRADE_THESIS advisory insight rows. It can suggest a thesis type only when evidence supports it. Weak identity or missing evidence is recorded as `NO_VALID_THESIS`.

## 11. AI Dynamic Hold-Time Advisor

The organ writes HOLD_TIME insights when a bounded hold-time/time-stop can be suggested from the available candidate context. Runtime verification produced 4 HOLD_TIME insights.

## 12. AI Exit / Invalidation Advisor

The organ writes EXIT_PLAN and INVALIDATION insights. Exit suggestions remain advisory and do not clear Exit Cortex blockers by themselves.

## 13. AI Already-Priced-In Critic

The organ writes ALREADY_PRICED_IN critique rows. Current fallback result is `UNKNOWN` unless enough market/orderbook/event movement evidence exists.

## 14. AI Why-Not Explainer

WATCH/BLOCK/INCOMPLETE candidates receive WHY_NOT and DECISION_CRITIQUE records with exact blockers such as thesis not supported, opportunity score below threshold, incomplete lineage, exit not ready, and existing hard blockers.

## 15. Runtime Alerting

The API supports AI alerts through the same insight table. No high-confidence AI alert was generated during verification.

## 16. Integration Surfaces

Added:

- `GET /dashboard/api/v2/control/ai-mesh-intelligence`
- `POST /dashboard/api/v2/control/ai-mesh-intelligence/refresh`
- system overview `ai_mesh_intelligence`
- CLI status/report AI Mesh block
- source refresh supervisor registration `ai_mesh_intelligence`

## 17. Tests Run

Focused:

`.venv\Scripts\python.exe -m pytest tests/test_ai_mesh_intelligence.py tests/test_ai_event_intelligence.py tests/test_ai_thesis_hold_time_advisor.py tests/test_ai_exit_invalidation_advisor.py tests/test_ai_mesh_integration_surfaces.py -q`

Result: `7 passed, 2 skipped`.

Related:

`.venv\Scripts\python.exe -m pytest tests/test_paper_eligibility_funnel_audit.py tests/test_non_dominant_thesis_coverage.py tests/test_multi_trigger_candidate_generation.py tests/test_trade_opportunity_scoring.py tests/test_paper_runtime_execution_chain.py -q`

Result: `13 passed, 2 skipped`.

Broad:

`.venv\Scripts\python.exe -m pytest tests -q -k "ai_mesh or ai_event or ai_thesis or hold_time or exit_invalidation or opportunity_score or paper_runtime or mesh"`

Result: `121 passed, 121 skipped, 2100 deselected`.

Compile:

`.venv\Scripts\python.exe -m compileall app tests`

Result: clean.

## 18. Runtime Verification

Before runtime:

- AI insights: 49
- paper intents/orders/fills/positions: 26 / 17 / 14 / 17
- open paper positions: 1
- live/shadow/real orders: 0 / 0 / 0

Action:

- `.\tools\polybot.ps1 off`
- `.\tools\polybot.ps1 on -mode paper`
- waited for supervisor cycle completion
- `.\tools\polybot.ps1 off`

After runtime:

- AI insights: 66
- latest AI run: PARTIAL
- latest AI error: `RuntimeError: ReadTimeout: timed out`
- paper intents/orders/fills/positions: 26 / 17 / 14 / 17
- open paper positions: 1
- live/shadow/real orders: 0 / 0 / 0
- system cleanup: OFF, execution DISABLED, supervisor STOPPED

## 19. Candidates Improved By AI

`candidates_upgraded_by_ai`: 8 advisory candidates had thesis/hold-time/exit/why-not context added. These are not execution approvals.

## 20. Candidates Correctly Rejected By AI

`candidates_kept_blocked_count`: 8 candidates remained blocked/watch/incomplete with explicit missing evidence and why-not reasons.

Top reasons:

- supported trade thesis required
- candidate must classify as PAPER_OBSERVATION
- opportunity score below threshold
- lineage incomplete
- exit not ready
- existing hard blockers present

## 21. Remaining Blockers

Local Ollama is reachable but generation timed out during runtime calls. This limits AI to deterministic/fallback advisory insights until prompt size/model latency/provider settings are tuned.

## 22. Safety Result

No paper intents, orders, fills, positions, live orders, shadow orders, or real orders were created by AI. AI outputs are explicitly marked non-execution authority and preserve all existing hard blockers.

## 23. Recommended Next Action

Tune local model serving for bounded JSON generation: shorter prompts, smaller/faster model, or a dedicated fast model. Then re-run AI Mesh refresh and measure successful model-generated insights before using them as a scoring component.
