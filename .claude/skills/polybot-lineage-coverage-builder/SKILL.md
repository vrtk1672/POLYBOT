---
name: polybot-lineage-coverage-builder
description: Audit and improve signal lineage and provenance coverage across all neuron outputs. Use during the Lineage Coverage Hardening phase of Mesh Hardening. Classifies provenance gaps and bound vs unbound signals — never invents lineage or creates fake provenance.
---

# POLYBOT Lineage Coverage Builder

## Purpose

Help Claude Code improve signal lineage and provenance coverage: ensure every signal emitted by a neuron carries enough provenance fields to trace it back to its origin (producer, source, correlation ID, raw payload reference, and generation context).

Lineage hardening means: every signal in the mesh can be audited. You can answer "who produced this signal, from what source, in what context, and when?" If you cannot answer any of those questions, the signal has a provenance gap.

---

## When to Use

- During the Lineage Coverage Hardening phase of Mesh Hardening.
- When a signal audit reveals signals missing `producer_id`, `source`, `correlation_id`, `raw_payload_ref`, or `generated_from`.
- When building a lineage coverage validator or provenance audit script.
- When diagnosing which neurons emit signals without complete provenance.
- When distinguishing signals produced in dry-run vs live runtime (provenance must record which context).

---

## Scope

Allowed to inspect or create:

- `app/signals/` — signal schema and lineage field definitions
- `app/neurons/` — neuron output adapters (read-only inspection for provenance gap diagnosis)
- `app/mesh/` or `app/neural_mesh/` — mesh propagation layer (read-only inspection)
- `app/db/models/` — `neuron_signals`, `neuron_signal_bindings`, producer/source tables (read-only)
- `app/validators/` — lineage coverage validators
- `tests/` — lineage coverage tests
- `scripts/` — read-only provenance audit scripts
- `docs/` — lineage gap reports and provenance documentation

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
- Any code that invents, backfills, or fabricates provenance for existing signals
- Any code that retroactively alters historical signal records to appear more complete

---

## Safety Rules

- Never invent provenance. A signal with `producer_id = None` is honest; a fabricated producer ID is a lie that corrupts the audit trail.
- Never backfill lineage fields in production DB records without explicit approval from ChatGPT.
- Dry-run vs runtime distinction must be preserved — never mark a dry-run signal as runtime-originated.
- No fake lineage in dashboard panels.
- Do not bypass State Governor or Risk Gate.
- If a hard boundary is reached, report RED and stop.
- Secrets must never be printed or logged.
- If lineage is incomplete, report the gap accurately — do not paper over it with defaults.

---

## Required Lineage Fields

Every signal should carry:

| Field | Purpose | Required? |
|---|---|---|
| `producer_id` | Which neuron/producer emitted this | Required |
| `source` | Which data source fed this signal | Required |
| `correlation_id` | Cross-signal tracing ID for this cycle | Required |
| `raw_payload_ref` | Reference to the raw input data (ID or hash) | Recommended |
| `generated_from` | The cycle, event, or trigger that caused emission | Recommended |
| `is_dry_run` | Was this produced in dry-run context? | Required |
| `created_at` | Timestamp of emission | Required |

---

## Required Investigation Before Building

Before writing any code, Claude must:

1. Read `docs/V2_NEURAL_MESH_PART1A_SIGNAL_CONTRACT.md` for the canonical signal schema.
2. Read `docs/V2_NEURAL_MESH_PART1B_NEURON_REGISTRY.md` for the full neuron and producer registry.
3. Read `docs/NEURAL_MESH_SIGNAL_BINDING_RUNTIME_WIRING_REPORT.md` for current binding state.
4. Inspect `app/db/models/` for the `neuron_signals` table to confirm which lineage fields exist.
5. Run a read-only audit query to count: signals with `producer_id`, signals without, signals with `correlation_id`, signals without, etc.
6. Inspect neuron adapters in `app/neurons/` to determine which are not populating lineage fields at emit time.
7. Distinguish signals from dry-run vs runtime origin to avoid mixing provenance contexts.

---

## Required Implementation Standards

### Lineage Coverage Classification

For each signal, classify:

- **Bound** (`bound`): all required lineage fields are present and non-null
- **Partially bound** (`partial`): some lineage fields present, some missing
- **Unbound** (`unbound`): most or all lineage fields missing

### Unbound by Reason

For every unbound or partially-bound signal, record:

- `missing_producer` — `producer_id` is null or empty
- `missing_source` — `source` is null or empty
- `missing_correlation_id` — `correlation_id` is null or empty
- `missing_raw_payload_ref` — `raw_payload_ref` not populated
- `missing_generated_from` — `generated_from` not populated
- `missing_dry_run_flag` — `is_dry_run` not set
- `unknown` — cannot determine without further investigation

### Dry-Run vs Runtime Distinction

Every lineage report must separately count:

- Dry-run signals (is_dry_run = True)
- Runtime signals (is_dry_run = False or unset)

Signals from dry-run cycles must not be presented as runtime evidence.

### Provenance Gap Report

Produce:

```
{
  total_signals: N,
  bound: N,
  partial: N,
  unbound: N,
  coverage_pct: X%,
  dry_run_signals: N,
  runtime_signals: N,
  unbound_by_reason: { reason: count, ... },
  provenance_gaps: [ { neuron, gap_type, count }, ... ]
}
```

---

## Required Tests

Before reporting GREEN, the following tests must pass:

1. **Bound signal test** — a signal with all lineage fields receives classification `bound`.
2. **Unbound signal test** — a signal missing `producer_id` and `correlation_id` receives classification `unbound`.
3. **Partial signal test** — a signal missing only `raw_payload_ref` receives classification `partial`.
4. **Unbound by reason test** — given a set of signals, each missing field maps to the correct reason code.
5. **Dry-run vs runtime test** — signals with `is_dry_run=True` are counted separately from runtime signals.
6. **No fake lineage test** — the lineage builder never writes fabricated provenance fields to any signal record.
7. **No order mutation test** — running lineage coverage logic end-to-end creates no order, fill, or position records.

---

## Verification Expectations

- Run: `pytest tests/ -k "lineage_coverage" -v`
- All 7 test categories above must pass.
- Lineage coverage report must show real DB counts, not mocked values.
- No runtime process started during tests.
- No migration applied.

---

## Expected Outputs

1. `lineage_coverage_summary` — full coverage dict with counts, percentages, dry-run split
2. `unbound_by_reason` — dict mapping reason → signal list
3. `bound_signals` — list of fully-bound signals (or count)
4. `unbound_signals` — list of unbound signals with gap details
5. `provenance_gaps` — per-neuron gap report
6. Tests for all lineage classification and no-fake-data guarantees

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
All 7 test categories pass. Lineage report produced from real data. No order/fill/position records mutated. No fabricated provenance fields introduced. No forbidden files touched.

**YELLOW:**
Lineage report produced but one or more test categories missing or skipped. Or: provenance gaps identified but fix not yet implemented. Or: dry-run vs runtime distinction not yet enforced in all signal paths.

**RED:**
Any test failed that touches order/fill/position mutation. Any fabricated or backfilled provenance introduced without explicit approval. Any forbidden file (Risk Governor, Execution Cortex, State Governor, Capital Allocator, Exit Cortex) modified. Any migration applied without explicit approval.
