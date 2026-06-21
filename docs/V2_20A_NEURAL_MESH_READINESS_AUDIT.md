# V2.20A Neural Mesh Readiness Audit

V2.20A is an audit-only phase before Paper Full System Run. It treats POLYBOT as a neural mesh, not a linear pipeline.

No trading features, live behavior, order creation, exit sending, or balance mutation were added.

## Audit Evidence

Generated machine-readable audit:

- `run_reports/v2_20a/neural_mesh_readiness_audit.json`

Audit scripts:

- `scripts/audit_v2_20_neural_mesh.ps1`
- `scripts/verify_v2_20_ai_models.ps1`
- `scripts/verify_v2_20_mesh_edges.ps1`
- `scripts/verify_v2_20_runtime_readiness.ps1`

## Neural Mesh Node Matrix

Static surface audit result after schema-name correction:

| Node | Status | Code | DB Truth | API Truth | Event Truth | Dashboard | Tests | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Runtime / State Governor | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Event Bus | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Market Data | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| News Neuron | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Social Neuron | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Whale Neuron | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Rules / Wording Neuron | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Market / Orderbook / Liquidity / Time / Fees Neurons | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Market Memory | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Context Brain | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Capital Brain | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Opportunity Cortex | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Strategy Router | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Capital Allocator | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Risk Gate | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Risk Governor | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Execution Cortex | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Exit Cortex | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| No-Trade Intelligence | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Feedback / Learning Loop | GREEN | yes | yes | yes | yes | yes | yes | NONE |
| Dashboard V2 | GREEN | yes | n/a | yes | n/a | yes | yes | NONE |
| AI / Local Models / Model Runtime | GREEN static, YELLOW runtime | yes | yes | yes | yes | yes | yes | HIGH runtime |
| Scheduler / Orchestrator / Runner | GREEN static, YELLOW runtime | yes | yes | yes | yes | yes | yes | HIGH runtime |
| Tests / Run Scripts / Long-Run Reports | GREEN | yes | n/a | n/a | n/a | n/a | yes | NONE |

Static matrix summary: 24 nodes present.

Runtime matrix caveat: endpoint readiness did not pass during this audit because the started runtime listened on port 8000 but health/API calls timed out.

## Neural Mesh Edge Matrix

Static edge audit result: 20 major edges connected by code/schema/API/event/query surfaces.

| From | To | Connection | Status |
| --- | --- | --- | --- |
| Market Data | Market Technical Neurons | DB / service | CONNECTED |
| Market Technical Neurons | Market Memory | DB / service | CONNECTED |
| News Neuron | Context Brain | DB / event | CONNECTED |
| Social Neuron | Context Brain | DB / event | CONNECTED |
| Whale Neuron | Context Brain | DB / event | CONNECTED |
| Rules / Wording Neuron | Context Brain | DB / event | CONNECTED |
| Context Brain | Opportunity Cortex | DB / service | CONNECTED |
| Capital Brain | Opportunity Cortex | DB / service | CONNECTED |
| Opportunity Cortex | Strategy Router | DB / service | CONNECTED |
| Strategy Router | Capital Allocator | DB / service | CONNECTED |
| Capital Allocator | Risk Gate | DB / service | CONNECTED |
| Risk Gate | Execution Cortex | DB / service | CONNECTED |
| Execution Cortex | Exit Cortex | DB / service | CONNECTED |
| Exit Cortex | Feedback / Learning Loop | DB / service | CONNECTED |
| Execution Cortex | Feedback / Learning Loop | DB / service | CONNECTED |
| No-Trade Intelligence | Feedback / Learning Loop | DB / service | CONNECTED |
| Feedback / Learning Loop | Market Memory | DB / manual confidence-gated | CONNECTED |
| All Nodes | Dashboard V2 | API / query | CONNECTED |
| Safety-Sensitive Paths | Runtime / State Governor | service | CONNECTED |
| Safety-Sensitive Paths | Risk Governor | service / DB | CONNECTED |

Runtime edge caveat: static connection does not prove live data flow. The next required step is V2.20B/V2.20C runtime smoke after startup responsiveness is fixed.

## AI / Model Readiness

Expected local models from `app/ai_brain/model_router.py`:

- `qwen3:8b`
- `qwen3:14b`
- `deepseek-r1:14b`

Cloud/escalation names referenced:

- `cloud-critical-reasoner`
- `claude-opus-4-6`

Detected state:

- `ollama` binary: not detected.
- Installed local models: none detectable.
- `ANTHROPIC_API_KEY`: not present.
- AI cache/cost tables: present in migrations.
- Hybrid AI fallback: unavailable local worker returns `UNAVAILABLE`; budget/cloud gates can block safely.
- Crash risk: MEDIUM for legacy/lite Anthropic services if invoked without `ANTHROPIC_API_KEY`; LOW for Hybrid AI unavailable local models.

Remediation when local AI is required:

```powershell
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull deepseek-r1:14b
```

Only set `ANTHROPIC_API_KEY` for explicitly approved cloud/lite analysis paths. Do not require it for safety smoke.

## Data Source Readiness

