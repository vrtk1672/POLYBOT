# Local AI Mesh Performance Stabilization Report

## 1. Purpose

Stabilize the existing Full Mesh AI intelligence organ so local Ollama can participate during normal PAPER runtime without stalling the supervisor. This stage keeps AI advisory only: AI records insights, why-not reasoning, thesis suggestions, hold-time hints, and exit/invalidation suggestions, but never creates intents, orders, fills, positions, or execution authority.

## 2. Current AI Timeout Root Cause

The local model was reachable, but runtime prompts were too large and task outputs were not bounded tightly enough for `qwen3:4b` inside supervisor time budgets. The same model was being used for both fast and reasoning tasks, and candidate reasoning could consume too much runtime budget. The runtime failure mode was safe but noisy: `ReadTimeout: timed out` produced PARTIAL AI runs.

## 3. Ollama / Local Model Audit

- Provider: Ollama.
- API-container reachable base URL: `host.docker.internal:11434`.
- Available model observed: `qwen3:4b`.
- Streaming: not used.
- JSON mode: used through Ollama `format=json`.
- Previous risk: even with JSON mode, long prompts and model behavior could produce timeout or invalid JSON.
- Current mode: bounded FAST_ONLY by default when only one local model is configured.

## 4. Benchmark Result

The new benchmark endpoint verifies connectivity, model list, compact JSON prompts, and task-shaped prompts. Latest observed model benchmark:

- Status: `OK`
- Recommended mode: `ENABLED`
- Model: `qwen3:4b`
- Tiny JSON prompt: success, about 2.0 seconds
- Event classification prompt: success, about 5.1 seconds
- Thesis prompt: success, about 11.3 seconds
- Latest benchmark error: none

Runtime candidate refresh is now bounded, but `qwen3:4b` can still occasionally return invalid JSON for candidate tasks. That is stored as `AI_INVALID_JSON` and does not crash runtime.

## 5. Prompt Compression Strategy

Prompts were reduced to compact JSON-only tasks:

- No chain-of-thought requests.
- No prose outside JSON.
- Event prompts ask only for compact summary/entities/topics/confidence.
- Candidate fast prompts ask for a very small JSON object.
- Prompt size is bounded by `max_prompt_chars`.
- Runtime source-refresh uses a smaller prompt/token budget than manual benchmark.

## 6. JSON Output Strategy

AI output handling now:

- Parses JSON strictly.
- Attempts one safe embedded JSON extraction.
- Records `AI_INVALID_JSON` if parsing still fails.
- Does not fabricate missing AI output.
- Keeps raw diagnostic snippets truncated.
- Sanitizes nested runtime payloads through existing JSON-safe handling.

## 7. Model Split Policy

Configuration now distinguishes fast and reasoning models:

- `AI_FAST_MODEL` / `OLLAMA_MODEL_FAST`
- `AI_REASONING_MODEL` / `OLLAMA_MODEL_REASONING`
- `AI_FAST_TIMEOUT_SECONDS`
- `AI_REASONING_TIMEOUT_SECONDS`
- `AI_NUM_PREDICT_FAST`
- `AI_NUM_PREDICT_REASONING`

With only `qwen3:4b` available, normal runtime defaults to fast bounded calls and disables reasoning calls by default. Reasoning can be enabled later when a faster or more JSON-reliable local model is available.

## 8. Runtime Budget Policy

Runtime AI is bounded:

- Source-refresh AI calls per cycle: 1.
- Reasoning calls per cycle: 0 by default.
- Prompt characters: bounded.
- Token output: bounded.
- Timeouts produce PARTIAL AI status, not supervisor failure.
- Budget skips, cache skips, low-priority skips, invalid JSON, timeouts, and latency are reported.

## 9. Cache / Dedup Policy

AI candidate selection now avoids repeated low-value calls:

