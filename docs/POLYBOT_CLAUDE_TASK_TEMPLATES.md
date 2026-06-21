# POLYBOT Claude Task Templates

These templates are reusable prompt structures for all Claude Code tasks in POLYBOT.

Every task must use one of these templates. Fill in all fields before handing the task to Claude Code.

ChatGPT is responsible for selecting the correct template and filling it out. Claude Code must not begin work on an incomplete template.

---

## Template 1: READ_ONLY_REVIEW

Use this when Claude Code should audit, inspect, or report — but never write code.

```
TASK MODE: READ_ONLY_REVIEW

Goal:
[One sentence: what Claude is auditing or reviewing.]

Context:
[Which phase this belongs to. What is known. What is uncertain. Why this audit is needed now.]

Allowed files to inspect (read-only):
- [List every file or directory Claude may read]
- [Use exact paths, not wildcards unless necessary]

Forbidden files (do not open):
- [List files that must not be read to avoid scope confusion]

Forbidden domains:
- Risk Governor
- Execution Cortex
- Exit Cortex
- Capital Allocator
- State Governor
- order/fill/position logic
- live/paper/shadow activation
- [add any task-specific forbidden areas]

Allowed commands:
- dir / ls
- grep / rg
- type / cat (read-only file inspection)
- git status (read-only)
- [list any additional read-only commands allowed]

Do NOT:
- modify any file
- run Docker
- apply migrations
- run tests
- run destructive commands
- enable PAPER / SHADOW_LIVE / LIVE
- create fake status

Required investigation:
[List the specific audit questions Claude must answer. Be explicit.]

Required output:

1. Current Reality — what exists today (code, routes, tables, tests, docs)
2. Missing Assets — what the audit question expects but does not find
3. Conflicts — any inconsistencies or contradictions found
4. Safety Concerns — any unexpected risky code or patterns
5. Suggested Implementation Boundary — what Claude Code could safely build next
6. Files to Inspect Next — if the audit is incomplete
7. Status: GREEN / YELLOW / RED

Status rules:
GREEN: Audit complete. Current reality is clear. No safety concerns found.
YELLOW: Audit partially complete. Some files missing or ambiguous. Safe to proceed with caution.
RED: Audit reveals unsafe behavior or missing critical context. Stop and report.

Can continue: YES / NO
```

---

## Template 2: SAFE_BUILD

Use this when Claude Code should create or modify low-risk files such as docs, tests, scripts, validators, or read-only APIs.

```
TASK MODE: SAFE_BUILD

Goal:
[One sentence: what Claude is building.]

Context:
[Which phase this belongs to. What already exists. What this task adds.]

Allowed files to create:
- [List new files Claude may create, with exact paths]

Allowed files to modify:
- [List existing files Claude may edit, with exact paths]

Forbidden files (do not touch):
- app/runtime/
- app/risk/
- app/execution/
- app/exit/
- app/capital/
- app/state/
- [add any task-specific forbidden paths]

Forbidden domains:
- Risk Governor core
- Execution Cortex
- Exit Cortex
- Capital Allocator
- State Governor
- order/fill/position logic
- live/paper/shadow activation
- production DB migrations
- secrets/env vars

Do NOT:
- modify forbidden files
- apply migrations
- enable PAPER / SHADOW_LIVE / LIVE
- create fake dashboard data
- bypass State Governor or Risk Gate
- create orders, fills, or positions

Required investigation before building:
- [List docs to read before starting]
- [List existing files to inspect for current state]

Required implementation:
[Describe exactly what Claude must build. Be specific about fields, endpoints, methods, return formats.]

Tests required:
- [List required test cases]
- [List test file names]
- [List exact test command]

Verification:
- [List verification commands to run after implementation]
- [State what a passing result looks like]

Final output format:
1. Files created
2. Files changed
3. Implementation summary
4. Tests run and exact results
5. Safety checklist
6. Remaining risks
7. Status: GREEN / YELLOW / RED
8. Can continue: YES / NO

Status rules:
GREEN: Required files created/modified. Tests pass. mock_data=false. No forbidden files touched.
YELLOW: Implementation complete but tests skipped or partial. Or: one minor gap remains but safety is intact.
RED: Tests failed. Forbidden file touched. Fake data introduced. Order/fill/position created. Safety unclear.
```

