# POLYBOT Claude Output Review Protocol

Date: 2026-05-28
Status: ACTIVE

Every Claude Code output must be reviewed by ChatGPT before the next task begins.
This protocol defines how that review works, what counts as evidence, and who has final authority.

---

## 1. Purpose

Claude Code works in Direct Mode inside the main repo without Git worktree isolation.
This means every edit is live. There is no branch to discard.

Because of this, every Claude output — whether docs, code, tests, or audits — must be reviewed by ChatGPT before Claude continues to the next task.

This protocol defines:
- What Claude must produce at the end of every task.
- What ChatGPT must check before issuing a verdict.
- What counts as evidence.
- When Codex review is also required.
- The exact format for the ChatGPT review verdict.

---

## 2. Review Authority

**ChatGPT is the final GREEN/YELLOW/RED judge.**

- Claude may suggest its own status at the end of every output.
- Claude's suggested status is **advisory only**. It is not binding.
- ChatGPT may confirm, upgrade, or downgrade Claude's status.
- ChatGPT may also override a Claude RED to YELLOW if the issue is minor and contained.

**Codex review is only required when:**
- Claude touched core runtime files.
- Claude touched the scheduler.
- Claude touched a DB migration.
- Claude touched State Governor, Risk Governor, Execution Cortex, Exit Cortex, or Capital Allocator.
- Claude changed any API behavior used by the trading path.
- Claude changed order, fill, or position logic.
- Claude made a broad refactor across multiple domains.
- Claude repeatedly failed tests.
- ChatGPT is unsure and requests a second opinion.

In all other cases, ChatGPT review alone is sufficient.

**Claude Chat is not a review authority.**
Claude Chat may be used as a rare second opinion on architectural questions, but it cannot issue a POLYBOT project verdict.

---

## 3. Required Claude Final Output