- Prioritizes non-dominant market/side bottleneck candidates.
- Deprioritizes duplicate dominant rows.
- Counts skipped cached and budget-limited candidates.
- Keeps recent insight reuse visible in diagnostics.

## 10. Bottleneck Candidate Prioritization

The AI budget is aimed at:

- `THESIS_MISSING`
- `THESIS_WATCH`
- `missing_dynamic_hold_time`
- `exit_not_ready`
- Non-dominant market/side candidates
- High-priority fresh trigger or source-linked candidates

It avoids spending scarce model budget on hard identity failures, missing market/token identity, and repeated duplicate rows.

## 11. API / CLI Changes

Added:

- `GET /dashboard/api/v2/control/ai-mesh-intelligence/diagnostics`
- `POST /dashboard/api/v2/control/ai-mesh-intelligence/benchmark`

Updated:

- `GET /dashboard/api/v2/control/ai-mesh-intelligence`
- `GET /dashboard/api/v2/control/system-overview`
- `tools/polybot.ps1 report`

New visibility includes AI mode, local model list, call budgets, attempted/completed/timed-out calls, invalid JSON count, average and p95 latency, cache skips, budget skips, latest successful insight, and benchmark result.

## 12. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_ai_local_performance.py tests/test_ai_prompt_compression.py tests/test_ai_json_output_handling.py tests/test_ai_runtime_budget.py tests/test_ai_bottleneck_candidate_selection.py -q
8 passed, 2 skipped
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_ai_mesh_intelligence.py tests/test_ai_event_intelligence.py tests/test_ai_thesis_hold_time_advisor.py tests/test_ai_exit_invalidation_advisor.py tests/test_ai_mesh_integration_surfaces.py -q
7 passed, 2 skipped
```

Broad targeted:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "ai_local or ai_prompt or ai_json or ai_runtime_budget or ai_mesh or ai_thesis or hold_time"
17 passed, 4 skipped, 2331 deselected
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

## 13. Runtime Verification

The API was rebuilt and restarted. The AI benchmark completed successfully against local Ollama. A manual AI refresh remained safe but PARTIAL because the local model returned invalid JSON for one candidate task instead of timing out. This is a safer runtime failure mode than the prior timeout: the supervisor can continue and diagnostics show the exact AI failure.

## 14. AI Insight Counts Before / After

Before this stabilization, the known baseline was 66 AI insight records. During stabilization, insight rows increased through bounded test/refresh calls. The exact final count should be read from `/dashboard/api/v2/control/ai-mesh-intelligence` after runtime verification because the runtime may create additional advisory records.

## 15. Timeout Count Before / After

Before stabilization, latest AI run was PARTIAL with `ReadTimeout`. After prompt compression and runtime budgeting, benchmark prompts completed within budget. The remaining observed failure was `AI_INVALID_JSON`, not a model read timeout.

## 16. Candidates Helped

The code now prioritizes non-dominant bottleneck candidates for scarce AI calls. Because the live local model still returned invalid JSON in one candidate refresh, no fabricated upgrade was recorded. Candidate improvements should only be counted when valid AI insight JSON is persisted.

## 17. Remaining AI Blockers

- `qwen3:4b` can still return invalid JSON for compact candidate tasks.
- Runtime reasoning tasks remain disabled by default to keep PAPER runtime safe.
- A smaller/faster local instruct model with stronger JSON compliance would likely improve runtime usefulness.

## 18. Safety Result

- AI remains a Full Mesh advisory organ.
- AI outputs are non-execution-authority.
- AI did not create paper intents, orders, fills, positions, live orders, or shadow orders.
- Risk, capital, exit, and lifecycle thresholds were not changed.
- No destructive DB action was performed.

## 19. Recommended Next Action

Install or configure a faster JSON-reliable local model for fast AI tasks, then re-enable a small reasoning budget. Keep `qwen3:4b` either benchmark-only or low-frequency reasoning-only until candidate-task JSON compliance is consistently clean.
