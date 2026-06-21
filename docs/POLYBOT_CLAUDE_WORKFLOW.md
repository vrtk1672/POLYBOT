# POLYBOT Claude Workflow

Claude is a Secondary Builder inside POLYBOT.

Claude may build, but only with strict scope, safety rules, and verification.

## Role Split

ChatGPT:
- commander
- architect
- judge
- prompt designer
- final decision maker

Codex:
- main builder
- core implementation
- deep repo work

Claude:
- secondary builder
- reviewer
- test engineer
- docs engineer
- failure analyzer
- scoped fixer

## Task Modes

### A. READ_ONLY_REVIEW

Claude reads and reviews only.
No file changes.

Use for:
- reviewing Codex output
- reviewing Claude output
- checking architecture
- checking safety
- checking test results
- checking current repo reality

### B. SAFE_BUILD

Claude may create or modify low-risk files.

Allowed:
- docs
- tests
- scripts
- validators
- parsers
- health checks
- read-only endpoints
- dashboard truth fields

Not allowed:
- trading execution
- live path
- order/fill/position creation
- State Governor core
- Risk Governor core
- dangerous migrations

### C. SCOPED_FIX

Claude may fix one defined bug only.

Rules:
- fix only the bug
- no unrelated refactor
- no broad redesign
- add or update tests
- report exact verification

### D. CONTROLLED_FEATURE

Claude may build a small feature with strict scope.

Rules:
- explicit allowed files
- explicit out-of-scope list
- tests required
- no live trading
- no fake dashboard data
- no safety bypass

## Every Claude Task Must Include

- task mode
- goal
- allowed files
- forbidden files
- exact scope
- out of scope
- tests required
- verification commands
- final GREEN/YELLOW/RED status

## Claude Code as Builder — Not Only Reviewer

Claude Code is expected to reduce Codex dependency.

Claude Code can build scoped non-critical features independently when:
- The task has explicit allowed and forbidden files.
- No forbidden core areas are touched.
- Tests can verify the result.
- No PAPER, SHADOW_LIVE, or LIVE activation is involved.

ChatGPT should assign Claude Code first for all non-core work, and escalate to Codex only when Claude Code has confirmed it cannot complete the work within its safe boundary.

### SAFE_BUILD Examples for POLYBOT

- Link Coverage Hardening: audit signal events for required link fields; produce coverage report; write validator.
- Signal Quality Contract: define signal quality scoring schema; build validator; write tests.
- Mesh Blockers Dashboard: build read-only API for current blocker summary; wire to dashboard panel.
- Dry Run Provenance: build provenance logging for dry-run cycles; produce evidence scripts.
- Producer Health Accuracy: build producer freshness checks; surface health truth in dashboard.
- Lineage Coverage Hardening: audit and repair signal lineage fields across all neuron outputs.
- Build Reports: write build reports summarizing phase completion, test results, and gaps.
- Test Suites: write targeted pytest tests for phase contracts, validators, and signal schemas.

### SCOPED_FIX Examples for POLYBOT

- Fix a field mapping bug in a signal parser (non-trading path).
- Repair a stale dashboard truth field that is showing wrong data.
- Fix a test that fails due to a schema change in a non-trading table.
- Correct a link field that references the wrong source ID.

### CONTROLLED_FEATURE Examples for POLYBOT

- Add a new read-only dashboard panel showing signal quality scores per neuron.
- Add a new health check endpoint that returns producer freshness status.
- Add a validator that checks if all required signal fields are present before mesh propagation.
- Add a coverage counter that reports lineage completeness by neuron type.

## Direct Mode Rules

Claude Code is currently operating in **Direct Mode** — working directly inside `C:\Server\apps\polybot` without Git worktree isolation.

Git worktree is paused. See `docs/POLYBOT_CLAUDE_DIRECT_MODE_PROTOCOL.md` for full protocol.

Additional rules that apply in Direct Mode:

1. Every task must define an explicit allowed file list before Claude starts.
2. Claude must not write to any file outside the allowed file list for the active task.
3. If Claude encounters a forbidden domain (Risk, Execution, Exit, Capital, State Governor, trading path), it stops immediately and marks the task RED.
4. ChatGPT must review every Claude output before the next task begins.
5. If a task requires touching more than 5 files across different domains, it should be broken into smaller tasks or escalated to Codex.

### Task Template

Every Direct Mode task must open with:

```
TASK MODE: READ_ONLY_REVIEW / SAFE_BUILD / SCOPED_FIX / CONTROLLED_FEATURE / OUTPUT_REVIEW
GOAL: [one sentence]
ALLOWED FILES: [exact list]
FORBIDDEN FILES: [exact list]
FORBIDDEN DOMAINS: [Risk / Execution / Exit / Capital / State / trading path / etc.]
TESTS ALLOWED: YES / NO — [which test files, which commands]
COMMANDS ALLOWED: [specific commands]
```

Use templates from `docs/POLYBOT_CLAUDE_TASK_TEMPLATES.md`.

---

## Output Review Required

Every Claude Code task must end with a review by ChatGPT before the next task begins.

- Claude's suggested GREEN / YELLOW / RED status is **advisory only**.
- ChatGPT is the final judge. Claude's status is not binding.
- No task begins until ChatGPT issues a verdict on the previous task.
- ChatGPT may confirm, upgrade, or downgrade Claude's suggested status.

See `docs/POLYBOT_CLAUDE_OUTPUT_REVIEW_PROTOCOL.md` for the full review protocol.
See `docs/POLYBOT_CLAUDE_GREEN_YELLOW_RED_RULES.md` for the compact status rulebook.

---

## Hard RED Conditions

Claude output is RED if:

- phase tests failed
- safety tests failed
- live safety unclear
- secrets exposed
- fake dashboard data introduced
- State Governor bypassed
- Risk Gate bypassed
- duplicate DB truth created
- implementation exceeded scope

## Standard Final Output

1. Short summary
2. Current reality found
3. Files created
4. Files changed
5. DB migrations
6. API routes
7. Dashboard changes
8. Tests added
9. Tests run and exact results
10. Runtime verification results
11. Safety checklist
12. Remaining risks
13. Status: GREEN / YELLOW / RED
14. Can continue: YES / NO
