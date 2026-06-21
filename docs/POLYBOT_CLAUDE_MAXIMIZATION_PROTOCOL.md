# POLYBOT Claude Code Maximization Protocol

## 1. Purpose

Claude Code is a Secondary Builder, not only a reviewer.

This protocol defines how to use Claude Code as a real implementation partner that reduces Codex dependency for safe, scoped, testable work — while keeping Codex focused on dangerous core architecture.

The goal: every task that can safely be done by Claude Code should go to Claude Code first.

---

## 2. What Claude Code Is Best At

| Strength                  | Examples in POLYBOT                                      |
|---------------------------|----------------------------------------------------------|
| Structured repo audits    | signal coverage gaps, table truth audits, link checks    |
| Test writing              | pytest files, contract tests, signal validation tests    |
| Documentation             | protocol docs, build reports, workflow docs              |
| Safe code                 | validators, parsers, read-only APIs, health checks       |
| Dashboards                | truth panels, blocker display, mesh health view          |
| Diagnostics               | producer freshness, staleness checks, coverage counters  |
| Reports                   | coverage reports, audit reports, readiness evidence      |
| Small scoped fixes        | field mapping bugs, non-trading parser fixes             |

Claude Code works best when:
- The task has a clear boundary (explicit allowed files + explicit forbidden files).
- Success can be verified without running PAPER or LIVE.
- Failure cannot create unsafe trading behavior.
- Tests can confirm the result.

---

## 3. How to Split Phases Between Claude Code and Codex

### Standard Pattern

```
1. ChatGPT defines the phase goal and scope.
2. Claude Code audits the safe surface (diagnostics, docs, tests, dashboard truth, validators).
3. Codex handles dangerous core parts only if the audit reveals they are necessary.
4. ChatGPT reviews the final combined output and issues GREEN / YELLOW / RED.
```

### Splitting Rule

Start with Claude Code. Escalate to Codex only when:
- The audit reveals a core architecture problem.
- The fix requires touching Risk, Execution, Exit, Capital, or State Governor.
- A DB migration touches a trading table.
- Failure of the change could create unsafe trading behavior.

Do not assign Codex by default. Assign Codex only when Claude Code has confirmed it cannot complete the work within its safe boundary.

---

## 4. Claude-Safe Task Shapes

### READ_ONLY_REVIEW

```
Task mode:        READ_ONLY_REVIEW
Goal:             Inspect [target files/tables/APIs] and report current reality.
Allowed:          Read access to [specific files]
Forbidden:        All writes
Required output:  Findings, gaps, safety concerns, suggested scope
No changes.       No test claims.
```

### SAFE_BUILD

```
Task mode:        SAFE_BUILD
Goal:             Create [specific deliverable] for [specific purpose]
Context:          [relevant context from AGENTS.md or current phase]
Allowed files:    [explicit list]
Forbidden files:  [explicit list — always include core runtime, trading, risk, execution, exit, capital]
Required investigation: [what to read first]
Required implementation: [exact deliverables]
Tests:            [exact test files and what they must verify]
Verification:     [exact commands to run]
Final output:     Summary / Files created / Files changed / Tests run / Results / Safety checklist / Status
```

### SCOPED_FIX

```
Task mode:        SCOPED_FIX
Goal:             Fix exactly: [one described bug]
Context:          [what the bug is, where it lives, what correct behavior looks like]
Allowed files:    [explicit list — only files needed for the fix]
Forbidden files:  [explicit list]
Rules:
  - Fix only this bug.
  - No refactor.
  - No broad redesign.
  - Add or update test for the fix.
  - Report exact before/after behavior.
Verification:     [exact test command]
Final output:     Same as SAFE_BUILD
```

### CONTROLLED_FEATURE

```
Task mode:        CONTROLLED_FEATURE
Goal:             Build [small feature] for [specific purpose]
Context:          [why this feature is needed, what it connects to]
Allowed files:    [explicit list]
Forbidden files:  [explicit list — always include live/paper activation, trading path, core]
Rules:
  - No live trading.
  - No fake dashboard data.
  - No safety bypass.
  - Tests required before claiming GREEN.
Verification:     [exact commands]
Final output:     Same as SAFE_BUILD
```