Every Claude Code task must end with a complete final output block.
A task is not complete if any of these sections is missing.

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
    [Claude's suggested status with one-line justification]

11. Can continue: YES / NO
    [Claude's recommendation on whether the next task can begin]
```

If Claude cannot provide any section, it must write "MISSING — [reason]" rather than omitting it.

---

## 4. ChatGPT Review Checklist

Before issuing a verdict, ChatGPT must verify each item below.

### 4a. Scope Compliance

- [ ] Did Claude stay inside the allowed file list for this task?
- [ ] Did Claude touch any file outside the allowed list?
- [ ] Did Claude touch any forbidden domain (Risk, Execution, Exit, Capital, State, trading path)?
- [ ] Did Claude modify `app/`, `tests/`, DB, runtime, or trading files when not allowed?

### 4b. Command Safety

- [ ] Did Claude run only the commands listed as allowed?
- [ ] Did Claude run any Docker rebuild, migration, or destructive command without approval?
- [ ] Did Claude run any command that modifies production state?

### 4c. Test Evidence

- [ ] If tests were required, did Claude provide exact test output?
- [ ] Did Claude name specific failing tests rather than claiming "tests passed"?
- [ ] Is the test count plausible (not suspiciously rounded)?
- [ ] Did Claude run against the correct test environment (not skipped with justification)?

### 4d. Data Integrity

- [ ] Did Claude create any fake dashboard data or mock data presented as truth?
- [ ] Did Claude hide any failure or error?
- [ ] Did Claude overclaim GREEN when evidence does not support it?
- [ ] Did Claude invent any market_id, signal_id, or other identifier?

### 4e. Safety

- [ ] Did Claude expose any secrets, credentials, or environment variables?
- [ ] Did Claude create or mutate any order, fill, or position record?
- [ ] Did Claude enable or unlock PAPER, SHADOW_LIVE, or LIVE?
- [ ] Did Claude apply a DB migration without explicit approval?
- [ ] Did Claude touch State Governor, Risk Governor, Execution Cortex, Exit Cortex, or Capital Allocator?
- [ ] Did Claude run a destructive command (DROP, DELETE, TRUNCATE, rm -rf)?

### 4f. Output Completeness

- [ ] Did Claude provide all 11 required output sections?
- [ ] Did Claude list remaining risks honestly?
- [ ] Did Claude refuse to show changed files?
- [ ] Is the output consistent (files claimed as changed match what was described)?

---

## 5. Evidence Requirements

The following count as acceptable evidence in a Claude output:

| Evidence Type | Acceptable For |
|---|---|
| Explicit file list with paths | Files created, changed, deleted |
| `git status` or file diff summary | Scope compliance, change confirmation |
| Exact command output (copy-pasted) | Commands run |
| `N passed, M failed in X.Xs` | Test results |
| Failing test names listed individually | Test failure evidence |
| API response (JSON snippet) | Endpoint behavior |
| Read-only DB count (`SELECT COUNT(*)`) | Signal/order/position counts |
| `Glob` or `file exists` check output | File existence |
| Build log excerpt | Docker/migration status |

The following do NOT count as evidence:

| Not Evidence | Why |
|---|---|
| "Tests passed" with no count or file names | Unverifiable claim |
| "Implementation complete" with no file list | No scope confirmation |
| "No orders created" with no DB count | Unverifiable safety claim |
| "Dashboard shows real data" with no endpoint call | No production proof |
| Status=GREEN with no supporting items | Overclaim |

---

## 6. No Evidence Rule

If Claude claims success without supporting evidence:

- If the claim is about non-safety behavior (docs created, files changed): mark **YELLOW**.
  - Require Claude to provide the file list before continuing.

- If the claim is about safety behavior (no orders created, no forbidden files touched): mark **YELLOW** at minimum.
  - If the unclaimed item is a hard safety boundary (order table, PAPER activation, Risk Governor), mark **RED**.
  - Do not continue until evidence is provided.

---

## 7. Hard RED Conditions

The task output is **RED** if any of the following is true:

| Condition | Description |
|---|---|
| Forbidden file modified | Any file outside the allowed list was written |
| Forbidden domain touched | Risk, Execution, Exit, Capital, State Governor edited |
| `app/` modified outside scope | Runtime, trading, or core code changed without approval |
| Tests required but not run | Task type required tests and Claude skipped them |
| Tests failed | Any failing test in the required test suite |
| Fake data introduced | mock data presented as production truth |
| market_id invented | Signal linked to a non-existent market |
| Forced linking | Signal linked without evidence |
| Orders/fills/positions created | Any record in paper_orders, shadow_orders, live_orders, fills, positions |
| PAPER/SHADOW_LIVE/LIVE enabled | Mode unlocked or activated |
| Secrets exposed | Credentials, env vars, API keys printed |
| Destructive command run | DROP, DELETE, TRUNCATE, rm -rf without approval |
| DB migration applied without approval | Any migration applied outside explicitly approved scope |
| Claude refuses to show changed files | Cannot confirm scope compliance |
| Safety checklist incomplete | Any safety item left blank or unaddressed |

A single RED condition makes the entire task RED. RED tasks must not continue until ChatGPT issues a remediation plan.

---

## 8. YELLOW Conditions

The task output is **YELLOW** if any of the following is true and no RED condition applies:

| Condition | Description |
|---|---|
| Runtime proof missing | Code changes correct but production endpoint not verified |
| Tests passed but production verification not done | Unit tests green but live system not checked |
| Docs updated but implementation not confirmed | Protocol doc written but runtime behavior not verified |
| Manual refresh still required | Scheduler not wired; analysis must be triggered manually |
| Known blockers remain documented | Required future Codex work identified but not yet done |
| Non-critical output incomplete | A secondary output was skipped with explanation |
| Status depends on future Codex work | Correct implementation but depends on an unresolved upstream decision |
| One minor file outside strict scope but not a hard boundary | Touched an adjacent non-trading file with low risk |
| Test count unexplained or partially covered | Tests ran but some categories not covered |

A YELLOW task may continue to the next step only if ChatGPT explicitly approves. ChatGPT may attach conditions (e.g., "proceed but verify endpoint before marking GREEN").

---

## 9. GREEN Conditions

The task output is **GREEN** only if **all** of the following are true:

| Condition | Must be true |
|---|---|
| Scope followed | All work stayed inside the allowed file list |
| All required files created/updated | Every file specified in the task goal exists |
| No forbidden domains touched | Risk, Execution, Exit, Capital, State Governor untouched |
| Tests passed | All required tests ran and passed (or tests not required for task type) |
| Safety checklist clean | All 8 safety checklist items confirmed |
| Remaining risks documented | Honest gap list present |
| No fake data | mock_data=false, no invented identifiers |
| No hidden failures | No errors suppressed or omitted |
| Evidence provided | File list, test output, or endpoint response as required |
| Can continue safely | No dependency on unresolved RED items |

GREEN does not mean perfect. It means the output is honest, evidence-backed, safe, and within scope.

---

## 10. Codex Review Triggers

Request Codex review before accepting a Claude output if:

- Claude touched `app/scheduler.py` or the main runtime loop.
- Claude touched any DB migration.
- Claude touched State Governor, Risk Governor, Execution Cortex, Exit Cortex, or Capital Allocator.
- Claude changed any API endpoint that feeds the trading path.
- Claude changed order, fill, or position creation logic.
- Claude made a refactor affecting more than 5 files across different domains.
- Claude failed the same test category more than once.
- ChatGPT is unsure whether a change is safe.

Codex review is in addition to ChatGPT review, not instead of it.

---

## 11. Standard ChatGPT Review Output

After reviewing a Claude output, ChatGPT should issue a verdict in this format:

```
## ChatGPT Review — [Task Name]

Verdict: GREEN / YELLOW / RED

### What passed
- [List items Claude did correctly]

### What failed or remains unclear
- [List gaps, missing evidence, or unsafe items]

### Safety status
- Forbidden files: [touched / not touched]
- Forbidden domains: [touched / not touched]
- Orders/fills/positions: [created / not created]
- PAPER/SHADOW_LIVE/LIVE: [enabled / not enabled]
- Secrets: [exposed / not exposed]
- Migrations: [applied / not applied]

### Test status
- Required: [YES / NO]
- Tests run: [N passed, M failed / not applicable]
- Failing tests: [list or none]

### Required fixes before continuing
- [List any items Claude must address before the next task starts]
- [Or: "None — task is clean"]

### Final status: GREEN / YELLOW / RED

### Can continue: YES / YES with conditions / NO
[Conditions if applicable]
```

---

## 12. Review Examples

### Example A: Docs-only SAFE_BUILD

Claude created `docs/POLYBOT_CLAUDE_DIRECT_MODE_PROTOCOL.md` and updated `CLAUDE.md`.

**ChatGPT checks:**
- Files created/changed match the allowed list? ✓
- No `app/`, `tests/`, DB, runtime files touched? ✓
- No tests required for docs-only task? ✓
- Remaining risks documented? ✓

**Verdict: GREEN** — Scope clean, docs complete, no safety concerns.

---

### Example B: Skill creation SAFE_BUILD

Claude created a new skill at `.claude/skills/polybot-new-skill/SKILL.md`.

**ChatGPT checks:**
- Skill file only — no app code? ✓
- Skill does not enable trading? ✓
- Skill scope matches the phase? ✓

**Verdict: GREEN** — Skills are docs-layer only. No safety concern.

---

### Example C: Link Coverage CONTROLLED_FEATURE

Claude implemented Link Coverage Hardening: migration, service, repository, routes, 5 test files. All 19 tests passed. `mock_data=false` confirmed. `stale_unlinked=68` documented as remaining risk.

**ChatGPT checks:**
- All files within allowed list? ✓
- No trading path touched? ✓
- Tests passed with exact count? ✓ (19/19)
- Remaining risks honest? ✓ (scheduler not wired, binding=0 documented)

**Verdict: YELLOW** — Tests passed, implementation complete, but production refresh is manual and stale signals remain. Safe to continue to next phase.

---

### Example D: Runtime scheduler change

Claude adds `analyze_recent_signals()` call to `app/scheduler.py`.

**ChatGPT checks:**
- Scheduler is a core runtime component? ✓ — triggers Codex review
- Does this affect `StateGovernor` behavior? Unclear.

**Verdict: Codex review required before accepting.** Do not continue until Codex confirms the scheduler change is safe.

---

### Example E: DB migration change

Claude applies migration `0071_new_table.sql` without explicit task approval.

**ChatGPT checks:**
- Task required migration? NO — migration was applied outside approved scope.

**Verdict: RED** — Migration applied without approval. Stop. Assess rollback with Codex.

---

### Example F: Tests failed

Claude ran 19 tests. 2 failed: `test_safety_no_orders` and `test_no_fake_market_id`.

**Verdict: RED** — Safety tests failed. Do not continue. Fix and re-run before next task.

---

### Example G: Forbidden file touched

Claude modified `app/runtime/state_governor.py` while implementing a dashboard endpoint.

**Verdict: RED** — State Governor is a hard forbidden boundary. Stop. Review all changes. Codex assessment required.

---

## 13. Protocol Maintenance

This protocol is reviewed when:
- A new task mode is introduced.
- A new agent (e.g., a new Codex model) joins the workflow.
- A RED incident reveals a gap in the checklist.
- Worktree is re-enabled (some rules may be relaxed under full isolation).

ChatGPT owns protocol updates. Claude Code may draft updates in SAFE_BUILD mode, subject to ChatGPT approval.
