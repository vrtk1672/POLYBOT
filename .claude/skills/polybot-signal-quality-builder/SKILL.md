---
name: polybot-signal-quality-builder
description: Build signal quality gates, scoring schema, and validators for POLYBOT neural mesh signals. Use during the Signal Quality phase of Mesh Hardening. Exposes quality truth only — never blocks or approves trading directly.
---

# POLYBOT Signal Quality Builder

## Purpose

Help Claude Code work on signal quality gates: define what makes a signal valid, score signal completeness, classify invalid or malformed signals, and expose quality truth in a way that informs the mesh without directly controlling trading decisions.

Signal quality gates answer: "Is this signal complete, well-formed, and trustworthy enough to propagate through the mesh?"

---

## When to Use

- During the Signal Quality phase of Mesh Hardening.
- When signals are reaching the decision layer with missing fields, unknown sources, or invalid values.
- When building a signal quality scoring schema or validator.
- When diagnosing which neurons are producing low-quality signals.
- When adding a quality gate check to the mesh propagation path.

---

## Scope

Allowed to inspect or create:

- `app/signals/` — signal schema and quality definitions
- `app/validators/` — signal quality validators
- `app/mesh/` or `app/neural_mesh/` — mesh propagation layer (read-only inspection; quality gate hook only)
- `app/neurons/` — neuron output adapters (read-only inspection for quality gap diagnosis)
- `app/db/models/` — signal models (read-only inspection)
- `tests/` — quality gate tests
- `scripts/` — read-only quality diagnostic scripts
- `docs/` — quality reports and gap documentation

---

## Out of Scope

The following must **never** be touched by this skill, regardless of context:

- Risk Governor core
- Execution Cortex
- Exit Cortex
- Capital Allocator
- State Governor core
- Order creation logic
- Fill creation logic
- Position creation logic
- Paper / Shadow Live / Live activation
- Production DB migrations
- Secrets or `.env` values
- Any code that directly blocks or approves a trade
- Any code that modifies the Risk Gate decision

---

## Safety Rules

- Quality gates are diagnostic truth — they classify signals as VALID, INVALID, or WARNING. They do not directly block or approve trades.
- Never introduce a quality gate bypass that allows invalid signals into the decision layer silently.
- No fake quality scores — every score must be derived from real field inspection.
- Do not bypass State Governor or Risk Gate.
- If a quality gate is wired to the trading path, it must only be wired to a read-only reporting channel, not an execution channel.
- If a hard boundary is reached, report RED and stop.
- Secrets must never be printed or logged.

---

## Required Investigation Before Building

Before writing any code, Claude must:

1. Read `docs/V2_NEURAL_MESH_PART1A_SIGNAL_CONTRACT.md` for the canonical signal schema and required fields.
2. Read `docs/V2_NEURAL_MESH_PART1B_NEURON_REGISTRY.md` for the full neuron registry and expected output types.
3. Inspect `app/signals/` for existing quality-related field definitions.
4. Inspect `app/validators/` for any existing validators.
5. Identify which fields are required, which are optional, and which have format constraints.
6. Run a read-only audit to find signals with: missing `market_id`, missing `source`, missing `producer`, missing `correlation_id`, missing `entity_id`, or invalid value formats.

---

## Required Implementation Standards

### Quality Status Classification

Every signal must be classified as:

- `VALID` — all required fields present and well-formed
- `INVALID` — one or more required fields missing or malformed (signal must not propagate)
- `WARNING` — all required fields present but one or more optional quality indicators are missing (signal may propagate with warning flag)

### Quality Check Categories

The validator must check:

- **Market check**: `market_id` or `market_slug` present and non-null
- **Entity check**: `entity_id` present and non-null where required by signal type
- **Source check**: `source` present and maps to a known registered source
- **Producer check**: `producer_id` present and maps to a known registered producer
- **Correlation check**: `correlation_id` present and non-empty
- **Schema check**: all fields match declared types (no int where string expected, etc.)
- **Malformation check**: no null values in required positions, no empty strings posing as data

### Quality Scoring

Produce a quality score per signal (0.0–1.0):
- 1.0 = fully valid, all required and optional fields present
- Deduct for each missing required field, missing optional field, or format mismatch
- Score formula must be documented and reproducible

### Invalid Signal Classification

For every invalid signal, produce:

```
{
  signal_id: ...,
  invalid_reason: [...],   # list of specific failures
  quality_score: 0.0–1.0,
  recommended_action: "drop" | "quarantine" | "repair"
}
```

---

## Required Tests

Before reporting GREEN, the following tests must pass:

1. **Valid signal test** — a fully-populated signal receives status `VALID` and score `1.0`.
2. **Missing market test** — a signal missing `market_id` is classified `INVALID` with reason `missing_market`.
3. **Missing source/producer test** — a signal missing `source` or `producer_id` is classified `INVALID`.
4. **Missing correlation test** — a signal missing `correlation_id` is classified `WARNING` or `INVALID` per contract.
5. **Malformed field test** — a signal with wrong-type field is classified `INVALID` with reason `malformed_field`.
6. **Quality score test** — scoring produces correct values for known valid, partial, and invalid signals.
7. **No order mutation test** — running the quality validator end-to-end creates no order, fill, or position records.

---

## Verification Expectations

- Run: `pytest tests/ -k "signal_quality" -v`
- All 7 test categories above must pass.
- Quality report must show real signal counts from DB, not mocked values.
- No runtime process started during tests.
- No migration applied.

---

## Expected Outputs

1. `signal_quality_summary` — dict: total, valid, invalid, warning, avg_quality_score
2. `invalid_signals_by_reason` — dict mapping reason → signal list
3. `quality_gate_status` — per-neuron quality pass/fail summary
4. `quality_blockers` — list of gaps preventing full mesh quality coverage
5. Quality validator module (read-only, no trading side-effects)
6. Tests for all classification and scoring logic

---

## Final Output Format

Every run of this skill must end with:

1. Summary
2. Files created
3. Files changed
4. Tests run
5. Exact test results
6. Safety checklist
7. Remaining risks
8. Status: GREEN / YELLOW / RED
9. Can continue: YES / NO

---

## GREEN / YELLOW / RED Rules

**GREEN:**
All 7 test categories pass. Quality report produced from real data. No order/fill/position records mutated. No fake quality scores. No forbidden files touched.

**YELLOW:**
Quality report produced but one or more test categories missing or skipped. Or: quality gate logic defined but not yet tested end-to-end. Or: some signal types not yet covered by the validator.

**RED:**
Any test failed that touches order/fill/position mutation. Any fake quality score introduced. Quality gate wired directly to trade approval/blocking logic without explicit approval. Any forbidden file (Risk Governor, Execution Cortex, State Governor, Capital Allocator, Exit Cortex) modified.
