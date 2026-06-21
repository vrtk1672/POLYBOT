# Research Priority Watchlist Stage 4.5 Report

## Purpose

Stage 4.5 adds a DATA_ONLY Research Priority Watchlist and Adaptive Refresh Scheduler projection for POLYBOT's Money Machine Core.

The goal is to focus research effort on markets with the strongest current evidence without activating Paper Simulation, Shadow, Live, Full Monitor Run, or execution.

## Money Machine Fit

Previous stages created market memory, source event memory, event-to-market recall, targeted revalidation, and proactive research seeds. Stage 4.5 turns those inputs into a market-level priority brain:

- Which markets are hot now.
- Which markets deserve more frequent refresh recommendations.
- Which markets can be monitored less aggressively.
- Which markets are archived or dormant without deletion.

## Existing Priority / Scheduler Audit

- `market_universe_memory.research_priority` already existed, but it was coarse market-memory metadata, not an adaptive scheduler profile.
- `SourceRefreshOrchestrator` used fixed TTL/source cadence registrations.
- Stage 3 targeted revalidation and Stage 4 proactive candidate generation had bounded DATA_ONLY hooks, but no priority-driven due-market surface.
- Opportunity score, paper actionability, source event memory, targeted revalidation, and proactive candidate generation already exposed enough market evidence to compute priority deterministically.
- No existing adaptive watchlist table was present, so a non-destructive migration was required.

## Architecture

Added `ResearchPriorityWatchlistService`:

- Reads existing DATA_ONLY evidence from market memory, source event links, targeted revalidation, proactive candidate seeds, opportunity scoring, and paper observation metadata.
- Computes one row per market.
- Stores priority band, priority score, cadence, next due time, reasons, demotions, required upgrades, score components, and evidence inputs.
- Records refresh runs and safety deltas.
- Does not call execution, Paper Simulation, Shadow, Live, or Full Monitor Run.

Scheduler behavior is recommendation-only:

- The service computes due state and cadence metadata.
- The source-refresh orchestrator refreshes the watchlist projection during SYSTEM ON.
- It does not directly perform deep refresh loops or execution work.

## Watchlist Data Model

Migration: `app/db/migrations/0137_research_priority_watchlist.sql`

Tables:

- `research_priority_watchlist`
- `research_priority_watchlist_runs`

Key fields:

- `priority_band`
- `priority_score`
- `refresh_cadence_seconds`
- `next_refresh_due_at`
- `scheduler_state`
- recent event/revalidation/seed counts
- liquidity/spread/volume/movement/payout states
- paper observation and full paper interest counts
- priority reasons, demotion reasons, required upgrades
- deterministic score components

## Priority Score Formula

`priority_score = event_heat + revalidation + candidate_seed + opportunity + liquidity + spread + volume + movement + closing_soon + paper_observation + thesis_edge - stale - identity_problem - token_problem - low_liquidity - repeated_no_signal`

The score is clamped to `0-100`.

No AI-generated evidence, fake liquidity, fake volume, or fake score is used.

## Band Rules

- `HIGH`: score >= 60, active market, usable liquidity, and recent direct/likely events or candidate seeds.
- `MEDIUM`: score >= 35.
- `LOW`: score >= 12 or demoted by token/identity issues.
- `DORMANT`: active but no meaningful signal heat.
- `ARCHIVED`: closed/resolved/archived terminal state.

Closed and dormant markets are retained, not deleted.

## Refresh Cadence Policy

- `HIGH`: 300 seconds.
- `MEDIUM`: 900 seconds.
- `LOW`: 3600 seconds.
- `DORMANT`: 21600 seconds.
- `ARCHIVED`: no active refresh.

The due endpoint exposes candidates for future scheduler consumers. This stage does not hammer external APIs.

## API Endpoints

Added:

- `GET /dashboard/api/v2/control/research-priority-watchlist`
- `POST /dashboard/api/v2/control/research-priority-watchlist/refresh`
- `GET /dashboard/api/v2/control/research-priority-watchlist/by-market`
- `GET /dashboard/api/v2/control/research-priority-watchlist/due`

Updated read-only visibility:

- market universe memory
- source event memory
- targeted market revalidation
- proactive candidate generation
- trade opportunity score
- paper actionability
- decision propagation trace
- source refresh orchestrator registry/status

## Tests Run

Focused:

`.venv\Scripts\python.exe -m pytest tests/test_research_priority_watchlist.py tests/test_research_priority_scoring.py tests/test_research_priority_scheduler.py tests/test_research_priority_integration_surfaces.py -q`

Result: `18 passed`

Related:

`.venv\Scripts\python.exe -m pytest tests/test_proactive_candidate_generation.py tests/test_targeted_market_revalidation.py tests/test_source_event_memory.py tests/test_market_universe_memory.py tests/test_trade_opportunity_scoring.py -q`

Result: `5 passed, 12 skipped`

Broad:

`.venv\Scripts\python.exe -m pytest tests -q -k "research_priority or watchlist or scheduler or proactive_candidate or targeted_market_revalidation or market_universe or source_event_memory or opportunity_score or paper_actionability"`

Result: `51 passed, 35 skipped, 2128 deselected`

Compile:

`.venv\Scripts\python.exe -m compileall app tests`

Result: passed.

## Deployment

Commands run:

- `docker compose build api`
- `docker compose build migrate`
- `docker compose run --rm migrate`
- `docker compose up -d --no-deps api`

Migration applied:

- `0137_research_priority_watchlist.sql`

Final API health:

- `/healthz`: OK.
- `/runtime/health`: `SAFE_STOPPED`, `runtime=STOPPED`, `system_power=OFF`.

## DATA_ONLY Verification

Manual Stage 4.5 refresh result:

- Watchlist rows: 14
- HIGH: 1
- MEDIUM: 10
- LOW: 3
- DORMANT: 0
- ARCHIVED: 0
- Due now: 0
- Average score: 55.57

Controlled SYSTEM ON verification:

- SYSTEM ON accepted in DATA_ONLY.
- Paper Simulation remained OFF.
- Supervisor completed 4 DATA_ONLY cycles.
- Source refresh orchestrator completed safely.
- SYSTEM OFF cleanup accepted.

Final watchlist counts after SYSTEM OFF:

- Watchlist rows: 14
- HIGH: 3
- MEDIUM: 8
- LOW: 3
- DORMANT: 0
- ARCHIVED: 0
- Due now: 0
- Average score: 58.86

Top HIGH markets:

- `2365093`: score 98, liquidity GOOD, spread TIGHT, 15 likely links, 8 recent seeds.
- `691547`: score 85, liquidity MEDIUM, spread MEDIUM, 82 direct links, 176 likely links, 260 recent seeds.
- `2354064`: score 79, liquidity MEDIUM, spread MEDIUM, 13 likely links, 2 recent seeds.

Research-only proactive candidate seeds increased during the DATA_ONLY source refresh path:

- Before controlled SYSTEM ON: 211
- After SYSTEM OFF: 308

These are Stage 4 research-only candidate seed rows, not execution candidates, paper intents, orders, fills, or positions.

## Safety Result

Paper artifact counts:

- `paper_intents`: 21 -> 21
- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12

Forbidden artifact counts:

- `live_orders`: 0 -> 0
- `positions`: 0 -> 0
- `shadow_orders`: 0 -> 0

Execution candidate tables checked:

- `fresh_candidate_seeds`: 22 -> 22
- `market_link_candidates`: 0 -> 0

No DB reset, volume reset, destructive DB action, threshold changes, fake evidence, Paper Simulation activation, Shadow activation, or Live activation occurred.

## Limitations

- The scheduler currently emits recommendations and due-market state; it does not perform priority-driven deep refresh execution.
- Existing `market_universe_memory.research_priority` remains a separate coarse projection. The new adaptive priority lives in `research_priority_watchlist`.
- Due count was 0 immediately after refresh because all markets were freshly recomputed.

## Recommended Next Stage

Proceed to:

Full Mesh Deep Inquiry for Proactive Candidate Seeds.

Use the Stage 4.5 watchlist to choose which proactive seeds and markets deserve deeper Mesh work first.