---

## Template 3: SCOPED_FIX

Use this when Claude Code should fix one specific, defined bug in a non-trading file.

```
TASK MODE: SCOPED_FIX

Goal:
[One sentence: exactly what bug is being fixed.]

Context:
[What is broken. What the expected behavior is. What evidence proves the bug exists.]

Bug location:
- File: [exact file path]
- Function/method: [exact name]
- Line numbers (approximate): [if known]

Root cause (if known):
[What is causing the bug.]

Allowed files to modify:
- [Exact list — typically 1-3 files for a scoped fix]

Forbidden files (do not touch):
- [All other files — list them explicitly if needed]
- [Especially: any trading, risk, execution, exit, capital, state files]

Forbidden domains:
- [Same as SAFE_BUILD — Risk, Execution, Exit, Capital, State Governor, order/fill/position]

Do NOT:
- refactor surrounding code
- redesign the function beyond the fix
- add features beyond the fix
- modify files outside the allowed list

Required implementation:
1. Reproduce or confirm the bug from existing evidence.
2. Apply the minimal fix.
3. Update or add one targeted test that covers the fixed behavior.
4. Run the test and report the exact result.

Tests required:
- [Name the specific test or test update needed]
- [Exact command to run it]

Verification:
- [Command to confirm the fix works]
- [What the passing state looks like]

Final output format:
1. Bug confirmed (YES / NO / INFERRED)
2. Root cause found
3. Files changed
4. Fix description
5. Tests run and exact results
6. Safety checklist
7. Remaining risks
8. Status: GREEN / YELLOW / RED
9. Can continue: YES / NO

Status rules:
GREEN: Bug fixed. Test passes. No forbidden files touched. No scope drift.
YELLOW: Fix applied but test only partially covers the behavior. Or: bug required touching one additional file within safe scope.
RED: Fix required touching forbidden files. Tests fail. Safety unclear. Scope exceeded.
```

---

## Template 4: CONTROLLED_FEATURE

Use this when Claude Code should build a small, well-scoped feature that does not touch trading paths.

```
TASK MODE: CONTROLLED_FEATURE

Goal:
[One sentence: what feature is being built.]

Context:
[Which phase. What already exists. Why this feature is needed. What it should NOT do.]

Important audit result:
[Summary of what the pre-build audit found. What is already implemented. What is missing.]

Do NOT rebuild:
[List any existing logic that should not be duplicated or replaced.]

Allowed files to create:
- [Exact list of new files]

Allowed files to modify:
- [Exact list of existing files that may be changed]

Potentially allowed only after explicit self-check:
- [Files that may be needed but require Claude to confirm safety before editing]

Forbidden files (do not touch):
- [All trading, risk, execution, exit, capital, state files]
- [Any file not in the allowed lists above]

Do NOT:
- force link any signal
- fake any market_id or signal data
- create market links without evidence
- auto-apply suggestions
- modify brain/coordinator/risk/execution/exit/capital/state logic
- create orders/fills/positions
- enable PAPER / SHADOW_LIVE / LIVE
- apply migrations
- create fake dashboard data
- bypass State Governor or Risk Gate

Required investigation before building:
1. [Read these docs]
2. [Read these existing files]
3. [Confirm what already exists and what is truly missing]

Required implementation:
[Describe each component to build. Be specific. Field names, function names, DB table names, route paths.]

1. [Component A]
2. [Component B]
3. [Component C]

Tests required:
- [List all required test cases]
- [List all test file names]
- [Exact test command]

Production-safe verification:
- [List API calls or SQL reads to confirm real production state]

Final output format:
1. Current reality found
2. Files changed
3. Files created
4. Implementation summary
5. API/dashboard truth summary
6. Tests run and exact results
7. Safety checklist
8. Remaining risks
9. Status: GREEN / YELLOW / RED
10. Can continue: YES / NO

Status rules:
GREEN: All required outputs present. Tests pass. mock_data=false. No forbidden files touched. No order/fill/position created.
YELLOW: Implementation complete. Tests pass. Scheduler/runtime wiring deferred. Remaining gaps documented. Safety intact.
RED: Tests fail. Fake data introduced. Forbidden file touched. Order/fill/position created. Safety unclear.
```

