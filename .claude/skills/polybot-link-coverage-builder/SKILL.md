---
name: polybot-link-coverage-builder
description: Diagnose and improve signal link field coverage across all neuron outputs. Use when working on Link Coverage Hardening in the Mesh Hardening phase. Produces coverage reports and suggested links as read-only truth — never forces links or mutates trading decisions.
---

# POLYBOT Link Coverage Builder

## Purpose

Help Claude Code diagnose and improve the coverage of market-link fields (`market_id`, `market_slug`, `condition_id`) in neuron-emitted signals, without forcing fake links or creating trading decisions.

Link coverage hardening means: every signal that *can* be linked to a market *should* be. Signals that genuinely cannot be linked must be classified and explained — not silently dropped or faked.

---

## When to Use

- During the Mesh Hardening / Link Coverage Hardening phase.
- When a signal audit reveals unlinked signals in `neuron_signals` or the event bus.
- When you need a coverage report before deciding which signals are ready for mesh propagation.
- When building a validator that checks whether required link fields are populated before a signal enters the decision layer.

---

## Scope

Allowed to inspect or create:

- `app/signals/` — signal schema definitions
- `app/neurons/` — neuron output adapters (read-only inspection)
- `app/mesh/` or `app/neural_mesh/` — mesh event binding layer
- `app/validators/` — link coverage validators
- `app/db/models/` — signal/binding DB models (read-only inspection)
- `tests/` — link coverage validator tests
- `scripts/` — read-only diagnostic scripts
- `docs/` — coverage reports and gap documentation

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
- Any file that creates, modifies, or deletes trading decisions
- Forcing `market_id` onto signals that do not have a genuine market link

---

## Safety Rules

- Never link a signal to a market by fabrication. `market_id = None` is honest; a fake ID is not.
- Never mutate order, fill, or position records.
- Never create signals that enter the live trading path.
- No fake dashboard data — coverage metrics must come from real DB or runtime truth.
- Do not bypass State Governor or Risk Gate.
- If a hard boundary is reached, report RED and stop.
- Secrets must never be printed or logged.
- If data is missing, prefer `unlinked_by_reason = "no_market_reference"` over guessing.

---

## Required Investigation Before Building

Before writing any code, Claude must:

1. Read `docs/V2_NEURAL_MESH_PART1A_SIGNAL_CONTRACT.md` to understand the signal schema.
2. Read `docs/V2_NEURAL_MESH_PART1C_SIGNAL_EVENT_BINDING.md` for event binding truth.
3. Read `docs/NEURAL_MESH_SIGNAL_BINDING_RUNTIME_WIRING_REPORT.md` for current binding state.
4. Inspect `app/db/models/` for `neuron_signals` and `neuron_signal_bindings` table definitions.
5. Inspect `app/signals/` or `app/mesh/` for existing link field population logic.
6. Run a read-only query or script to count: total signals, linked signals, unlinked signals.
7. Identify the *reason* each unlinked signal is unlinked (no market reference in source, neuron does not emit market fields, etc.).

---

## Required Implementation Standards

### Unlinked Signal Classification

Classify every unlinked signal into one of:

- `no_market_reference` — the source data for this signal type contains no market identifier
- `missing_neuron_output_field` — the neuron does not populate the link field at emit time
- `market_lookup_failed` — a market reference exists but the lookup returned nothing
- `binding_not_yet_run` — signal predates migration 0061 (known gap; not a code bug)
- `unknown` — cannot determine reason without further investigation

### Linkable vs Non-Linkable

Distinguish:
- **Linkable signals**: signals where a market reference exists in the source but the neuron is not populating it. These should be fixed in the neuron adapter.
- **Non-linkable signals**: signals whose source type genuinely has no market context (e.g., macro-level news). These should be documented, not forced.

### Suggested Market Links

Produce `suggested_market_links` as a read-only output:
- Format: `{ signal_id, suggested_market_id, match_basis, confidence }`
- `match_basis`: how the suggestion was derived (e.g., `"title_keyword_match"`, `"existing_binding"`)
- These are suggestions only. No code should apply them automatically.
- Never write suggested links to a live trading table.

### Coverage Status

Produce a coverage status summary:

```
total_signals: N
linked: N
unlinked: N
linkable: N
non_linkable: N
coverage_pct: X%
```

---

## Required Tests

Before reporting GREEN, the following tests must pass:

1. **Unlinked by reason test** — given a set of mock signals, the classifier returns correct `unlinked_by_reason` values.
2. **Linkable vs non-linkable test** — given a mixed set of signals, the splitter correctly identifies which are linkable.
3. **Suggested market links test** — given a signal with a known market reference, the suggester returns the correct `suggested_market_id` and `match_basis`.
4. **No order mutation test** — run all link coverage logic end-to-end; assert that no order, fill, or position record is created or modified.
5. **Coverage summary test** — given a known set of signals, the coverage summary returns correct counts and percentage.

---

## Verification Expectations

- Run: `pytest tests/ -k "link_coverage" -v`
- All 5 test categories above must pass.
- Script output must show real DB counts, not mocked numbers.
- No runtime process started during tests.
- No migration applied.

---

## Expected Outputs

1. `unlinked_by_reason` — dict mapping reason → signal list
2. `linkable_signals` — list of signals that can be fixed
3. `non_linkable_signals` — list of signals that are genuinely unlinked by design
4. `suggested_market_links` — read-only suggestion list
5. `coverage_status` — summary dict with counts and percentage
6. `remaining_blockers` — list of gaps that need Codex or ChatGPT approval to resolve

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
All 5 test categories pass. Coverage report produced from real data. No order/fill/position records mutated. No fake links created. No forbidden files touched.

**YELLOW:**
Coverage report produced but one or more test categories missing or skipped. Or: linkable signals identified but fix not yet verified. Or: suggested links could not be validated against real market data.

**RED:**
Any test failed that touches order/fill/position mutation. Any fake `market_id` introduced. Any forbidden file (Risk Governor, Execution Cortex, State Governor, Capital Allocator, Exit Cortex) modified. Any migration applied without explicit approval.
