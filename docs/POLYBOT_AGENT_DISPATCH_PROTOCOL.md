# POLYBOT Agent Dispatch Protocol

## 1. Purpose

Every POLYBOT task must be classified before any prompt is written or any implementation plan is started.

No agent should begin coding, planning, or generating prompts without first completing the classification below.
This protocol is permanent and applies to every task, every session, every agent.

---

## 2. Role Split

### ChatGPT — Commander / Architect / Dispatcher / Prompt Writer / Judge

- Defines phases and goals.
- Writes all implementation prompts.
- Decides which agent executes each task.
- Reviews final output and issues GREEN / YELLOW / RED.
- Is the final decision maker on all architecture and safety questions.
- Cannot be replaced by Claude Chat in normal workflow.

### Codex — Main Builder

- Owns all dangerous, production-critical, and core architecture work.
- Receives fully written prompts from ChatGPT.
- Should not be used for low-risk tasks that Claude Code can safely handle.

### Claude Code — Secondary Builder

- Owns scoped, testable, non-critical implementation.
- Reads AGENTS.md, POLYBOT_CLAUDE_WORKFLOW.md, and this protocol before starting.
- Must refuse or self-report RED if asked to touch forbidden core areas without explicit approval.
- Should proactively identify tasks within its safe scope and reduce Codex dependency.
- Operates in a defined task mode with explicit allowed and forbidden files every time.

### Claude Chat — Backup / Second Opinion Only

- Not part of the normal POLYBOT workflow.
- Use only for:
  - Rare second opinion on architectural questions.
  - Backup if ChatGPT is unavailable.
  - Optional external architectural comparison.
- Must never become a planning or judgment layer.
- Output from Claude Chat must be reviewed by ChatGPT before acting on it.

---

## 2b. Direct Mode Safety Notice

**Claude Code is currently operating in Direct Mode** (as of 2026-05-28).

Git worktree is paused. Claude Code works directly inside `C:\Server\apps\polybot` without branch isolation.

This increases the importance of tight task scope. Every task dispatched to Claude Code in Direct Mode must:

1. Include an explicit allowed file list (not just a category — exact paths).
2. Include an explicit forbidden file list.
3. Define the task mode (READ_ONLY_REVIEW / SAFE_BUILD / SCOPED_FIX / CONTROLLED_FEATURE / OUTPUT_REVIEW).
4. Be reviewed by ChatGPT before the next task begins.

If a task requires working across more than 5 files in different domains, or involves any risk domain, do not dispatch to Claude Code in Direct Mode. Assign to Codex or wait for worktree to be re-enabled.

See `docs/POLYBOT_CLAUDE_DIRECT_MODE_PROTOCOL.md` for the full Direct Mode protocol.
See `docs/POLYBOT_CLAUDE_TASK_TEMPLATES.md` for ready-to-use task templates.

---

## 2c. Output Review Rule

**ChatGPT review is mandatory after every Claude Code task, without exception.**

- Every Claude task ends with Claude's suggested GREEN / YELLOW / RED status.
- Claude's status is advisory only. ChatGPT is the final judge.
- No next task begins until ChatGPT issues a verdict on the current task.
- ChatGPT may confirm, upgrade, or downgrade Claude's suggested status.

See `docs/POLYBOT_CLAUDE_OUTPUT_REVIEW_PROTOCOL.md` for the full review checklist and verdict format.

---

## 3. Mandatory Classification Before Every Task

Before any prompt is written or implementation begins, fill out this block:

```
Recommended executor:  ChatGPT / Codex / Claude Code
Task mode:             PLANNING / SAFE_BUILD / READ_ONLY_REVIEW / SCOPED_FIX / CONTROLLED_FEATURE / CORE_BUILD
Risk level:            LOW / MEDIUM / HIGH
Codex review needed:   YES / NO
ChatGPT review needed: YES  (always YES)
Reason:                [one line]
```

**ChatGPT review is always required.** There is no task where ChatGPT review is optional.

---

## 4. Codex Task Types

Codex owns work that can affect money, trades, safety, or system state:

- Core architecture design and implementation.
- State Governor core.
- Risk Governor core.
- Execution Cortex.
- Exit Cortex.
- Capital Allocator.
- Order, fill, and position creation logic.
- Live, Shadow Live, and Paper activation logic.
- Dangerous DB migrations (schema changes to trading tables).
- Production-critical runtime fixes.
- Any code path that produces or blocks a real trade.
- Any change that could make the system enter PAPER, SHADOW_LIVE, or LIVE unexpectedly.

---

## 5. Claude Code Task Types

Claude Code owns low-risk, scoped, testable work:

