# POLYBOT Agent Context

## Project Identity

POLYBOT is a **24/7 Adaptive Asymmetric Money Engine** for prediction markets.

Core principle: **upside open, downside defined**. The system hunts measurable Edge. It does not chase every trade, and `NO_TRADE` is a first-class decision.

## Current Codebase Reality

This repository is a Python/FastAPI/Postgres monorepo. Current known assets include:

- FastAPI runtime with canonical entrypoint `app/main.py`.
- Canonical operator script `scripts/start_runtime.ps1`.
- `MarketService.refresh()` as the current central runtime cycle.
- Postgres phase schema and repository pattern through `DatabaseConnectionFactory`.
- Canonical Postgres-backed paper trading through `paper_*` tables.
- Dashboard API/query layer.
- Intelligence services, whale scoring, invalidation, advisory, and command-intent phases.
- V2.0 Core Runtime Foundation, when present: System State Governor, runtime modes, runtime routes, health truth, cycle ledger, and service health.

Known legacy:

- `app/stage3` SQLite paper trading is legacy/reference only.
- Postgres `paper_*` tables are canonical paper truth.

## Mandatory Runtime Modes

The canonical modes are:

- `DATA_ONLY`: collects and analyzes only.
- `PAPER`: simulates only through canonical Postgres paper trading.
- `SHADOW_LIVE`: computes live-like decisions but sends no real orders.
- `SMALL_LIVE`: requires certification, explicit permission, and strict limits.
- `ATTACK_MODE`: requires explicit Governor approval.
- `COOLDOWN`: reduces risk and blocks or limits new entries.
- `KILL`: blocks trading.

Never bypass the State Governor. Missing runtime state must never enable trading.

## Safety Rules

- Never enable live trading unless explicitly requested by the current task.
- Never loosen safety checks to pass tests.
- Never print or expose secrets.
- Never let `.env` silently enable live behavior in tests.
- Never bypass State Governor.
- Never send live orders in `DATA_ONLY`, `PAPER`, `SHADOW_LIVE`, `COOLDOWN`, or `KILL`.
- Every trading decision must pass mode check, risk check, and exit-plan check.
- Missing data means `NO_TRADE`.
- No entry without exit plan.
- No fake dashboard data.
- No broad unrelated refactors.

## Development Process

Every implementation phase must include, as relevant:

- DB tables and migrations.
- Repositories.
- Services.
- Contracts.
- Events.
- API.
- Dashboard truth.
- Tests.
- Docs.
- Smoke commands.
- Rollback notes.
- Build report.
- Definition of Done.

Use existing codebase patterns. Make small focused changes. Preserve useful existing assets and reports.

## Testing Requirements

Every implementation must run targeted tests. If touching runtime, safety, live, paper, scheduler, execution, or controls, also run relevant regression tests.

If tests fail, report exact failures and do not claim success. Distinguish phase-related failures from unrelated legacy or environment failures.

## Reporting Requirements

Every coding task must end with:

- Summary.
- Changed files.
- Migrations.
- Tests run.
- Results.
- Risks.
- What is complete.
- What is partial.
- Whether it is safe to proceed.

## Architecture Direction

Build toward:

- Event Bus / Neural Mesh.
- Hybrid AI Brain.
- Data Foundation.
- Intelligence Neurons.
- Market Memory V2.
- Opportunity Cortex.
- Strategy Engines.
- Capital Brain.
- Risk Governor.
- Execution Cortex.
- Exit Cortex.
- No-Trade Intelligence.
- Dashboard V2.
- Learning Loop.

Do not implement future phases unless explicitly asked.

## Agent Dispatch Rule

Before any implementation task, classify the task using `docs/POLYBOT_AGENT_DISPATCH_PROTOCOL.md`.

No prompt should be written before deciding:
- ChatGPT / Codex / Claude Code
- task mode
- risk level
- review requirements

ChatGPT review is always required.
Claude Code must refuse or mark RED if asked to touch forbidden core areas without explicit approval.

## Context Index

Read `docs/POLYBOT_CONTEXT_INDEX.md` first for the current context map.
