# POLYBOT Claude Direct Mode Protocol

Date: 2026-05-28
Status: ACTIVE — Git worktree is currently paused.

---

## 1. Purpose

Claude Code currently works directly inside the main project folder:

```
C:\Server\apps\polybot
```

This is called **Direct Mode**.

Direct Mode is in effect because Git worktree setup was attempted and paused due to operational friction. Until worktree is re-enabled, all Claude Code tasks must be executed inside the main repo with stricter scope controls than would otherwise be required.

Direct Mode is not a permanent state. Worktree can be revisited and re-enabled at any time when the team is ready.

---

## 2. Direct Mode Risk

When Claude Code works inside the main project folder:

- There is no branch isolation. Edits are made directly to the working tree.
- Mistakes in the wrong file affect the live codebase immediately.
- There is no automatic rollback path — only git restore or manual revert.
- Parallel Codex work and Claude Code work can conflict if not carefully coordinated.

Because of these risks, Direct Mode requires **stricter scope definition** than worktree mode for every Claude task.

The scope must be defined before Claude starts any work — not after.

---

## 3. Mandatory Before Every Claude Task

Every Claude Code task in Direct Mode must explicitly define all of the following before implementation begins:

```
TASK MODE:      READ_ONLY_REVIEW / SAFE_BUILD / SCOPED_FIX / CONTROLLED_FEATURE / OUTPUT_REVIEW
GOAL:           [one sentence — what Claude will accomplish]
CONTEXT:        [why this task is needed, what phase it belongs to]
ALLOWED FILES:  [exact list of files Claude may read and write]
FORBIDDEN FILES: [exact list of files Claude must not touch]
FORBIDDEN DOMAINS: [Risk Governor / Execution / Exit / Capital / State / trading path / etc.]
TESTS ALLOWED:  YES / NO — [which test files, which commands]
COMMANDS ALLOWED: [specific shell commands Claude may run, if any]
FINAL OUTPUT FORMAT: [what Claude must return]
STATUS RULE:    GREEN / YELLOW / RED — [what each means for this task]
```

No exceptions. If a task arrives without this block, Claude must request it from ChatGPT before starting.

---

## 4. Allowed Direct Mode Tasks

Claude Code may build or modify the following in Direct Mode:

- Documentation (`docs/`)
- Skills (`.claude/skills/`)
- Audit and review reports
- Read-only diagnostics
- Tests (`tests/`)
- Scripts (`scripts/`)
- Read-only API endpoints
- Dashboard truth panels
- Signal quality validators
- Link coverage auditing
- Lineage coverage auditing
- Producer health checks
- Build reports and completion reports
- Small scoped bug fixes in non-trading paths
- Non-trading feature additions

All work must stay within the explicit allowed file list for the task. Being in the allowed category does not override the allowed file list.

---

## 5. Forbidden Direct Mode Tasks Without Explicit Approval

Claude Code must not touch the following domains without explicit written approval from ChatGPT in the task definition:

| Domain | Examples |
|---|---|
| Risk Governor | Risk Gate, risk parameters, NO_TRADE core |
| Execution Cortex | Order creation, execution routing |
| Exit Cortex | Exit logic, fill closure, stop handling |
| Capital Allocator | Sizing, budget allocation, reinvest logic |
| State Governor | Mode transitions, kill switch |
| Order/Fill/Position logic | Any code path that creates or closes trades |
| Live/Paper/Shadow activation | Mode enable, mode unlock |
| Production DB migrations | Any migration touching trading or live tables |
| Secrets and environment variables | `.env`, `config.py` credential fields |
| Destructive scripts | DROP, DELETE, TRUNCATE, rm -rf |

If Claude Code encounters any of these during a task, it must:

1. Stop immediately.
2. Report what it found.
3. Mark the task RED.
4. Wait for ChatGPT to confirm before proceeding.

---

## 6. Git/Worktree Status

**Current state: Git worktree is PAUSED.**

Worktree was attempted but created friction in the workflow. It is not currently in use.

All Claude Code work is being done directly in:
```
C:\Server\apps\polybot
```

Worktree remains the recommended isolation strategy for risky, multi-file, or long-running tasks. It can and should be revisited when the team is ready to re-enable it.

Until worktree is re-enabled:

- Every Claude task must be tightly scoped with an explicit allowed file list.
- Claude must not write to files outside the allowed list for the active task.
- If a task requires writing to many files across different domains, it should be broken into smaller tasks or escalated to Codex.
- ChatGPT must review all Claude output before the next task begins.

**When to re-enable worktree:**
- When Codex and Claude Code need to work on the repo simultaneously.
- When a task modifies more than 5 files across domains.
- When a task is risky enough to benefit from branch isolation before review.

---

## 7. Required Review

Every Claude Code output in Direct Mode must be reviewed by ChatGPT before the next task begins.

There are no exceptions. Direct Mode has no branch isolation — every edit is live. This makes review even more critical than in worktree mode.

ChatGPT review is not optional even when Claude output is GREEN.

Claude may proceed to the next step only after ChatGPT confirms:
- The output is acceptable (GREEN or acceptable YELLOW).
- The next task scope is defined.
- No unintended side effects were introduced.

### Claude's Status Is Advisory

Claude's suggested GREEN / YELLOW / RED at the end of each task is **advisory only**. It is not the final verdict.

ChatGPT is the final judge. ChatGPT may confirm, upgrade, or downgrade Claude's suggested status.

Claude must never begin the next task based on its own status assessment alone.

### Review Protocol Reference

Use the standard ChatGPT review checklist in `docs/POLYBOT_CLAUDE_OUTPUT_REVIEW_PROTOCOL.md`.

That protocol defines:
- What Claude must produce at the end of every task (11 required sections).
- What ChatGPT must check before issuing a verdict (6 checklist areas).
- Evidence requirements (what counts as proof vs unsupported claim).
- Hard RED conditions that block continuation.
- YELLOW conditions that require explicit ChatGPT approval before continuing.
- The standard ChatGPT verdict format.

The compact status rulebook is at `docs/POLYBOT_CLAUDE_GREEN_YELLOW_RED_RULES.md`.

---

## 8. Emergency Stop Rule

If Claude Code at any point:
- Writes to a file outside the allowed file list for the active task.
- Touches a forbidden domain (Risk, Execution, Exit, Capital, State Governor, order/fill/position, live/paper/shadow).
- Applies a migration without explicit approval.
- Runs a destructive command.
- Exposes secrets.
- Introduces fake dashboard data.

Then:
- The task is immediately RED.
- All further work stops.
- Claude reports exactly what happened and which files were touched.
- No cleanup, revert, or further action is taken by Claude without ChatGPT's instruction.
- ChatGPT decides the remediation path.

**An Emergency Stop is not a failure of judgment — it is the correct response.**

---

## 9. Direct Mode vs Worktree Mode Summary

| Aspect | Direct Mode (current) | Worktree Mode (paused) |
|---|---|---|
| Branch isolation | None | Full — separate branch per task |
| Rollback path | Manual git restore | Delete worktree |
| Parallel agent safety | Requires coordination | Built-in isolation |
| Scope requirement | Strict — explicit allowed file list | Strict — but branch bounds scope |
| Risk of conflict | Higher | Lower |
| Use case | Tight, well-defined single tasks | Multi-file, multi-session, parallel work |
| ChatGPT review | Always required | Always required |
