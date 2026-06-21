# POLYBOT Claude GREEN / YELLOW / RED Status Rulebook

Date: 2026-05-28
Status: ACTIVE

This is the compact status reference for Claude Code and ChatGPT.
Use this alongside `docs/POLYBOT_CLAUDE_OUTPUT_REVIEW_PROTOCOL.md` which defines the full ChatGPT review process.

Claude Code's suggested status is **advisory only**. ChatGPT is the final judge.

---

## 1. Purpose

Every Claude Code task must end with a status of GREEN, YELLOW, or RED.

This document defines:
- What each status means.
- When each status applies.
- How status escalates.
- POLYBOT-specific examples.

---

## 2. GREEN

### Definition

GREEN means the output is honest, evidence-backed, safe, and within scope.

GREEN does **not** mean perfect. It means every required item is present and verifiable.

### Required for GREEN

All of the following must be true:

| Condition | Required |
|---|---|
| All required files created or updated | YES |
| All work stayed inside the allowed file list | YES |
| No forbidden domains touched | YES |
| Required tests ran and passed | YES (or "not required for this task type") |
| Safety checklist completed — all 8 items confirmed | YES |
| Remaining risks documented honestly | YES |
| No fake/mock data presented as production truth | YES |
| No hidden failures or suppressed errors | YES |
| Evidence provided (file list, test output, or API response) | YES |
| No dependency on unresolved RED items | YES |

### GREEN Examples

| Scenario | Status |
|---|---|
| Claude created `.claude/skills/polybot-new-skill/SKILL.md` only | GREEN |
| Claude created docs-only files with no app/ changes | GREEN |
| Claude updated a protocol doc and updated CLAUDE.md only | GREEN |
| Claude wrote tests that all passed (19/19), no fake data | GREEN |
| Claude produced a read-only audit with no file changes | GREEN |
| Claude built a read-only API endpoint, tests pass, no trading logic | GREEN |

---

## 3. YELLOW

### Definition

YELLOW means the output is honest and safe, but incomplete or unverified in one or more areas.

YELLOW is not a failure — it is an honest acknowledgment of a remaining gap.

A YELLOW task may continue to the next step only if ChatGPT explicitly approves.

### YELLOW Applies When

| Condition | Example |
|---|---|
| Runtime proof missing | Tests pass but production API endpoint not verified live |
| Manual refresh still required | Scheduler not wired; analysis must be triggered manually |
| Known blockers remain documented | Required Codex work identified but not yet done |
| Tests passed but production not checked | Unit tests green, live system not verified |
| Docs updated but implementation not confirmed | Protocol written but runtime behavior not verified |
| One minor file outside strict scope (not a hard boundary) | Touched adjacent non-trading file with low risk |
| Test count unexplained or some categories not covered | Tests ran but not all required categories covered |
| Status depends on future Codex work | Correct implementation but depends on unresolved upstream decision |

### YELLOW Examples

| Scenario | Status |
|---|---|
| Link Coverage hardening complete, tests pass, but scheduler not wired — stale signals remain | YELLOW |
| Dashboard endpoint created but stale/error states not yet fully implemented | YELLOW |
| Docs complete but one referenced file missing — not a safety concern | YELLOW |
| Implementation complete but `neuron_signal_bindings=0` gap documented as remaining risk | YELLOW |
| Audit complete but some ambiguous files noted — safe to proceed | YELLOW |

---

## 4. RED

### Definition

RED means the output contains a hard safety violation, a boundary breach, or an unresolvable failure that prevents continuing.

A single RED condition makes the entire task RED. RED tasks must not continue until ChatGPT issues a remediation plan.

### RED Applies When

| Condition | Description |
|---|---|
| Forbidden file modified | Any file outside the allowed list was written |
| Forbidden domain touched | Risk, Execution, Exit, Capital, State Governor edited without approval |
| Tests required but not run | Task type required tests and Claude skipped them |
| Tests failed | Any failing test in the required test suite |
| Fake data introduced | mock data presented as production truth |
| market_id invented | Signal linked to a non-existent or fabricated market |
| Orders/fills/positions created | Any record in paper_orders, shadow_orders, live_orders, fills, positions |
| PAPER/SHADOW_LIVE/LIVE enabled | Mode unlocked or activated |
| Secrets exposed | Credentials, env vars, API keys printed or logged |
| Destructive command run | DROP, DELETE, TRUNCATE, rm -rf without approval |
| DB migration applied without approval | Any migration applied outside explicitly approved scope |
| Claude refuses to show changed files | Cannot confirm scope compliance |
| Safety checklist incomplete | Any safety item left blank or unaddressed |
| State Governor bypassed | Mode decision circumvented |
| Risk Gate bypassed | Risk check skipped or suppressed |

### RED Examples