---

## 5. How to Prevent Damage

Every Claude Code task must specify:

**Allowed files** — explicit list. Claude Code must not write outside this list.

**Forbidden files** — always include:
- `app/core/state_governor*`
- `app/core/risk_governor*`
- `app/core/execution_cortex*`
- `app/core/exit_cortex*`
- `app/core/capital_allocator*`
- `app/trading/*`
- Any migration touching trading tables
- `.env` files
- Secrets or credential files
- Any file enabling PAPER, SHADOW_LIVE, or LIVE

**No production writes without approval.**

**No live / paper activation.**

**No secrets printed or logged.**

**No fake data.** Every dashboard field must come from real DB or runtime truth.

**Tests required.** Claude Code must not claim GREEN unless tests ran and passed.

**Final GREEN/YELLOW/RED** must be reported using the standard format from `docs/POLYBOT_CLAUDE_WORKFLOW.md`.

---

## 6. Claude Code Work Examples for POLYBOT

### Link Coverage Builder
- Task: audit all signal events for presence of required link fields; produce coverage report; write repair validator.
- Mode: SAFE_BUILD
- Safe: touches only signal contract files, validators, tests, docs.

### Signal Quality Builder
- Task: define signal quality scoring schema; build validator that scores signal quality per neuron; write tests.
- Mode: SAFE_BUILD
- Safe: schema layer only, no execution path.

### Dashboard Blockers Panel
- Task: build a read-only API endpoint that returns current mesh blocker summary; wire to dashboard display.
- Mode: SAFE_BUILD / CONTROLLED_FEATURE
- Safe: read-only API + dashboard truth field; no writes to trading tables.

### Test Writer
- Task: write targeted pytest tests for a specific phase's contracts and validators.
- Mode: SAFE_BUILD
- Safe: tests only, no runtime modification.

### Docs Sync
- Task: read current build reports and update POLYBOT_CONTEXT_INDEX.md and relevant protocol docs.
- Mode: SAFE_BUILD
- Safe: docs only, no code changes.

### Route Audit
- Task: audit all FastAPI routes for safety compliance (mode check, auth, no live writes from GET endpoints).
- Mode: READ_ONLY_REVIEW
- Safe: read-only audit, report findings.

### Production-Safe Verification Script
- Task: build a verification script that checks DB truth, signal counts, API health, and reports a readiness status.
- Mode: SAFE_BUILD
- Safe: read-only queries, no writes, no live activation.

---

## 7. When to Stop Claude Code and Switch to Codex

Stop Claude Code and escalate to Codex when:

- The task requires architecture redesign beyond the current module boundary.
- The fix must touch Risk, Execution, Exit, Capital, or State Governor.
- Tests are repeatedly failing because of a core runtime problem, not a test problem.
- The only fix is an unsafe workaround that loosens safety checks.
- The production behavior is unclear and could affect order creation or position sizing.
- A DB migration to a trading table is required.
- Claude Code marks a sub-task RED and cannot resolve it within its safe boundary.

When escalating: report exactly which boundary was hit, what was attempted, and what Codex needs to fix.

---

## 8. Standard Claude Code Prompt Template

Use this template every time ChatGPT prepares a prompt for Claude Code:

```
POLYBOT Claude Code Task

Task mode:              [SAFE_BUILD / READ_ONLY_REVIEW / SCOPED_FIX / CONTROLLED_FEATURE]
Risk level:             [LOW / MEDIUM]
Codex review needed:    [YES / NO]
ChatGPT review needed:  YES

Goal:
[One paragraph describing the exact deliverable and why it matters.]

Context:
- Current phase: [phase name]
- Relevant docs: [list]
- Current reality: [brief summary of what exists]

Allowed files:
[Explicit list of files Claude Code may create or modify.]

Forbidden files:
[Explicit list of files Claude Code must not touch under any circumstances.]

Required investigation:
[What Claude Code must read before implementing. Include file names.]

Required implementation:
[Exact deliverables. Be specific.]

Tests:
[What tests must be written. What they must verify. What command to run.]

Verification:
[Exact commands to run. Expected output if known.]

Final output:
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
