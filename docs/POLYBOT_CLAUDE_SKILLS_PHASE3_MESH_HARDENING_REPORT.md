# POLYBOT Claude Skills Phase 3 — Mesh Hardening Report

**Date:** 2026-05-28
**Task Mode:** SAFE_BUILD
**Phase:** Mesh Hardening / Signal Quality Gates
**Author:** Claude Code (Secondary Builder)

---

## 1. Files Created

| File | Purpose |
|---|---|
| `.claude/skills/polybot-link-coverage-builder/SKILL.md` | Link Coverage Hardening skill |
| `.claude/skills/polybot-signal-quality-builder/SKILL.md` | Signal Quality Gates skill |
| `.claude/skills/polybot-lineage-coverage-builder/SKILL.md` | Lineage Coverage Hardening skill |
| `.claude/skills/polybot-mesh-blockers-dashboard-builder/SKILL.md` | Mesh Blockers Dashboard skill |
| `.claude/skills/polybot-producer-health-builder/SKILL.md` | Producer Health Accuracy skill |
| `docs/POLYBOT_CLAUDE_SKILLS_PHASE3_MESH_HARDENING_REPORT.md` | This report |

---

## 2. Files Changed

| File | Change |
|---|---|
| `docs/POLYBOT_CLAUDE_SKILLS_ROADMAP.md` | Updated Current Skills table; moved 5 skills from Recommended to Current |
| `docs/POLYBOT_CONTEXT_INDEX.md` | Added Phase 3 Mesh Hardening Skills section |

---

## 3. Summary of Each Skill

### A. polybot-link-coverage-builder

Diagnoses and improves market-link field coverage (`market_id`, `market_slug`, `condition_id`) across all neuron-emitted signals.

**Key capabilities:**
- Classifies unlinked signals by reason: `no_market_reference`, `missing_neuron_output_field`, `market_lookup_failed`, `binding_not_yet_run`, `unknown`
- Distinguishes linkable vs non-linkable signals
- Produces `suggested_market_links` as read-only suggestions (never applied automatically)
- Outputs coverage summary with counts and percentage

**Safety boundary:** Never forces a `market_id` onto a signal. Never creates trading decisions. Never touches Risk/Execution/Exit/Capital/State Governor.

**Required tests (5):** unlinked_by_reason, linkable/non_linkable split, suggested links, coverage summary, no order mutation.

---

### B. polybot-signal-quality-builder

Builds signal quality gates, scoring schema, and validators to classify signal completeness and validity before mesh propagation.

**Key capabilities:**
- Classifies signals as VALID / INVALID / WARNING
- Checks: market, entity, source, producer, correlation, schema, malformation
- Produces quality score per signal (0.0–1.0)
- Produces `invalid_signals_by_reason` and `quality_gate_status` per neuron

**Safety boundary:** Quality gates are diagnostic truth only — they do not directly block or approve trades. Never wired to a trade execution channel without explicit approval.

**Required tests (7):** valid signal, missing market, missing source/producer, missing correlation, malformed field, quality score, no order mutation.

---

### C. polybot-lineage-coverage-builder

Audits and improves signal lineage and provenance coverage across all neuron outputs.

**Key capabilities:**
- Classifies signals as `bound` / `partial` / `unbound` by provenance completeness
- Tracks: `producer_id`, `source`, `correlation_id`, `raw_payload_ref`, `generated_from`, `is_dry_run`
- Separates dry-run signals from runtime signals
- Produces `lineage_coverage_summary`, `unbound_by_reason`, and `provenance_gaps` per neuron

**Safety boundary:** Never invents or backfills provenance. Never retroactively alters historical signal records without explicit approval.

**Required tests (7):** bound signal, unbound signal, partial signal, unbound_by_reason, dry-run vs runtime separation, no fake lineage, no order mutation.

---

### D. polybot-mesh-blockers-dashboard-builder

Builds read-only dashboard truth and API endpoints exposing Mesh Hardening blockers across all mesh health domains.

**Key capabilities:**
- Exposes 5 dashboard panels: Signal Quality Status, Link Coverage Status, Lineage Coverage Status, Producer Health Status, Dry-Run Provenance Status
- Every panel includes stale and error states
- Blocker severity uses honest GREEN/YELLOW/RED — never fakes GREEN without real data
- API response format includes `status`, `blockers`, `last_updated`, `is_stale`, `data_source`

**Safety boundary:** No mock data. No trading controls. No mode-switch controls. Stale/error states are mandatory.

**Required tests (8):** real data, stale state, error state, blocker severity, no mock data, no trading control, signal quality status, link coverage status.

---

### E. polybot-producer-health-builder

Diagnoses producer health and signal production accuracy for all registered neuron producers.

**Key capabilities:**
- Classifies producers as ACTIVE / STALE / FAILING / DISABLED / UNKNOWN
- Tracks: `enabled`, `last_seen`, `produced_count`, `malformed_count`, `accepted_count`, `rejected_count`, `error_count`, staleness flag, health status
- Computes per-producer quality score (acceptance_rate)
- Stale threshold is configurable (default 30 minutes)

