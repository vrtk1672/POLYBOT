# POLYBOT Claude Code Skills Roadmap

## 1. Current Skills

The following Claude Code skills are already defined in `.claude/skills/`:

| Skill Name                              | Purpose                                                                 |
|-----------------------------------------|-------------------------------------------------------------------------|
| polybot-output-reviewer                 | Review Codex or Claude implementation output for GREEN/YELLOW/RED       |
| polybot-phase-builder                   | Build a strict implementation prompt for one POLYBOT V2 phase           |
| polybot-safety-auditor                  | Audit safety rules, State Governor, Risk Gate, execution blocks          |
| polybot-current-reality-auditor         | Audit the current repo reality before implementing a phase              |
| polybot-test-runner                     | Prepare and run scoped verification commands for POLYBOT phases         |
| polybot-link-coverage-builder           | Diagnose and improve signal link field coverage; produces coverage report and read-only suggested links |
| polybot-signal-quality-builder          | Build signal quality gates, scoring schema, and validators; exposes quality truth only |
| polybot-lineage-coverage-builder        | Audit and improve signal lineage/provenance coverage; classifies bound vs unbound signals |
| polybot-mesh-blockers-dashboard-builder | Build read-only dashboard truth and API for Mesh Hardening blockers     |
| polybot-producer-health-builder         | Diagnose producer health and signal accuracy; classifies active/stale/failing producers |

Added in Phase 3 Mesh Hardening (2026-05-28). See `docs/POLYBOT_CLAUDE_SKILLS_PHASE3_MESH_HARDENING_REPORT.md`.

---

## 2. Recommended New Skills

The following skills should be created to support the Mesh Hardening and beyond phases:

### Immediate Priority

All Immediate Priority skills have been created (2026-05-28). See Current Skills above.

### Next Priority

| Skill Name                              | Purpose                                                                 |
|-----------------------------------------|-------------------------------------------------------------------------|
| polybot-dry-run-provenance-builder      | Build dry-run provenance logging and evidence scripts                   |
| polybot-dashboard-truth-builder         | Build or repair dashboard truth fields from real DB/runtime sources     |
| polybot-runtime-diagnostics             | Read-only audit of runtime health, cycle ledger, and API responsiveness |

### Later

| Skill Name                              | Purpose                                                                 |
|-----------------------------------------|-------------------------------------------------------------------------|
| polybot-db-safety-reviewer              | Review DB migrations for safety, duplicate truth, and schema risks      |
| polybot-log-analyzer                    | Parse and summarize POLYBOT runtime logs for anomalies and failures     |
| polybot-doc-sync                        | Synchronize POLYBOT docs with current repo reality                      |
| polybot-safe-fix                        | Apply one scoped, non-trading bug fix with test verification            |

---

## 3. Priority Order

### Immediate (current Mesh Hardening phase)
1. polybot-link-coverage-builder
2. polybot-signal-quality-builder
3. polybot-lineage-coverage-builder
4. polybot-mesh-blockers-dashboard-builder

### Next (Paper Readiness and Shadow Live prep)
5. polybot-producer-health-builder
6. polybot-dry-run-provenance-builder
7. polybot-dashboard-truth-builder
8. polybot-runtime-diagnostics

### Later (tooling and automation layer)
9. polybot-db-safety-reviewer
10. polybot-log-analyzer
11. polybot-doc-sync
12. polybot-safe-fix

---

## 4. Skill Template

Use this template when creating a new POLYBOT Claude Code skill:

```markdown
---
name: [polybot-skill-name]
description: [One sentence: when to use this skill and what it produces. Used by the system to match user requests to this skill.]
---

# [Skill Display Name]

## When to Use

[Describe the trigger condition: what the user asks, or what phase/situation calls for this skill.]

## Scope

[What files, tables, APIs, or layers this skill is allowed to inspect or create.]

## Out of Scope

[What this skill must never touch. Always include:]
- State Governor core
- Risk Governor core
- Execution Cortex
- Exit Cortex
- Capital Allocator
- Order / fill / position creation
- Live / Shadow Live / Paper activation
- Production migrations
- Secrets

## Safety Rules

- No live trading enabled.
- No fake dashboard data.
- No safety bypass.
- No write outside allowed scope.
- No secrets printed.
- If blocked by a hard boundary, report RED and stop.

## Required Tests

[Describe what tests must pass before this skill can report GREEN.]

## Final Output

1. Summary
2. Files created
3. Files changed
4. Tests run
5. Exact test results
6. Safety checklist
7. Remaining risks
8. Status: GREEN / YELLOW / RED
9. Can continue: YES / NO
```

---

## 5. Notes on Skill Evolution

Skills should be added when:
- The same type of task recurs across multiple phases.
- A task shape is complex enough to need explicit scope, safety, and output rules.
- An agent repeatedly needs the same investigation or build pattern.

Skills should not be created for:
- One-time tasks with no recurring value.
- Tasks that are already covered by an existing skill with minor variation.
- Tasks that touch core dangerous areas (those belong to Codex prompts, not Claude skills).
