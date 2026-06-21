---
name: polybot-producer-health-builder
description: Diagnose producer health and accuracy across all POLYBOT neuron producers. Use during the Producer Health Accuracy phase of Mesh Hardening. Classifies active, stale, and failing producers — never restarts services or modifies runtime scheduling.
---

# POLYBOT Producer Health Builder

## Purpose

Help Claude Code diagnose the health and signal production accuracy of all registered neuron producers. The goal is a clear, honest picture of which producers are active, which are stale, which are failing, and what quality of signals each is producing.

Producer health hardening means: the dashboard and mesh can accurately answer "is this producer alive, and are its signals trustworthy?" If the answer is unknown, that is a health gap — not a reason to report GREEN.

---

## When to Use

- During the Producer Health Accuracy phase of Mesh Hardening.
- When the mesh has producers that have not emitted signals recently.
- When signal quality is degraded and the source may be a failing or misconfigured producer.
- When building producer freshness checks or health truth for the dashboard.
- When diagnosing which producers are producing malformed or rejected signals.

---

## Scope

Allowed to inspect or create:

- `app/db/models/` — `neuron_producers`, `neuron_health`, `neuron_registry` tables (read-only)
- `app/validators/` or `app/health/` — producer health checkers
- `app/api/` or `app/routers/` — read-only producer health endpoints
- `app/signals/` — signal acceptance/rejection logic (read-only inspection)
- `tests/` — producer health tests
- `scripts/` — read-only producer health audit scripts
- `docs/` — producer health reports and gap documentation

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
- Any code that restarts, enables, or disables producer services at runtime
- Any code that changes producer scheduling, polling intervals, or activation state
- Any code that modifies how producers are registered without explicit approval
- Any trading decision logic

---

## Safety Rules

- Never restart or modify runtime producer services. Health checks are read-only observers.
- Never change a producer's enabled/disabled state without explicit ChatGPT approval.
- Do not fabricate `last_seen` timestamps — if a producer has never emitted, `last_seen = null` is the honest answer.
- Stale producer detection must use a configurable threshold, not a hardcoded magic number.
- Do not bypass State Governor or Risk Gate.
- If a hard boundary is reached, report RED and stop.
- Secrets must never be printed or logged.
- If data is missing for a producer, classify it as `UNKNOWN`, not `HEALTHY`.

---

## Required Investigation Before Building

Before writing any code, Claude must:

1. Read `docs/V2_NEURAL_MESH_PART1B_NEURON_REGISTRY.md` for the full producer/neuron registry.
2. Inspect `app/db/models/` for `neuron_producers` and `neuron_health` table definitions.
3. Check `docs/NEURAL_MESH_DB_ACTIVATION_GREEN_REPORT.md` for the current count: 6 producers registered.
4. Run a read-only query or script to get current state: producer names, enabled flags, last_seen timestamps, signal counts.
5. Inspect signal acceptance/rejection logic to understand what constitutes a malformed or rejected signal per producer.
6. Identify the staleness threshold already in use by the system, if any.

---

## Required Implementation Standards

### Producer State Classification

Every producer must be classified as:

- `ACTIVE` — produced signals within the freshness window; no recent errors
- `STALE` — has not produced signals within the freshness window (configurable threshold, e.g. 30 minutes)
- `FAILING` — producing signals but with high error or malformed-signal rate
- `DISABLED` — marked disabled in `neuron_producers`; expected to not produce
- `UNKNOWN` — no data available to classify

### Health Metrics Per Producer

For each producer, collect:

| Metric | Description |
|---|---|
| `enabled` | Is this producer active in the registry? |
| `last_seen` | Timestamp of most recent signal emission |
| `produced_count` | Total signals emitted (all time or since last reset) |
| `malformed_count` | Signals emitted that failed schema or quality validation |
| `accepted_count` | Signals that passed all quality gates |
| `rejected_count` | Signals that were rejected (malformed + other failures) |
| `error_count` | Producer-level errors (if tracked) |
| `staleness_flag` | True if `last_seen` exceeds staleness threshold |
| `health_status` | ACTIVE / STALE / FAILING / DISABLED / UNKNOWN |

### Stale Producer Detection

A producer is stale if:
- `last_seen` is null (never emitted), OR
- `now() - last_seen > staleness_threshold`

The staleness threshold must be configurable (not hardcoded). Default: 30 minutes.

### Producer Quality Score

Compute per producer:

```
acceptance_rate = accepted_count / produced_count  (if produced_count > 0)
quality_score = acceptance_rate  (0.0–1.0)
```

A producer with `acceptance_rate < 0.5` should be classified as `FAILING` regardless of `last_seen`.

---

## Required Tests

Before reporting GREEN, the following tests must pass:

1. **Active producer test** — a producer with recent `last_seen` and high acceptance rate is classified `ACTIVE`.
2. **Stale producer test** — a producer with `last_seen` older than threshold is classified `STALE`.
3. **Failing producer test** — a producer with `acceptance_rate < 0.5` is classified `FAILING`.
4. **Disabled producer test** — a producer with `enabled = False` is classified `DISABLED`.
5. **Unknown producer test** — a producer with no data available is classified `UNKNOWN`, not `HEALTHY`.
6. **Staleness threshold test** — changing the threshold changes which producers are classified as stale.
7. **No runtime restart test** — health check logic contains no code that restarts, enables, or disables producers.
8. **No order mutation test** — running producer health checks creates no order, fill, or position records.

---

## Verification Expectations

- Run: `pytest tests/ -k "producer_health" -v`
- All 8 test categories above must pass.
- Health report must show real DB values (6 registered producers per current DB state).
- No runtime process started during tests.
- No migration applied.

---

## Expected Outputs

1. `producer_health_summary` — overall health status across all producers
2. `stale_producers` — list of producers classified STALE with last_seen details
3. `failing_producers` — list of producers classified FAILING with acceptance rates
4. `active_producers` — list of producers classified ACTIVE
5. `producer_quality` — per-producer quality score and acceptance rate
6. Read-only API endpoint for producer health dashboard panel
7. Tests for all health classification and no-mutation guarantees

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
All 8 test categories pass. Health report produced from real DB data. No producer restart or state change performed. No order/fill/position records mutated. No forbidden files touched.

**YELLOW:**
Health report produced but one or more test categories missing. Or: stale threshold not yet configurable. Or: malformed/rejection counts not yet tracked per producer (data gap, not a code error).

**RED:**
Any runtime producer restart or state change performed. Any test failed that checks for order/fill/position mutation. Any fake `last_seen` or `health_status` fabricated. Any forbidden file (Risk Governor, Execution Cortex, State Governor, Capital Allocator, Exit Cortex) modified.