| Scenario | Status |
|---|---|
| Claude modified `app/runtime/state_governor.py` while implementing a dashboard endpoint | RED |
| Claude applied migration `0071_new_table.sql` without explicit approval | RED |
| Claude introduced `mock_data=True` presented as live system truth | RED |
| Claude invented `market_id = "abc-123"` for a signal with no real market link | RED |
| Safety tests failed: `test_safety_no_orders` and `test_no_fake_market_id` | RED |
| Claude wired the scheduler to an unapproved trading path | RED |
| Claude printed API keys or environment credentials to output | RED |
| Claude created a record in `paper_orders` without PAPER mode authorization | RED |

---

## 5. Status Escalation Rules

These rules apply when the status is uncertain.

| Situation | Escalation |
|---|---|
| Any safety uncertainty (cannot confirm forbidden file not touched) | Escalate to YELLOW at minimum |
| Any forbidden file modification (Risk, Execution, Exit, Capital, State, trading) | Immediately RED |
| Any test failure in a required test suite | RED |
| Tests required by task type but skipped | YELLOW (if Claude explains) or RED (if Claude claims GREEN anyway) |
| No production runtime proof for runtime claims | Not GREEN — YELLOW |
| Mock/fake data presented as live truth | RED regardless of other status |
| Remaining risks undocumented | Escalate one level (GREEN → YELLOW, YELLOW → review) |
| No evidence for a safety claim ("no orders created" with no DB count) | YELLOW minimum; RED if hard safety boundary |
| Claude claims GREEN without file list or test output | Downgrade to YELLOW; ChatGPT must request evidence |

---

## 6. POLYBOT-Specific Examples

### Claude skills created only

- All work in `.claude/skills/`
- No `app/`, `tests/`, `docs/` modified
- Skill does not enable trading or touch forbidden domains
- **Status: GREEN**

---

### Direct Mode docs created only

- All work in `docs/`
- New protocol docs created, existing docs updated
- No `app/`, `tests/`, DB touched
- **Status: GREEN**

---

### Link Coverage hardening with manual refresh remaining

- Link coverage service implemented
- Tests pass (19/19)
- Scheduler not wired — analysis must be triggered manually
- `stale_unlinked=68` documented as remaining risk
- `neuron_signal_bindings=0` documented as pre-existing gap
- **Status: YELLOW** — Safe to continue. Remaining gaps documented honestly. No safety issue.

---

### Scheduler wiring without approval

- Claude modifies `app/scheduler.py` to wire link coverage analysis
- ChatGPT did not authorize scheduler/runtime changes
- `app/scheduler.py` is a core runtime component
- **Status: RED or Codex review required** — Stop. Do not proceed. Report to ChatGPT.

---

### Risk or Execution Cortex touched by Claude without approval

- Claude edits any file under `app/risk/`, `app/execution/`, `app/exit/`, `app/capital/`, or `app/runtime/state_governor.py`
- No explicit ChatGPT approval in the task definition
- **Status: RED** — Hard boundary. Stop. Report all changes. Await remediation plan from ChatGPT.

---

### Order table mutated by Claude

- Claude creates, modifies, or deletes a record in `paper_orders`, `shadow_orders`, `live_orders`, `fills`, or `positions`
- **Status: RED** — Immediate stop. Hard safety boundary. All work halted pending ChatGPT and Codex review.

---

### Dashboard returns mock_data=true presented as success

- Dashboard endpoint returns hardcoded values
- Output claims "data is real" or counts are plausible but not from DB
- `mock_data=True` anywhere in the dashboard code
- **Status: RED** — Fake data introduced. No GREEN can be claimed.

---

### Read-only audit with no file changes

- Claude ran a READ_ONLY_REVIEW
- Produced a full 7-section audit report
- No files modified
- Remaining questions documented
- **Status: GREEN** (if complete) or **YELLOW** (if some audit questions unanswerable)

---

## 7. Quick Reference

| Claude's claim | What ChatGPT must verify |
|---|---|
| "All tests passed" | Exact test count and output? Failing test names listed? |
| "No forbidden files touched" | File list provided? git status or Glob check shown? |
| "No orders created" | DB count provided? SELECT COUNT from order tables? |
| "Dashboard shows real data" | Endpoint called? Real DB query confirmed? |
| "Implementation complete" | All required files listed? Every required section present? |
| Status=GREEN | All 10 GREEN conditions verified? |

---

## 8. Authority Chain

```
Claude Code → suggests GREEN / YELLOW / RED (advisory)
ChatGPT → confirms, upgrades, or downgrades (binding verdict)
Codex → required for hard technical review of runtime/trading changes
```

Claude's suggested status is never the final verdict. ChatGPT issues the final GREEN/YELLOW/RED. Codex review is additionally required for core runtime and trading path changes.