- Documentation (docs/).
- Tests (tests/).
- Scripts (scripts/).
- Diagnostics and health checks.
- Dashboard truth panels (read-only APIs, display fields).
- Read-only API endpoints.
- Validators and parsers.
- Signal quality scoring.
- Link coverage auditing and hardening.
- Lineage coverage auditing and hardening.
- Dry-run provenance scripts.
- Producer health checks.
- Mesh blockers dashboard.
- Build reports and audit reports.
- Small scoped bug fixes (non-trading path).
- Non-trading feature additions.

---

## 6. Claude Chat Rule

**Default: do not use Claude Chat in normal POLYBOT workflow.**

Claude Chat may be used only for:
- Rare second opinion on a hard architectural question.
- Backup when ChatGPT is unavailable.
- Optional comparison of external architectural patterns.

Claude Chat output is never authoritative. ChatGPT must review any Claude Chat output before it influences the project.

---

## 7. Decision Questions

Before assigning any task, answer these questions:

1. Does this touch orders, fills, or positions?
2. Does this touch Risk, Execution, Exit, Capital, or State Governor?
3. Can a failure in this work create unsafe trading behavior?
4. Is this only docs, tests, dashboard, diagnostics, or a read-only API?
5. Can it be verified without enabling PAPER or LIVE?
6. Can Claude Code complete it inside a limited, explicitly defined file scope?
7. Does Codex need to review the result before it is merged?

If the answer to questions 1–3 is YES → assign to Codex.
If the answer to questions 4–6 is YES → assign to Claude Code.
If uncertain → assign to Codex or ask ChatGPT.

---

## 8. Task Classification Matrix

| Task Type                    | Default Executor | Allowed Mode          | Review Required       | Examples                                      |
|------------------------------|------------------|-----------------------|-----------------------|-----------------------------------------------|
| Core Runtime                 | Codex            | CORE_BUILD            | Codex + ChatGPT       | main loop, startup, cycle ledger              |
| State Governor               | Codex            | CORE_BUILD            | Codex + ChatGPT       | mode transitions, kill switch                 |
| Risk                         | Codex            | CORE_BUILD            | Codex + ChatGPT       | Risk Gate, risk parameters, NO_TRADE core     |
| Execution                    | Codex            | CORE_BUILD            | Codex + ChatGPT       | order creation, execution cortex              |
| Exit                         | Codex            | CORE_BUILD            | Codex + ChatGPT       | exit logic, fill closure                      |
| Capital                      | Codex            | CORE_BUILD            | Codex + ChatGPT       | capital allocator, sizing                     |
| DB Migrations (dangerous)    | Codex            | CORE_BUILD            | Codex + ChatGPT       | trading table schema changes                  |
| Dashboard                    | Claude Code      | SAFE_BUILD            | ChatGPT               | dashboard panels, truth fields, read-only API |
| Tests                        | Claude Code      | SAFE_BUILD            | ChatGPT               | pytest files, test contracts                  |
| Docs                         | Claude Code      | SAFE_BUILD            | ChatGPT               | protocol docs, workflow docs, build reports   |
| Diagnostics                  | Claude Code      | READ_ONLY_REVIEW      | ChatGPT               | health checks, audit scripts                  |
| API read-only                | Claude Code      | SAFE_BUILD            | ChatGPT               | /health, /status, /audit endpoints            |
| Signal Quality Contract      | Claude Code      | SAFE_BUILD            | ChatGPT               | signal schema, field validation               |
| Signal Processing State      | Claude Code      | SAFE_BUILD            | ChatGPT               | signal state tracking, staleness checks       |
| Link Coverage Hardening      | Claude Code      | SAFE_BUILD            | ChatGPT               | link field coverage audit and repair          |
| Lineage Coverage Hardening   | Claude Code      | SAFE_BUILD            | ChatGPT               | lineage field coverage audit and repair       |
| Dry Run Provenance           | Claude Code      | SAFE_BUILD            | ChatGPT               | dry-run logging, provenance scripts           |
| Mesh Blockers Dashboard      | Claude Code      | SAFE_BUILD            | ChatGPT               | blocker panel, mesh health display            |
| Producer Health Accuracy     | Claude Code      | SAFE_BUILD            | ChatGPT               | producer status, freshness truth              |
| Market Technical Truth       | Split            | SAFE_BUILD / CORE_BUILD | ChatGPT + Codex if needed | Claude: diagnostics; Codex: if runtime orderbook changes needed |
| Orderbook Snapshots          | Split            | SAFE_BUILD / CORE_BUILD | ChatGPT + Codex if needed | Claude: read/display; Codex: if write path changes |
| Paper Readiness Evidence     | Split            | SAFE_BUILD / CORE_BUILD | ChatGPT + Codex if needed | Claude: scripts/diagnostics; Codex: if runtime core fails |
| Paper / Shadow / Live        | Codex            | CORE_BUILD            | Codex + ChatGPT       | mode activation, order routing                |