**Safety boundary:** Never restarts, enables, or disables producer services. Health checks are read-only. Never changes producer scheduling or activation state without explicit ChatGPT approval.

**Required tests (8):** active, stale, failing, disabled, unknown classification, threshold change, no runtime restart, no order mutation.

---

## 4. Safety Boundaries Confirmed

The following hard boundaries are explicitly documented in every skill:

| Boundary | Confirmed in All 5 Skills? |
|---|---|
| Risk Governor core — never touch | YES |
| Execution Cortex — never touch | YES |
| Exit Cortex — never touch | YES |
| Capital Allocator — never touch | YES |
| State Governor core — never touch | YES |
| Order creation — never touch | YES |
| Fill creation — never touch | YES |
| Position creation — never touch | YES |
| Paper / Shadow Live / Live activation — never | YES |
| Production migrations — never without approval | YES |
| Secrets — never print or log | YES |
| Fake dashboard data — never | YES |
| No trading controls in dashboard | YES |

---

## 5. How These Skills Apply to Current Link Coverage Hardening

The **polybot-link-coverage-builder** skill directly governs the current Link Coverage Hardening work:

1. **Investigation step**: The skill requires reading the signal contract (`V2_NEURAL_MESH_PART1A_SIGNAL_CONTRACT.md`), the binding wiring report, and running a read-only audit to count unlinked signals — before touching any code.

2. **Classification first**: Every unlinked signal must be classified by reason before any fix is attempted. This prevents premature or incorrect link population.

3. **Linkable vs non-linkable split**: The skill requires explicitly separating signals that can be fixed (neuron not populating a field that exists in the source) from signals that genuinely have no market context.

4. **Suggested links as read-only**: Any proposed `market_id` assignments are produced as suggestions with `match_basis` and `confidence` — never applied automatically.

5. **Tests gate every output**: The 5 required test categories prevent any link coverage work from reporting GREEN without verified non-mutation of orders/fills/positions.

The other 4 skills (signal quality, lineage, dashboard, producer health) address the parallel Mesh Hardening tracks and will feed into the `mesh_blockers_summary` once their respective phases are built.

---

## 6. Verification Performed

All verification in this task is documentation-only (SAFE_BUILD, skills/docs task).

**File existence checks performed:**

```
.claude/skills/polybot-link-coverage-builder/SKILL.md         EXISTS
.claude/skills/polybot-signal-quality-builder/SKILL.md        EXISTS
.claude/skills/polybot-lineage-coverage-builder/SKILL.md      EXISTS
.claude/skills/polybot-mesh-blockers-dashboard-builder/SKILL.md EXISTS
.claude/skills/polybot-producer-health-builder/SKILL.md       EXISTS
docs/POLYBOT_CLAUDE_SKILLS_PHASE3_MESH_HARDENING_REPORT.md    EXISTS
```

All 5 skills confirmed by the Claude Code runtime (appeared in system-reminder after each Write).

**No runtime tests run.** This is a documentation task. Runtime tests are the responsibility of the implementation phase that follows each skill.

**No Docker run.** No DB commands. No migrations.

---

## 7. Remaining Risks

| Risk | Severity | Note |
|---|---|---|
| Skills reference file paths (`app/signals/`, `app/validators/`, etc.) that may not yet exist | LOW | Skills explicitly require investigation before building — the agent will discover missing paths during the required investigation step. |
| `neuron_signal_bindings = 0` (per DB activation report) — link coverage work may find no bound signals to verify against | LOW | Known gap documented in current context. Skills handle this by classifying `binding_not_yet_run` separately. |
| Staleness threshold for producer health is not yet confirmed as a system config value | LOW | Skill defaults to 30 minutes and requires it to be configurable — implementation must verify this against current runtime config. |
| Mesh blockers dashboard requires wiring to actual runtime data sources that may need implementation first | MEDIUM | The dashboard skill requires the other 4 skills (link, quality, lineage, producer) to be implemented first to have real data sources. This is the correct dependency order. |

---

## 8. Status

**GREEN**

All 5 skills created. Each skill includes:
- YAML frontmatter (name + description)
- Purpose
- When to Use
- Scope
- Out of Scope (all 9 forbidden areas explicitly listed)
- Safety Rules
- Required Investigation Before Building
- Required Implementation Standards
- Required Tests (5–8 categories per skill)
- Verification Expectations
- Expected Outputs
- Final Output Format
- GREEN/YELLOW/RED Rules

No runtime code modified. No DB modified. No tests modified. No trading logic touched. No Docker files touched. No app/ files touched. No migrations applied. No fake status created.

---

## 9. Can Continue

**YES**

The 5 skills are ready for use. The recommended next step is:

1. Use `polybot-link-coverage-builder` to begin the Link Coverage Hardening implementation (first Mesh Hardening track).
2. Run `polybot-current-reality-auditor` first to confirm current signal binding and link field state before coding.
3. After link coverage, proceed to `polybot-signal-quality-builder` for Signal Quality Gates.
4. After all 4 domain skills are implemented, use `polybot-mesh-blockers-dashboard-builder` to surface combined truth.