---

## Template 5: OUTPUT_REVIEW

Use this when Claude Code should review the output of a previous Claude Code or Codex build — reading only, no changes.

```
TASK MODE: OUTPUT_REVIEW

Goal:
[One sentence: what output is being reviewed and why.]

Context:
[Which phase this belongs to. Which agent produced the output. What the reviewer should look for.]

Output to review:
- [Build report path: docs/...]
- [Test results: exact results from the last run]
- [Files changed: list from the build report]
- [API endpoints: list from the build report]

Allowed files to inspect (read-only):
- [List every file or directory the reviewer may read]

Forbidden files (do not open):
- [Any files outside the review scope]

Do NOT:
- modify any file
- add code
- run Docker
- apply migrations
- enable PAPER / SHADOW_LIVE / LIVE

Required review questions:
1. [Question 1 — e.g., "Does the implementation match the stated goal?"]
2. [Question 2 — e.g., "Are the tests actually testing the right behavior?"]
3. [Question 3 — e.g., "Is mock_data=false enforced everywhere?"]
4. [Question 4 — e.g., "Are any forbidden files mentioned in the build report?"]
5. [Question 5 — e.g., "Are remaining risks documented honestly?"]

Required output:

1. Review Summary — overall assessment of the output
2. Findings — specific issues, gaps, or concerns found
3. Confirmed Correct — list of items that are correct and complete
4. Safety Assessment — is the output safe to accept as-is?
5. Recommended Action — accept GREEN / escalate YELLOW / reject RED
6. Files that should be changed before accepting (if any)
7. Status: GREEN / YELLOW / RED
8. Can continue: YES / NO

Status rules:
GREEN: Output matches goal. Tests passed. Safety rules followed. No forbidden areas touched. Ready to accept.
YELLOW: Output mostly correct. One or more minor gaps. Safe to accept with documented remediation plan.
RED: Output contains unsafe code. Fake data. Forbidden area touched. Tests failed. Must not be accepted.
```

---

## Required Final Output Block

Every Claude Code task — regardless of template — must end with this complete output block.
A task is not complete if any section is missing.

```
1. Current reality found
   [What existed before this task started — relevant files, routes, tables, tests, docs]

2. Files created
   [Exact list with paths]

3. Files changed
   [Exact list with paths and one-line description of what changed]

4. Files deleted
   [Exact list, or "None"]

5. Commands run
   [Every shell command executed, with purpose]

6. Tests run
   [Test command(s) used, or "None — not required for this task type"]

7. Exact test results
   [N passed, M failed. List failing test names if any. Or "N/A"]

8. Safety checklist
   [ ] No forbidden files modified
   [ ] No forbidden domains touched
   [ ] No orders/fills/positions created
   [ ] No PAPER/SHADOW_LIVE/LIVE enabled
   [ ] No migrations applied without approval
   [ ] No secrets exposed
   [ ] No fake data introduced
   [ ] mock_data=false throughout (if applicable)

9. Remaining risks
   [Honest list of what is not yet resolved, what needs Codex, what needs ChatGPT decision]

10. Status: GREEN / YELLOW / RED
    [Claude's suggested status — advisory only. ChatGPT is the final judge.]

11. Can continue: YES / NO
    [Claude's recommendation on whether the next task can begin]
```

If Claude cannot provide any section, write "MISSING — [reason]" rather than omitting it.

This output is what ChatGPT reviews. See `docs/POLYBOT_CLAUDE_OUTPUT_REVIEW_PROTOCOL.md` for the full ChatGPT review checklist.

---

## Choosing the Right Template

| Situation | Template |
|---|---|
| Need to understand what currently exists before building | READ_ONLY_REVIEW |
| Building docs, tests, scripts, validators, read-only APIs | SAFE_BUILD |
| Fixing one specific bug in a safe file | SCOPED_FIX |
| Building a small non-trading feature | CONTROLLED_FEATURE |
| Reviewing a Codex or Claude Code build report | OUTPUT_REVIEW |

When in doubt, use READ_ONLY_REVIEW first. Never start SAFE_BUILD or CONTROLLED_FEATURE without a prior audit of what already exists.
