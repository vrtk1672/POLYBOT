# POLYBOT AI Provider Root Cause Analysis

Generated: 2026-06-02T07:05Z
Scope: Ollama, OpenAI, Anthropic provider diagnostics. No secrets printed. No route_context production smoke was run after patches to avoid writing AI/neural/mesh audit rows.

## Config Snapshot

Masked `.env` inspection:

- OLLAMA_BASE_URL=http://localhost:11434
- OLLAMA_MODEL_FAST=qwen3:4b
- OLLAMA_MODEL_PRIMARY=qwen3:4b
- OLLAMA_MODEL_REASONING=qwen3:4b
- AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS: missing in `.env`, API default 15
- AI_CONTEXT_TOTAL_TIMEOUT_SECONDS: missing in `.env`, API default 45
- AI_REQUIRED: missing in `.env`, API default false
- OPENAI_API_KEY: present, masked
- OPENAI_MODEL / AI_CONTEXT_OPENAI_MODEL: missing
- ANTHROPIC_API_KEY: present, masked
- ANTHROPIC_MODEL / AI_CONTEXT_ANTHROPIC_MODEL: missing
- ANTHROPIC_VERSION: missing in `.env`, API default 2023-06-01
- LIVE_TRADING_ENABLED=false
- LIVE_KILL_SWITCH=true

API container env after compose defaults:

- AI_CONTEXT_PROVIDER_ORDER=ollama,openai,anthropic
- AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS=15
- AI_CONTEXT_TOTAL_TIMEOUT_SECONDS=45
- AI_CONTEXT_OLLAMA_KEEP_ALIVE=5m after patch/recreate
- AI_REQUIRED=false
- ANTHROPIC_VERSION=2023-06-01

## Ollama

### Code Path

- Endpoint: `/api/generate`
- Streaming: `stream=false`
- Format: `json`
- Token cap: `num_predict=min(max_response_tokens, 48)`
- Context cap: `num_ctx=512`
- Model: `qwen3:4b`

### Host Diagnostics

Windows host:

- `/api/tags`: OK, model list includes `qwen3:4b`.
- Router-like non-streaming generation with `keep_alive=0s`: 18.278s.
- Same prompt with `keep_alive=5m`: 10.774s, then 6.000s.

### API Container Diagnostics

API container:

- `http://localhost:11434/api/tags`: connection refused. Inside Docker, localhost is the API container, not host Ollama.
- `http://host.docker.internal:11434/api/tags`: OK, model list includes `qwen3:4b`.
- Patched-like generation through `host.docker.internal`, `keep_alive=5m`:
  - cold-ish call: 15.860s
  - immediate warmed calls: 3.498s and 3.453s

### Additional Finding

`qwen3:4b` returned JSON in Ollama's `thinking` field while `response` was empty. The previous router extracted only `response`, so a successful Ollama call could produce an empty AI text even when the model actually returned content.

### Root Cause

Primary:

- OLLAMA_MODEL_LOAD_SLOW / OLLAMA_GENERATION_SLOW caused by qwen3:4b latency exceeding the 15s provider timeout on cold-ish calls.

Contributing:

- OLLAMA_HOST_NETWORKING: `.env` sets localhost, which is wrong from inside the API container. The router fallback to `host.docker.internal` works, but the first endpoint is still wrong.
- OLLAMA_TIMEOUT_TOO_SHORT for cold calls.
- Router used `keep_alive=0s`, forcing model unload after each call and preventing warm-call latency.
- OLLAMA_RESPONSE_EXTRACTION_BUG: qwen3 returns useful output in `thinking` with empty `response`.

### Fix Applied

- Changed Ollama keep-alive to configurable `AI_CONTEXT_OLLAMA_KEEP_ALIVE` / `OLLAMA_KEEP_ALIVE`, default `5m`.
- In Docker, prefer `host.docker.internal:11434` before container-local localhost when `.env` uses localhost.
- Extract Ollama text from `response`, falling back to `thinking`.
- Added `AI_CONTEXT_OLLAMA_KEEP_ALIVE=5m` to `.env.example` and compose defaults.

## Anthropic

### Code Path

- Endpoint: `https://api.anthropic.com/v1/messages`
- Header: `anthropic-version: 2023-06-01`
- Body shape: Messages API with `model`, `max_tokens`, `temperature`, `messages`.

### Diagnostics

- API key present, masked.
- `GET /v1/models?limit=20`: HTTP 200.
- Available model ids included:
  - `claude-opus-4-8`
  - `claude-opus-4-7`
  - `claude-sonnet-4-6`
  - `claude-opus-4-6`
  - `claude-opus-4-5-20251101`
  - `claude-haiku-4-5-20251001`
  - `claude-sonnet-4-5-20250929`
  - `claude-opus-4-1-20250805`
- Old fallback models:
  - `claude-3-5-haiku-latest`: HTTP 404, `not_found_error`
  - `claude-3-haiku-20240307`: HTTP 404, `not_found_error`
- Current model tiny call:
  - `claude-haiku-4-5-20251001`: HTTP 200 with max_tokens=1.

### Root Cause

ANTHROPIC_MODEL_NOT_FOUND.

The endpoint, auth, version header, and request body shape are valid. The 404 came from stale fallback model names not available to this account/key.

### Fix Applied

- Updated Anthropic default fallback order to include:
  - `claude-haiku-4-5-20251001`
  - `claude-sonnet-4-6`
  - legacy fallbacks after current models
- Added `ANTHROPIC_MODEL=claude-haiku-4-5-20251001` to `.env.example`.

## OpenAI

### Code Path

- Endpoint: `https://api.openai.com/v1/chat/completions`
- Default model: `gpt-4o-mini`
- Body: chat completions with `messages`, `temperature=0`, bounded `max_tokens`.

### Diagnostics

Tiny call returned:

- HTTP 429
- error type: `insufficient_quota`
- error code: `insufficient_quota`
- message says current quota exceeded and to check plan/billing details.

### Root Cause

OPENAI_QUOTA_EXCEEDED.

This is not a transient local timeout and not a model-name issue. It requires operator/provider account action.

### Fix Applied

- Added precise `OPENAI_QUOTA_EXCEEDED` classification.
- Kept generic 429/rate text as `OPENAI_RATE_LIMITED`.
- Added `OPENAI_QUOTA_EXCEEDED` to observer safe-yellow AI reasons when AI is optional.

## AI Router Policy

- AI_REQUIRED=false is visible in dashboard/config.
- AI all-fail path remains non-blocking.
- AI_CONTEXT_UNAVAILABLE is emitted on total failure.
- No fake AI_CONTEXT_UPDATED is emitted when no provider succeeds.
- Source-to-neuron uses the router and keeps AI as supporting context only.
- Observation preflight can allow safe-yellow AI degradation only when other safety checks are clean.

## Safety

No live/shadow/order/write endpoints were called during this RCA. Direct provider diagnostics did not write DB rows. The API container was rebuilt/recreated with SYSTEM OFF.