---

## 9. Hard Boundaries for Claude Code

Claude Code must not touch the following without explicit approval from ChatGPT:

- Risk Governor core.
- Execution Cortex core.
- Exit Cortex core.
- Capital Allocator core.
- State Governor core.
- Order, fill, and position creation logic.
- Live, Shadow Live, or Paper activation logic.
- Production migrations (especially trading table schema changes).
- Secrets or environment variable handling.
- Destructive scripts (DROP, DELETE, TRUNCATE).

If Claude Code is asked to touch any of these without an explicit approval statement in the task, it must:
1. Stop immediately.
2. Report the boundary violation.
3. Mark the task RED.
4. Ask ChatGPT to confirm before proceeding.

---

## 10. GREEN / YELLOW / RED Rules

### GREEN

- Task was classified correctly before prompts were written.
- Correct executor was assigned.
- All work stayed within the defined scope.
- No forbidden files were touched.
- Tests passed or were not required for this task type.
- Safety rules were not loosened.
- No fake data was introduced.
- ChatGPT reviewed the output.

### YELLOW

- Classification was done but scope drift occurred.
- Some required tests are missing.
- A file outside the allowed list was touched but it is not a hard boundary violation.
- ChatGPT review is pending.
- One minor rule was stretched but safety is not at risk.

### RED

- No classification was done before implementation started.
- A forbidden core file was touched without explicit approval.
- Live, Shadow Live, or Paper was activated or unblocked without approval.
- Safety checks were loosened or bypassed.
- Fake dashboard data was introduced.
- Tests failed on safety or core logic.
- Secrets were exposed.
- State Governor or Risk Gate was bypassed.

---

## 11. Examples from Current Phase

### Signal Quality Contract
- Executor: Claude Code
- Mode: SAFE_BUILD
- Risk: LOW
- Codex review: NO
- Reason: defines signal field schema and validation — no trading logic, no core changes.

### Signal Processing State
- Executor: Claude Code
- Mode: SAFE_BUILD
- Risk: LOW
- Codex review: NO
- Reason: tracks signal state for mesh monitoring — read-side only, no execution impact.

### Link Coverage Hardening
- Executor: Claude Code
- Mode: SAFE_BUILD
- Risk: LOW
- Codex review: NO
- Reason: audits and repairs signal link field coverage — no trading path involved.

### Lineage Coverage Hardening
- Executor: Claude Code
- Mode: SAFE_BUILD
- Risk: LOW
- Codex review: NO
- Reason: audits and repairs signal lineage coverage — diagnostic and docs layer only.

### Dry Run Provenance
- Executor: Claude Code
- Mode: SAFE_BUILD
- Risk: LOW
- Codex review: NO
- Reason: logging and provenance for dry-run cycles — no live execution path.

### Mesh Blockers Dashboard
- Executor: Claude Code
- Mode: SAFE_BUILD
- Risk: LOW
- Codex review: NO
- Reason: display panel for blockers — read-only API and dashboard fields only.

### Producer Health Accuracy
- Executor: Claude Code
- Mode: SAFE_BUILD
- Risk: LOW
- Codex review: NO
- Reason: producer freshness checks and health truth — diagnostic layer, no trading impact.

### Market Technical Truth
- Executor: Split — Claude Code first, Codex only if runtime orderbook changes are needed.
- Claude mode: SAFE_BUILD (diagnostics, display, validation)
- Codex mode: CORE_BUILD (only if orderbook write path or core runtime changes required)
- Risk: MEDIUM (escalates if Codex path is needed)
- Reason: most of the truth surfacing is safe; only core orderbook write path needs Codex.

### Risk + No-Trade Core
- Executor: Codex
- Mode: CORE_BUILD
- Risk: HIGH
- Codex review: YES
- Reason: directly touches Risk Governor and NO_TRADE decision logic — hard Codex boundary.

### Exit Foundation
- Executor: Codex
- Mode: CORE_BUILD
- Risk: HIGH
- Codex review: YES
- Reason: directly touches Exit Cortex — hard Codex boundary.

### Paper Readiness Evidence Loop
- Executor: Split — Claude Code for diagnostics and scripts, Codex only if runtime core fails verification.
- Claude mode: SAFE_BUILD (scripts, reports, evidence collection)
- Codex mode: CORE_BUILD (only if runtime fix is required)
- Risk: MEDIUM
- Reason: evidence collection is safe; only a discovered runtime failure escalates to Codex.
