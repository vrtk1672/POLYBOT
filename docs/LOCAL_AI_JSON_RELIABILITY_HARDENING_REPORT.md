# Local AI JSON Reliability Hardening Report

## 1. Purpose

Harden the existing POLYBOT AI Mesh organ so local AI outputs are machine-readable, schema-validated, bounded, and safe during normal PAPER runtime. AI remains a Full Mesh advisory organ only. It cannot execute, create paper intents, create orders, override blockers, or fabricate market/source/token truth.

## 2. Current AI Blocker

Before this repair, local Ollama was reachable and `qwen3:4b` could pass simple benchmarks, but real candidate runtime tasks still sometimes returned invalid JSON. Latest pre-repair runtime failure was:

```text
AI_INVALID_JSON: Unterminated string
```

The timeout issue had already been stabilized. The remaining problem was JSON reliability and schema discipline for candidate tasks.

## 3. Model Audit

- Provider: Ollama
- API container base URL: `host.docker.internal:11434`
- Installed models: `qwen3:4b`
- Fast model before repair: `qwen3:4b`
- Reasoning model before repair: `qwen3:4b`
- Ollama JSON mode: supported through `format: "json"`
- Streaming: disabled
- Temperature/top_p: low and deterministic
- `think`: disabled in request payload

No smaller JSON-specialized model was installed locally.

## 4. JSON Reliability Benchmark

Added:

```text
POST /dashboard/api/v2/control/ai-mesh-intelligence/benchmark-json
```

Benchmark tasks:

- tiny JSON object
- event classification
- trigger interpretation
- thesis skeleton
- hold-time schema
- exit/invalidation schema
- why-not schema

Final live benchmark result:

- Status: `OK`
- Models tested: `qwen3:4b`
- Valid JSON: 7 / 7
- Schema valid: 7 / 7
- Fallback used: 0 / 7
- Recommended FAST_JSON_MODEL: `qwen3:4b`
- Recommended REASONING_MODEL: `qwen3:4b`
- Recommended AI mode: `FAST_JSON_ONLY`

Representative latencies:

- tiny JSON: 1566 ms
- event classification: 3439 ms
- thesis skeleton: 8491 ms
- hold time: 5210 ms
- exit/invalidation: 5969 ms

## 5. Recommended Model Configuration

Current installed model is now acceptable for bounded FAST JSON tasks:

```text
AI_FAST_JSON_MODEL=qwen3:4b
AI_FAST_MODEL=qwen3:4b
AI_REASONING_MODEL=qwen3:4b
AI_MAX_REASONING_CALLS_PER_CYCLE=0
```

Runtime should remain `FAST_JSON_ONLY` until longer reasoning prompts prove stable under repeated runs.

If future repeated runtime runs show invalid JSON again, recommended small local model pull:

```text
ollama pull llama3.2:1b
```

That command was not run during this task.

## 6. Prompt / Schema Hardening

Candidate fast prompt was reduced to a tiny JSON contract:

```json
{"summary":"watch reason <=8 words","confidence":0.0}
```

The prompt now explicitly forbids:

- markdown
- extra keys
- invented facts
- invented IDs
- execution authority

Runtime output budget was increased from too-small/truncation-prone values to a bounded `220` token budget for fast JSON calls. This fixed the real candidate refresh that was previously truncating or over-generating invalid JSON.

## 7. JSON Mode Support

Ollama request path now explicitly uses:

- `format: "json"`
- `stream: false`
- `think: false`
- `temperature: 0`
- `top_p: 0.2`
- bounded `num_predict`
- bounded `num_ctx`

Tests verify the `format=json` option is passed to Ollama.

## 8. Repair / Fallback Behavior

Added schema validation and safe repair:

- valid JSON is parsed and schema-checked
- missing non-critical fields receive safe defaults
- repaired output is marked `schema_repaired=true`
- invalid critical fields trigger `AI_SCHEMA_INVALID`
- invalid JSON triggers `AI_INVALID_JSON`
- failures create deterministic fallback only

Fallback is marked:

- `generated_by=DETERMINISTIC_FALLBACK`
- `model_provider=NONE`
- `confidence=0.0`
- `is_execution_authority=false`

Fallback never pretends to be AI reasoning.

## 9. Runtime Budget / Caching

Runtime remains bounded:

- max AI calls per cycle: 1
- max reasoning calls per cycle: 0
- cache TTL: 6 hours
- duplicate and cached evidence is skipped
- failures do not fail the supervisor

New counters:

- valid JSON
- invalid JSON
- schema invalid
- repaired JSON
- fallback count
- valid JSON rate
- latest invalid task/model

## 10. API / CLI Changes

Added:

- `POST /dashboard/api/v2/control/ai-mesh-intelligence/benchmark-json`

Updated:

- `GET /dashboard/api/v2/control/ai-mesh-intelligence`
- `GET /dashboard/api/v2/control/ai-mesh-intelligence/diagnostics`
- `GET /dashboard/api/v2/control/system-overview`
- `tools/polybot.ps1 report`

CLI now displays:

- Fast JSON model
- JSON reliability
- invalid JSON count
- schema invalid count
- repaired JSON count
- fallback count
- valid JSON rate

## 11. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_ai_json_reliable_model_selection.py tests/test_ollama_json_mode_support.py tests/test_ai_schema_validation_repair.py tests/test_ai_deterministic_fallback.py tests/test_ai_json_reliability_endpoint.py -q
9 passed
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_ai_local_performance.py tests/test_ai_prompt_compression.py tests/test_ai_json_output_handling.py tests/test_ai_runtime_budget.py tests/test_ai_bottleneck_candidate_selection.py -q
8 passed, 2 skipped
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "ai_json or ollama or ai_schema or deterministic_fallback or ai_local or ai_mesh"
20 passed, 7 skipped, 2334 deselected
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

## 12. PAPER Runtime Verification

Actions:

1. `.\tools\polybot.ps1 off`
2. `POST /dashboard/api/v2/control/ai-mesh-intelligence/benchmark-json`
3. `POST /dashboard/api/v2/control/ai-mesh-intelligence/refresh?limit=2&force=true`
4. `.\tools\polybot.ps1 on -mode paper`
5. waited for supervisor/source cycles
6. `.\tools\polybot.ps1 report`
7. `.\tools\polybot.ps1 off`

Runtime remained RUNNING during verification. Final cleanup returned system to OFF, execution DISABLED, supervisor STOPPED.

## 13. AI Insights Before / After

- Task start known baseline from previous report: 72
- Pre-hardening live audit: 89
- After manual AI refresh: 90
- After PAPER runtime verification: 95

## 14. Invalid JSON Before / After

Pre-hardening latest run:

- invalid JSON count: 1
- valid JSON rate: 0.0
- latest error: `AI_INVALID_JSON`

Post-hardening manual refresh:

- calls attempted: 1
- calls succeeded: 1
- invalid JSON: 0
- schema invalid: 0
- repaired JSON: 1
- fallback count: 3 deterministic non-model rows for budget/cache paths
- valid JSON rate: 1.0

Post-runtime:

- JSON reliability: `RELIABLE`
- invalid JSON: 0
- latest AI error: none

## 15. Remaining Blockers

- Only `qwen3:4b` is installed. It is now usable for bounded FAST JSON tasks, but reasoning calls remain disabled by default.
- Some recent insight rows still include previous fallback why-not history until refreshed by new valid model calls.
- Broader paper eligibility still depends on real thesis/score/exit evidence, not AI alone.

## 16. Recommended Next Action

Run a longer PAPER runtime with `FAST_JSON_ONLY` and monitor valid JSON rate. If valid JSON drops below 1.0 over repeated runs, install a smaller JSON-oriented fast model:

```text
ollama pull llama3.2:1b
```

Then set:

```text
AI_FAST_JSON_MODEL=llama3.2:1b
AI_FAST_MODEL=llama3.2:1b
AI_REASONING_MODEL=qwen3:4b
```

Keep reasoning calls at 0 per runtime cycle until the reasoning model passes repeated JSON reliability benchmarks.