| Source | Required For | Status | Fallback | Blocker |
| --- | --- | --- | --- | --- |
| Market data | Data / technical / opportunity | UNKNOWN until runtime smoke | NO_DATA / STALE | HIGH |
| Orderbook | Liquidity / execution / exit | UNKNOWN until runtime smoke | block execution / insufficient_data | HIGH |
| News | context / invalidation | UNKNOWN until runtime smoke | stale/no-data | MEDIUM |
| Social | context / hype | UNKNOWN until runtime smoke | stale/no-data | MEDIUM |
| Whales | context / learning | UNKNOWN until runtime smoke | stale/no-data | MEDIUM |
| Rules | wording / risk / opportunity | static code present | no-trade / penalty | MEDIUM |
| AI | optional interpretation | PARTIAL | UNAVAILABLE / BUDGET_BLOCKED | MEDIUM |

## Runtime Readiness

Observed:

- Postgres reachable when `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`.
- Migrations current: `No pending migrations`.
- Applied migration count via readiness script: 57.
- Docker check timed out on `docker info`.
- Redis not detected and not required by current scripts.
- Runtime temporary process reached listening state on `127.0.0.1:8000`.
- Runtime endpoints then timed out. Verified endpoints included `/healthz`, `/runtime/state`, `/runtime/health`, `/dashboard/api/v2/overview`, `/dashboard/api/v2/learning`, `/ai/health`, `/events/lag`, `/risk/health`, `/execution/health`, `/exits/health`, `/no-trade/health`.

Runtime blocker: HIGH. Long-running V2.20 should not start until endpoint responsiveness is stable.

## Mode Readiness

DATA_ONLY:

- Static safety surfaces present.
- State Governor routes exist.
- V2.20 no-live mutation checker exists.
- Runtime endpoint instability blocks confident 30m DATA_ONLY now.

PAPER:

- Static paper/shadow boundaries present.
- PAPER smoke script exists and forces live disabled.
- Runtime endpoint instability blocks 30m PAPER now.

SHADOW / live:

- Out of scope for V2.20A.
- Live remains disabled by script policy.

## Dashboard Truth

Dashboard V2 API endpoints exist for all major nodes, including `/dashboard/api/v2/learning`.

Runtime dashboard truth check could not complete because runtime endpoints timed out. V2.18 dashboard regression tests passed, but that is not a substitute for runtime dashboard smoke.

## Test Coverage / Run Readiness

Audit tests:

- `tests/test_v2_20a_neural_mesh_readiness.py`: passed.

Regression tests run:

- Runtime: passed.
- V2.19: passed.
- V2.18: passed.

Coverage gaps before long run:

- Need runtime mesh smoke that verifies rows/events actually move across edges.
- Need endpoint latency/readiness stabilization.
- Need AI model/runtime decision for local model availability.
- Need data-source freshness evidence with runtime running.

## Blocker List

### CRITICAL

None found in static safety surfaces.

### HIGH

1. Runtime endpoint responsiveness failed after startup.
   - Affected node: Scheduler / Orchestrator / Runtime.
   - Evidence: process started and port listened, but health/dashboard/API calls timed out.
   - Why it matters: blocks 30m/24h readiness and dashboard truth checks.
   - Suggested fix: capture runtime startup logs, profile app startup after port bind, ensure scheduler/service initialization does not block the event loop.
   - Scope: medium.
   - Can safely defer: NO.

2. Local AI runtime/models missing.
   - Affected node: AI / Local Models / Model Runtime.
   - Evidence: `ollama` not found; `qwen3:8b`, `qwen3:14b`, `deepseek-r1:14b` not detectable.
   - Why it matters: AI-enhanced neurons may degrade or be unavailable during long run.
   - Suggested fix: decide whether V2.20 requires local AI. If yes, install Ollama/models. If no, explicitly run in AI-degraded mode and verify no crash.
   - Scope: medium.
   - Can safely defer: YES for no-AI smoke, NO for AI-full smoke.

3. Market/orderbook source freshness unknown.
   - Affected nodes: Market Data, Technical Neurons, Execution, Exit.
   - Evidence: runtime unavailable for source freshness checks.
   - Why it matters: orderbook/liquidity truth is required for execution and exit quality.
   - Suggested fix: after runtime responsiveness fix, run source freshness checks and dashboard data coverage.
   - Scope: small.
   - Can safely defer: NO for PAPER.

### MEDIUM

- Docker readiness is unclear because `docker info` timed out.
- Dashboard runtime truth unverified due endpoint timeout.
- Legacy paper position exit-plan linkage remains partial truth.
- Mesh edges are static-connected but need runtime row/event evidence.

### LOW

- PowerShell wildcard use with pytest passes literal globs; use explicit `Get-ChildItem` expansion or direct filenames.

## Fix Plan

V2.20A: Readiness Audit only.

V2.20B: Fix critical/high mesh blockers:

1. Runtime endpoint responsiveness/logging.
2. Runtime dashboard truth check.
3. Data source freshness check.
4. AI model/no-AI mode decision.

V2.20C: DATA_ONLY 30m smoke.

V2.20D: PAPER 30m smoke.

V2.20E: 24h DATA_ONLY.

V2.20F: 24h PAPER.

V2.20G: 72h PAPER.

V2.20H: 7d PAPER.

## Go / No-Go

- Can run 30m DATA_ONLY now: NO, fix runtime responsiveness first.
- Can run 30m PAPER now: NO, fix runtime responsiveness and source freshness first.
- Can run 24h DATA_ONLY now: NO.
- Can run 24h PAPER now: NO.

Phase status: YELLOW. Audit completed and blockers are categorized, but long-run readiness is not proven.
