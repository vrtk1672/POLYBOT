# POLYBOT Full System Micro Audit and Life Definition

**Date:** 2026-05-30  
**Executor:** Claude Code  
**Mode:** READ_ONLY_REVIEW + FULL_SYSTEM_MICRO_AUDIT + BRAIN_MESH_DIALOGUE_AUDIT  
**Risk:** MEDIUM  
**Status:** GREEN  
**Can continue:** YES

---

## 1. Executive Summary

POLYBOT is not yet a living Brain Mesh. It is a collection of expertly built components split across two disconnected processing paths that have never been wired together into a unified autonomous cycle.

**Path A — Data Collection Loop (ACTIVE, automatic, every ~70 seconds):**
- Fetches market data from Polymarket Gamma API
- Scores and ranks markets
- Persists market_snapshots, liquidity_snapshots, fee_snapshots, event_log entries
- Runs intelligence stage (news/whale/AI digest)
- Paper stage: BLOCKED — runtime DB mode is DATA_ONLY

**Path B — Neural Mesh Pipeline (BUILT, NOT WIRED, manual API only):**
- Producer Evidence → Brain Outputs → Coordinator Decisions → Position Thesis Profiles → Risk Decisions → Exit Plans → Paper Eligibility → Paper Intents
- Ran exactly ONCE ever via manual API trigger (2026-05-28)
- NOT called by the scheduler loop
- NOT called autonomously at any interval
- Zero output in the last 24 hours

The single biggest blocker is structural: **the neural mesh cycle is not wired into the automated runtime loop.** The second biggest blocker is the **DB mode being DATA_ONLY** which prevents the paper engine from executing even if the mesh were alive.

The system does not feel alive because: market data cycles every minute, but the Brain never wakes up to read it.

---

## 2. System ON / OFF Reality

### Current system_state (DB truth)
```
current_mode:        DATA_ONLY
kill_switch_active:  false
cooldown_active:     false
state_status:        ACTIVE
last_transition_at:  2026-05-20T23:20:29 UTC (first startup, never changed)
actor:               runtime_startup
reason:              safe startup default
```

### Docker-compose environment
```
POLYBOT_RUNTIME_MODE:     PAPER
POLYBOT_EXECUTION_BACKEND: paper
LIVE_TRADING_ENABLED:     false
LIVE_KILL_SWITCH:         true
```

### The mode mismatch
- Docker-compose env says PAPER
- DB state says DATA_ONLY
- `SafeStartupPolicy.initialize()` calls `ensure_initial_state()` which reads the existing DB row — it does NOT upgrade DATA_ONLY to PAPER based on the env var
- The env var is only used in the legacy `canonical_runtime_mode()` function for `RuntimePaperTradingService._execution_mode`
- The orchestrator uses the DB state to gate all stages

### DATA_ONLY permissions
```
can_collect_data:       true   ← Scanner runs
can_run_intelligence:   true   ← Intelligence stage runs
can_run_paper_engine:   false  ← Paper stage BLOCKED
can_generate_signals:   false
can_open_paper_positions: false
max_risk_multiplier:    0.0
```

### Does SYSTEM ON exist?
**NO.** There is no single action (API call, script, button) that:
1. Changes DB mode to PAPER
2. Starts the neural mesh loop autonomously
3. Starts fresh orderbook snapshot collection
4. Wires brain producers into the cycle
5. Creates paper intents from eligible candidates

There is a `/runtime/mode/request` endpoint that can change the DB mode, but changing it to PAPER would only allow the legacy paper execution path — it would NOT start the neural mesh or fix the signal/binding/orderbook blockers.

### Does SYSTEM OFF exist?
**PARTIAL.** No single action stops all POLYBOT activity. The scheduler has a stop mechanism (called by FastAPI lifespan shutdown), but:
- There is no "KILL all activity now" button that stops the scheduler loop immediately from outside
- `docker compose down` stops everything, but this is destructive infrastructure-level stop, not application-level
- The KILL mode in system_state blocks all runtime permissions, which would stop the paper engine if it were running

### Runtime cycle reality (last 5 cycles)
| Cycle ID | Mode | Scanner | Intelligence | Paper | Blocked |
|---|---|---|---|---|---|
| v2-20260529T210741 | DATA_ONLY | ✓ done | ✓ done | ✗ not started | false |
| v2-20260529T210633 | DATA_ONLY | ✓ done | ✓ done | ✗ not started | false |
| v2-20260529T210524 | DATA_ONLY | ✓ done | ✓ done | ✗ not started | false |
| v2-20260529T210415 | DATA_ONLY | ✓ done | ✓ done | ✗ not started | false |
| v2-20260529T210307 | DATA_ONLY | ✓ done | ✓ done | ✗ not started | false |

9,203 total cycles. 9,183 with intelligence run. 0 with paper run. `blocked_by_mode=false` — the cycle is not "blocked"; the paper stage simply never starts because `should_run_stage("paper")` returns false for DATA_ONLY.

---

## 3. Repository Anatomy

### Top-level structure
```
polybot/
  app/
    ai_brain/           Hybrid local/cloud AI interpretation
    api/                FastAPI routers (35 route modules)
    brains/             Context Brain, Capital Brain
    capital/            Capital Allocator V2
    data_foundation/    Market data ingestion and persistence
    db/                 Connection, migration runner, migrations/
    domain/contracts/   Data contracts (market, ranking, paper, etc.)
    events/             Event Bus, event types, store, replay
    execution_v2/       Execution Cortex V2
    exit_cortex/        Exit Cortex V2
    ingestion/          Gamma API client, MarketService
    learning/           Feedback Learning Loop
    market_memory/      Market Memory V2
    market_neuron/      Market/Orderbook/Liquidity/Time/Fees technical neurons
    models/             NormalizedMarket, ScoredMarket
    neural_mesh/        Neuron registry, signal, binding, producer, health
    news_neuron/        News Neuron (AP/Reuters sources)
    no_trade/           No-Trade Intelligence
    opportunity/        Opportunity Cortex
    repositories/       All DB repositories
    risk/               Risk Gate, Risk Governor
    rules_neuron/       Rules / Wording / Compliance Neuron
    runtime/            StateGovernor, CycleOrchestrator, Modes, SafeStartup
    scoring/            OpportunityScorer
    services/           RuntimeIntelligenceService, RuntimePaperTradingService, etc.
    social_neuron/      Social / Hype Neuron
    stage2/             Legacy Claude analyst
    stage3/             Legacy SQLite paper trading (not used)
    stage4/             Stage4 execution client (Polymarket CLOB)
    strategy/           Strategy Router + Engines
    tools/              Utilities
    utils/              Terminal rendering, time utils
    whale_neuron/       Whale Neuron
    main.py             FastAPI app factory + lifespan
    scheduler.py        RefreshScheduler (the automated loop)
    config.py           Settings
    logging.py          Logger setup
  docs/                 100+ documentation and build report files
  tests/                300+ test files
  scripts/              Utility scripts
  docker-compose.yml    4 services: postgres, redis, api, migrate
```

### Component inventory (by domain)

| Component Name | File Path | Type | Status |
|---|---|---|---|
| Runtime Orchestrator / StateGovernor | app/runtime/state_governor.py | Runtime Gate | ACTIVE |
| CycleOrchestrator | app/runtime/cycle_orchestrator.py | Runtime Control | ACTIVE |
| SafeStartupPolicy | app/runtime/safe_startup.py | Runtime Init | ACTIVE |
| ServiceRegistry | app/runtime/service_registry.py | Runtime Registry | ACTIVE (decorative) |
| RefreshScheduler | app/scheduler.py | Autonomous Loop | ACTIVE |
| MarketService | app/ingestion/market_service.py | Data + Orchestrator | ACTIVE |
| GammaClient | app/ingestion/gamma_client.py | External Data | ACTIVE |
| DataFoundationService | app/data_foundation/service.py | Data Persistence | ACTIVE |
| RuntimeIntelligenceService | app/services/runtime_intelligence.py | Intelligence Loop | ACTIVE (news/whale/AI) |
| RuntimePaperTradingService | app/services/runtime_paper_trading.py | Paper Engine | EXISTS, BLOCKED |
| Event Bus | app/events/event_bus.py | Event Mesh | ACTIVE (publishes) |
| Event Store | app/events/event_store.py | Event Persistence | ACTIVE |
| News Neuron | app/news_neuron/ | Neuron | EXISTS_BUT_DORMANT |
| Social / Hype Neuron | app/social_neuron/ | Neuron | MISSING (disabled) |
| Whale Neuron | app/whale_neuron/ | Neuron | EXISTS_BUT_DORMANT |
| Market Neuron | app/market_neuron/ | Neuron | EXISTS_BUT_DORMANT |
| Orderbook Neuron | — | Neuron | RUNS_BUT_SILENT |
| Liquidity Neuron | — | Neuron | RUNS_BUT_SILENT |
| Time Neuron | — | Neuron | MISSING |
| Rules / Wording Neuron | app/rules_neuron/ | Neuron | EXISTS_BUT_DORMANT |
| Fees / Rewards Neuron | — | Neuron | MISSING |
| Context Brain | app/brains/ | Brain | EXISTS_BUT_DORMANT |
| Capital Brain | app/brains/ | Brain | EXISTS_BUT_DORMANT |
| Opportunity Cortex | app/opportunity/ | Cortex | EXISTS_BUT_DORMANT |
| Strategy Router | app/strategy/ | Router | EXISTS_BUT_DORMANT |
| Risk Gate | app/risk/ | Gate | EXISTS_BUT_DORMANT |
| Risk Governor | app/risk/ | Governor | ACTIVE (guards) |
| Execution Cortex | app/execution_v2/ | Cortex | EXISTS_BUT_DORMANT |
| Exit Cortex | app/exit_cortex/ | Cortex | EXISTS_BUT_DORMANT |
| Capital Allocator | app/capital/ | Allocator | EXISTS_BUT_DORMANT |
| Memory Node / Market Memory | app/market_memory/ | Memory | EXISTS_BUT_DORMANT |
| No-Trade Ledger | app/no_trade/ | Ledger | RUNS_BUT_SILENT (receives but doesn't generate) |
| Dashboard Truth | app/api/ (dashboard routes) | Dashboard | ACTIVE (reads real DB) |
| Brain Mesh Dialogue Feed | — | Feed | MISSING |
| Runtime Brain Producer Adapter | app/services/ | Brain → Signal | EXISTS_BUT_DORMANT |
| Runtime Coordinator Decision | app/services/ | Coordinator | EXISTS_BUT_DORMANT |
| Runtime Producer Evidence | app/services/ | Evidence | EXISTS_BUT_DORMANT |

---

## 4. Brain Mesh Communication Map

The neural mesh is designed as a directed graph. Here is what exists in code versus what actually fires:

```
[Gamma API]
    ↓ every ~70s (ACTIVE)
[GammaClient.fetch_active_events()]
    ↓
[MarketService.refresh()]
    ↓
[market_snapshots, liquidity_snapshots, fee_snapshots] ← ACTIVE, writes to DB
    ↓
[DataFoundationService.process_markets()] ← ACTIVE
    ↓
[event_log: market.snapshot.created] ← ACTIVE, 100k+ events
    ↓
[RuntimeIntelligenceService.refresh()] ← ACTIVE but thin output
    ↓ (if news_enabled and due)
[ExternalIntelligenceFoundationService] → [news_raw_events, news_normalized_events]
    ↓ (if new news)
[ExternalEventEnrichmentService] → [external_event_enrichments]
    ↓
[ExternalToCognitionHandoffService] → [cognition_handoff_candidates]
    ↓ (if due)
[WhaleScoringService] → [whale_scoring_runs]
    ↓
[AI Digest via Anthropic API] → [alert_events]

====== BREAK ======  ← THE GAP: nothing below runs automatically

[RuntimeProducerEvidenceService] ← MANUAL API ONLY, ran 1x (2026-05-28)
    ↓ produces
[neuron_producer_evidence_items]
    ↓
[RuntimeBrainProducerAdapter] ← MANUAL API ONLY, ran 1x (2026-05-28)
    ↓ produces
[brain_outputs] (148 total, last: 2026-05-28)
    ↓
[RuntimeCoordinatorDecisionService] ← MANUAL API ONLY, ran 1x (2026-05-28)
    ↓ produces
[coordinator_decisions] (112 total, last: 2026-05-28)
    ↓
[PositionThesisProfileService] ← MANUAL API ONLY
    ↓ produces
[position_thesis_profiles] = 0 ROWS  ← NEVER RAN
    ↓
[RiskCoreService] ← partial automation in the paper phase
    ↓ produces
[risk_decisions] (100 total, all BLOCK, all from automated runs)
    ↓
[ExitFoundationService] ← partial automation
    ↓ produces
[exit_plans] (100 total, all INSUFFICIENT_DATA, all from automated runs)
    ↓
[PaperEligibilityGateService] ← partial automation
    ↓ produces
[paper_eligibility_candidates] (100 total, all BLOCKED, all from automated runs)
    ↓
[PaperIntentService] ← BLOCKED: paper_intent_allowed=false DB constraint
    ↓ produces
[paper_intents] = 0 ROWS

[paper_orders] = 0 ROWS
[paper_positions] = 0 ROWS
```

### Communication status by component

| From → To | Channel | Payload | Status | Gap |
|---|---|---|---|---|
| GammaAPI → MarketService | HTTP | events JSON | ACTIVE | none |
| MarketService → DB | SQL | market_snapshots, cycles | ACTIVE | none |
| MarketService → EventBus | event_log | market.snapshot.created | ACTIVE | none |
| RuntimeIntelligenceService → DB | SQL | news_raw_events | PARTIAL | AP News only; rarely fires due to interval |
| ProducerEvidence → BrainProducer | internal | neuron signals | DORMANT | not wired into cycle |
| BrainProducer → DB | SQL | brain_outputs | DORMANT | not wired into cycle |
| BrainOutputs → Coordinator | internal | coordinator_decisions | DORMANT | not wired into cycle |
| Coordinator → ThesisProfile | internal | position_thesis_profiles | MISSING | 0 rows, never automated |
| ThesisProfile → RiskCore | internal | risk_decisions | PARTIAL | Risk runs but blocks on missing thesis |
| RiskCore → ExitFoundation | internal | exit_plans | PARTIAL | Exit runs but blocks on missing risk approval |
| ExitFoundation → Eligibility | internal | paper_eligibility_candidates | PARTIAL | Eligibility runs but blocks on multiple missing items |
| Eligibility → PaperIntent | internal | paper_intents | BLOCKED | DB constraint enforces paper_intent_allowed=false |
| PaperIntent → Execution | internal | paper_orders | BLOCKED | paper engine not running |

---

## 5. Component Dialogue Audit

For each component: structured output / human-readable message / event type / DB record / timestamp / market_id+candidate_id / reason / next_required_evidence / dashboard visibility.

| Component | Structured | Human msg | Event type | DB record | Timestamp | Market ID | Reason | Next evidence | Dashboard |
|---|---|---|---|---|---|---|---|---|---|
| News Neuron | PARTIAL | NO | YES (rules.ingested) | YES (news_raw_events) | YES | PARTIAL | NO | NO | YES/stale |
| Social Neuron | MISSING | NO | NO | YES (empty) | — | — | — | — | YES/no data |
| Whale Neuron | PARTIAL | NO | NO | YES (whale_scan_runs) | YES | NO | NO | NO | YES/stale |
| Market Neuron | PARTIAL | NO | YES (source_status_observed) | YES (neuron_signals) | YES | PARTIAL | NO | NO | YES/stale |
| Orderbook Neuron | PARTIAL | NO | YES (source_status_observed) | YES (neuron_signals) | YES | PARTIAL | NO | NO | YES/stale |
| Liquidity Neuron | MISSING | NO | NO | YES (liquidity_snapshots) | YES | YES | NO | NO | YES/stale |
| Time Neuron | MISSING | NO | NO | NO | — | — | — | — | NO |
| Rules Neuron | PARTIAL | NO | YES (rules_resolution_status_observed) | YES (neuron_signals) | YES | PARTIAL | PARTIAL | NO | YES/degraded |
| Fees Neuron | MISSING | NO | NO | NO | — | — | — | — | NO |
| Context Brain | EXISTS | NO | NO | YES (brain_outputs) | YES (stale) | PARTIAL | YES | NO | YES/stale |
| Capital Brain | EXISTS | NO | NO | YES (capital_brain_outputs) | — | — | — | — | YES/no data |
| Opportunity Cortex | EXISTS | NO | NO | YES (opportunity_scores_v2) | — | — | — | — | YES/no data |
| Strategy Router | EXISTS | NO | NO | YES (strategy_routes_v2) | — | — | — | — | YES/no data |
| Risk Gate | EXISTS | NO | YES (risk_decisions) | YES | YES | YES | YES (blockers) | YES | YES |
| Risk Governor | ACTIVE | NO | NO | YES (risk_governor_state) | — | — | — | — | YES |
| Execution Cortex | EXISTS | NO | YES (execution.*) | YES (orders_v2) | YES (stale) | PARTIAL | NO | — | YES/stale |
| Exit Cortex | EXISTS | NO | NO | YES (exit_plans) | YES | YES | YES (blockers) | YES | YES |
| Memory Node | EXISTS | NO | NO | YES (market_memory_v2) | — | — | — | — | YES/no data |
| No-Trade Ledger | ACTIVE | YES (explanation field) | NO | YES (no_trade_log) | YES | YES | YES (primary_reason) | NO | YES |
| Dashboard Truth | ACTIVE | NO | — | reads real DB | YES | YES | PARTIAL | NO | YES |
| Runtime Orchestrator | ACTIVE | NO | YES (runtime.cycle.*) | YES (runtime_cycles_v2) | YES | — | PARTIAL | — | YES |
| Event Bus | ACTIVE | NO | YES (many types) | YES (event_log) | YES | YES | PARTIAL | — | YES |
| Brain Mesh Dialogue Feed | MISSING | — | — | NO | — | — | — | — | NO |

### Neuron health summary (from API, 2026-05-30)
```
total_neurons:    22
active_neurons:   0   ← ZERO active neurons
partial_neurons:  11
disabled_neurons: 2   (news, social)
missing_neurons:  4   (fees, liquidity, time, position)
degraded_neurons: 1   (rules)
stale_neurons:    4   (ai, market, orderbook, whale)
signals_24h:      0   (ALL neurons, every single one)
signals_1h:       0   (ALL neurons, every single one)
```

---

## 6. Runtime Autonomy Audit

### What runs autonomously

| Service | Entrypoint | Loop | Interval | Output |
|---|---|---|---|---|
| RefreshScheduler | app/scheduler.py | YES | ~70 seconds | runs MarketService.refresh() |
| MarketService.scanner | inside refresh() | NO (called by scheduler) | per-cycle | market_snapshots, cycles |
| MarketService.intelligence | inside refresh() | NO | per-cycle | news/whale/AI if due |
| DataFoundationService | inside refresh() | NO | per-cycle | market_snapshots_v2, liquidity_snapshots |
| EventBus publisher | inside refresh() | NO | per-cycle | event_log entries |

### What is manual-only

| Service | How triggered | Last run |
|---|---|---|
| RuntimeProducerEvidenceService | POST /producers/runtime-evidence/run | 2026-05-28 09:16 |
| RuntimeBrainProducerAdapter | POST /brain/runtime/run | 2026-05-28 10:03 |
| RuntimeCoordinatorDecisionService | POST /coordinator/runtime/run | 2026-05-28 18:22 |
| PositionThesisProfileService | POST /thesis/profiles/build | NEVER |
| OrderbookSnapshotService | POST /orderbook/snapshots/collect | 2026-05-28 23:10 |
| RulesNeuron / Rules analysis | POST /rules/analyze/all | 2026-05-21 |
| NewsNeuron (manual) | POST /news/collect | 2026-05-21 |
| WhaleNeuron (manual) | POST /whales/scan | 2026-05-21 |
| MeshDryRun | POST /mesh/dry-run/* | occasional |

### What is dead / never started

- Social Neuron runtime loop: NO (disabled in registry)
- Capital Brain autonomous loop: NO
- Opportunity Cortex loop: NO
- Strategy Router loop: NO
- Learning loop: NO (no outcomes to learn from)
- Market Memory loop: NO
- Brain Dialogue Feed: NO (not built)

### Service health reality

| Service Name | Registered Status | last_heartbeat_at | last_success_at | Reality |
|---|---|---|---|---|
| scheduler | HEALTHY | 2026-05-29 21:07:41 | 2026-05-29 21:07:51 | TRULY RUNNING |
| market_service | HEALTHY | null | 2026-05-29 21:07:51 | TRULY RUNNING |
| data_foundation | HEALTHY | null | 2026-05-29 21:07:51 | TRULY RUNNING |
| fastapi | RUNNING | 2026-05-29 21:08:17 | null | TRULY RUNNING |
| postgres | HEALTHY | 2026-05-29 21:08:17 | null | TRULY RUNNING |
| redis | HEALTHY | 2026-05-29 21:08:17 | null | TRULY RUNNING |
| news_neuron | RUNNING | null | null | DECORATIVE (startup label only) |
| social_neuron | RUNNING | null | null | DECORATIVE |
| whale_neuron | RUNNING | null | null | DECORATIVE |
| market_neuron | RUNNING | null | null | DECORATIVE |
| context_capital_brains | RUNNING | null | null | DECORATIVE |
| opportunity_cortex | RUNNING | null | null | DECORATIVE |
| strategy_router | RUNNING | null | null | DECORATIVE |
| risk_gate_governor | RUNNING | null | null | DECORATIVE |
| execution_cortex_v2 | RUNNING | null | null | DECORATIVE |
| exit_cortex_v2 | RUNNING | null | null | DECORATIVE |
| paper_runtime | STOPPED | null | null | TRULY STOPPED |
| intelligence_runtime | STOPPED | null | null | TRULY STOPPED |
| dashboard | STOPPED | null | null | (reads from DB — shown as stopped but API works) |
| telegram | STOPPED | null | null | TRULY STOPPED |

The service registry is populated in `main.py` lifespan with `service_registry.register_service("news_neuron", ..., status="RUNNING")` for every component. This is a startup declaration, not an ongoing health signal. Components show "RUNNING" because they were declared alive — not because they are producing output.

---

## 7. Service and API Status

| Service | Container | Status | Health |
|---|---|---|---|
| polybot_api | polybot_api | Up 42+ min | HEALTHY (curl /docs → 200) |
| polybot_postgres | polybot_postgres | Up 20+ hours | HEALTHY |
| polybot_postgres_test | polybot_postgres_test | Up 21+ hours | HEALTHY |
| polybot_redis | polybot_redis | Up 21+ hours | HEALTHY |

### Key API endpoint checks

| Endpoint | Result | Notes |
|---|---|---|
| GET /healthz | `{"status":"ok","ready":true}` | GREEN |
| GET /runtime/state | DATA_ONLY mode, all paper/shadow/live blocked | GREEN (correct) |
| GET /runtime/health | HEALTHY, scheduler HEALTHY | GREEN |
| GET /dashboard/api/v2/overview | DEGRADED, 0 active neurons, mock_data=false | YELLOW |
| GET /dashboard/api/v2/neurons | DEGRADED, 0 signals/24h for all neurons | RED |
| GET /dashboard/api/v2/signals | real DB, all stale | YELLOW |
| GET /markets/top | returns top scored markets | GREEN |
| GET /dashboard/api/v2/paper-eligibility | 100 candidates, all BLOCKED | YELLOW |
| GET /dashboard/api/v2/paper-intents | 0 intents | RED |
| GET /dashboard/api/v2/orderbook | 22 snapshots, all stale >24h | RED |

### Notable routes that exist but point to dormant components:
- `/brain/runtime/run` — triggers RuntimeBrainProducerAdapter (ran 1x manually)
- `/coordinator/runtime/run` — triggers RuntimeCoordinatorDecisionService (ran 1x manually)
- `/producers/runtime-evidence/run` — triggers RuntimeProducerEvidenceService (ran 1x manually)
- `/thesis/profiles/build` — builds position thesis (0 rows, never automated)
- `/orderbook/snapshots/collect` — collects fresh CLOB orderbook data (ran 1x manually 2026-05-28)

---

## 8. Database Truth Map

DB: 236 tables. Key tables by category:

### Data collection (ACTIVE, healthy)
| Table | Rows | Latest |
|---|---|---|
| market_snapshots | 91,818 | 2026-05-29 20:51 |
| event_log | 301,000+ | 2026-05-29 21:07 |
| runtime_cycles_v2 | 9,250+ | 2026-05-29 21:07 |
| system_state | 1 | 2026-05-20 23:20 (never updated) |
| liquidity_snapshots | 91,850 | 2026-05-29 |
| fee_snapshots | 91,850 | 2026-05-29 |

### Neural mesh (STALE, not refreshing)
| Table | Rows | Latest | Status |
|---|---|---|---|
| neuron_signals | 147 | 2026-05-28 09:16 | STALE (>24h) |
| neuron_signal_bindings | 111 | 2026-05-28 09:16 | STALE |
| signal_market_links | 20 | 2026-05-27 07:25 | STALE (>3 days) |
| brain_outputs | 148 | 2026-05-28 10:03 | STALE (>24h) |
| coordinator_decisions | 112 | 2026-05-28 18:22 | STALE (>24h) |
| position_thesis_profiles | 0 | — | MISSING |
| thesis_profiles | 0 | — | MISSING |
| orderbook_snapshots | 22 | 2026-05-28 23:10 | STALE (>24h) |
| runtime_producer_evidence_runs | 1 | 2026-05-28 09:16 | STALE |
| runtime_brain_producer_runs | 1 | 2026-05-28 10:03 | STALE |
| runtime_coordinator_runs | 1 | 2026-05-28 18:22 | STALE |

### Decision pipeline (populated but all blocked)
| Table | Rows | Latest | Verdict |
|---|---|---|---|
| risk_decisions | 100 | 2026-05-29 10:26 | All BLOCK/BLOCKED |
| exit_plans | 100 | 2026-05-29 13:52 | All INSUFFICIENT_DATA |
| paper_eligibility_candidates | 100 | 2026-05-29 18:28 | All BLOCKED |
| no_trade_log | 100 | 2026-05-29 20:09 | All risk_not_approved |
| paper_intents | 0 | — | EMPTY |
| paper_orders | 0 | — | EMPTY (1 historical from 2026-05-21) |
| paper_positions | 0 | — | EMPTY |

### Brain component tables (all empty)
| Table | Rows |
|---|---|
| context_brain_outputs | 0 |
| capital_brain_outputs | 0 |
| opportunity_scores_v2 | 0 |
| strategy_routes_v2 | 0 |
| capital_allocations_v2 | 0 |
| ranking_v2_candidates | 0 |

### DB constraint safety locks (hardcoded in schema)
These fields are enforced FALSE at the DB schema level. They are safety guarantees, not bugs:
- `paper_eligibility_candidates.paper_intent_allowed` — CHECK (= false)
- `paper_eligibility_candidates.execution_allowed` — CHECK (= false)
- `risk_decisions.paper_candidate_allowed` — CHECK (= false)
- `risk_decisions.execution_allowed` — CHECK (= false)
- `exit_plans.paper_intent_allowed` — CHECK (= false)
- `exit_plans.execution_allowed` — CHECK (= false)

These constraints ensure that no accidental enable of execution can happen through these tables directly. The intended path for enabling paper execution goes through the `PaperIntentService` which is governed separately.

---

## 9. Candidate-Level Deep Trace

Selected 5 real current blocked candidates from paper_eligibility_candidates (most recent):

### Candidate 1: market_id=597964
```
eligibility_id: eligibility_exit_risk_thesis_coord_9ccf225d2ca14aea8932600f8573cf2b
market_id: 597964
side: NULL  ← MISSING_SIDE
status: BLOCKED
risk_decision_id: risk_thesis_coord_9ccf225d2ca14aea8932600f8573cf2b
exit_plan_id: exit_risk_thesis_coord_9ccf225d2ca14aea8932600f8573cf2b
orderbook_snapshot_id: NULL  ← MISSING_FRESH_ORDERBOOK
risk_approved: false
exit_ready: false
lineage_trusted: true  ← lineage IS trusted (good)

Eligibility blockers: EXIT_NOT_READY, MISSING_FRESH_ORDERBOOK, MISSING_SIDE,
                      MISSING_SIGNAL_MARKET_BINDING, RISK_BLOCKED, RISK_NOT_APPROVED,
                      THESIS_NOT_COMPLETE

Risk blockers: MISSING_FRESH_ORDERBOOK, MISSING_MARKET_LINK,
               MISSING_SIGNAL_MARKET_BINDING, THESIS_BLOCKED

Exit blockers: MISSING_FRESH_ORDERBOOK, MISSING_MARKET_LINK, MISSING_MID_PRICE,
               MISSING_RISK_APPROVAL, MISSING_SIDE, MISSING_SIGNAL_MARKET_BINDING,
               RISK_BLOCKED, THESIS_BLOCKED
```

### Candidate 2: market_id=691547
Same pattern as Candidate 1. All 5 candidates share identical blocker sets.

### Universal blocker pattern (all 5 candidates identical):
1. **MISSING_SIGNAL_MARKET_BINDING** — neuron signals exist but are NOT bound to specific market IDs. The 20 signal_market_links are stale from 2026-05-27.
2. **MISSING_FRESH_ORDERBOOK** — orderbook_snapshots last refreshed 2026-05-28 23:10, now >24h stale. The freshness window is shorter than the refresh interval.
3. **MISSING_SIDE** — no YES/NO direction can be determined without a valid signal-market binding
4. **THESIS_BLOCKED / THESIS_NOT_COMPLETE** — position_thesis_profiles = 0. No thesis was ever created for any of these candidates by the PositionThesisProfileService.
5. **RISK_BLOCKED / RISK_NOT_APPROVED** — cascades from THESIS_BLOCKED and MISSING_FRESH_ORDERBOOK
6. **MISSING_MARKET_LINK** — no market link established (related to binding gap)
7. **EXIT_NOT_READY / MISSING_MID_PRICE** — exit plan has INSUFFICIENT_DATA because it cannot compute a mid-price without a fresh orderbook

### Root cause chain for all 5 candidates:
```
PositionThesisProfileService NEVER RAN (0 thesis profiles)
  → coordinator_decisions exist (112) but thesis was never built from them
  → risk_decisions run but see THESIS_BLOCKED
  → exit_plans run but see THESIS_BLOCKED + no mid-price
  → eligibility gate sees nothing ready
  → no_trade_log records risk_not_approved for all 100 candidates
  → paper_intents = 0
```

The secondary chain:
```
No orderbook refresh loop running
  → orderbook_snapshots become stale (>24h)
  → MISSING_FRESH_ORDERBOOK in every risk/exit/eligibility evaluation
  → Even if thesis were built, orderbook staleness would block paper
```

---

## 10. Paper Not Alive — Root Cause Analysis

### Layer 1: MODE BLOCK (PRIMARY)
**Blocker type: CONFIG_OR_ENV_MISMATCH**

The DB system_state is DATA_ONLY. The scheduler's `should_run_stage("paper")` calls `governor.can_execute(RUN_PAPER_ENGINE)` which returns false for DATA_ONLY. The paper stage never starts.

Even if all evidence requirements were met, paper could not run until the DB mode is changed to PAPER via the `/runtime/mode/request` API.

Root: SafeStartupPolicy initializes from DB state, not from env var. DB was set DATA_ONLY on first startup 2026-05-20 and never transitioned.

### Layer 2: NEURAL MESH NOT WIRED (PRIMARY)
**Blocker type: COMPONENT_DORMANT**

The scheduler calls MarketService.refresh() → RuntimeIntelligenceService.refresh(). Neither of these calls RuntimeProducerEvidenceService, RuntimeBrainProducerAdapter, or RuntimeCoordinatorDecisionService. The brain mesh cycle is NOT in the automated loop.

All brain_outputs, coordinator_decisions, and related tables stopped updating after 2026-05-28 when they were manually triggered.

### Layer 3: POSITION THESIS NEVER BUILT (PRIMARY)
**Blocker type: MISSING_COMPONENT**

PositionThesisProfileService has never been run (position_thesis_profiles = 0). Even the manual trigger on 2026-05-28 that ran the brain producer and coordinator did not include thesis profile creation. Without thesis, the entire downstream chain (risk → exit → eligibility) produces only "THESIS_BLOCKED" decisions.

### Layer 4: ORDERBOOK SNAPSHOTS STALE (BLOCKING)
**Blocker type: STALE_DATA_BLOCK**

Orderbook snapshots are from 2026-05-28 23:10 — over 24 hours ago. Risk evaluations require a fresh orderbook. The CLOB endpoint is available, but there is no automated orderbook refresh loop. The endpoint `/orderbook/snapshots/collect` must be called manually.

### Layer 5: SIGNAL MARKET BINDINGS STALE (BLOCKING)
**Blocker type: STALE_DATA_BLOCK**

20 signal_market_links exist (last: 2026-05-27). The RuntimeProducerEvidenceService creates bindings, but it only ran once. There is no ongoing signal market binding refresh.

### Layer 6: NO POSITION SIDE (BLOCKING)
**Blocker type: OUTPUT_NOT_CONSUMED**

No candidate has a side (YES/NO). Side comes from the coordinator_decision which derives direction from brain_outputs. Even though coordinator_decisions exist (112), they are stale and no new ones are generated. Without a fresh, bound, side-assigned coordinator decision, the eligibility gate cannot determine which side to enter.

### Layer 7: DB SAFETY CONSTRAINTS (VALID_SAFETY_BLOCK)
**Blocker type: VALID_SAFETY_BLOCK**

DB constraints hardcode paper_intent_allowed=false in all three tables (eligibility, risk, exit). These are schema-level safety controls. They are correct and intentional. The actual activation path for paper trades must go through the PaperIntentService logic, not through these fields.

---

## 11. Brain Dialogue Feed Gap Analysis

### Does a Brain Dialogue Feed exist?

**NO.** There is no Brain Dialogue Feed in the current system.

### What exists that could power it:

1. **event_log** (301k+ rows) — contains runtime.cycle.started, runtime.cycle.finished, market.snapshot.created, rules.*, execution.* events. Has: event_type, source_service, correlation_id, occurred_at, payload_json. Missing: component decision explanations, conflict detection, next_required_evidence.

2. **no_trade_log** (100 rows) — has: primary_reason, explanation text, blockers JSON, missing_requirements JSON, source_layer, market_id. This is the closest existing record to a dialogue message.

3. **paper_eligibility_candidates** — has: eligibility_blockers JSON, missing_requirements JSON, evidence JSON. Very detailed but not time-ordered dialogue.

4. **risk_decisions** — has: blockers JSON, required_missing_evidence JSON, risk_reasons JSON. Detailed.

5. **coordinator_decisions** — has: conflicts JSON. Partial.

6. **brain_outputs** — has: output data. Missing human-readable explanation.

### Components that produce enough explanation for dialogue:
- **No-Trade Ledger** — YES (explanation field, primary_reason, blockers)
- **Paper Eligibility Gate** — YES (eligibility_blockers, missing_requirements, evidence)
- **Risk Core** — YES (blockers, required_missing_evidence, risk_reasons)
- **Exit Cortex** — YES (blockers, missing_exit_evidence)
- **Coordinator** — PARTIAL (conflicts, but missing human message)

### Components needing richer dialogue output:
- **News Neuron** — no human-readable message, no agrees_with/conflicts_with
- **Brain Outputs** — no operator-facing explanation
- **Scheduler/Cycle** — only has status, no "what I did and why"
- **Market Neuron** — signals exist but no human interpretation
- **Orderbook Neuron** — raw status only

### Proposed Brain Dialogue Feed schema:
```json
{
  "id": "uuid",
  "timestamp": "2026-05-30T00:00:00Z",
  "component": "risk_core",
  "component_type": "gate",
  "event_type": "risk.decision.blocked",
  "severity": "BLOCKED",
  "market_id": "597964",
  "candidate_id": "risk_thesis_coord_9ccf225d2ca14aea8932600f8573cf2b",
  "signal_id": null,
  "decision_id": "risk_thesis_coord_9ccf225d2ca14aea8932600f8573cf2b",
  "inputs_received": ["coordinator_decision", "thesis_profile"],
  "agrees_with": [],
  "conflicts_with": [],
  "evidence_used": {"thesis_status": "BLOCKED", "orderbook_age_seconds": 90000},
  "decision": "BLOCK",
  "status": "BLOCKED",
  "block_reason": "MISSING_FRESH_ORDERBOOK, THESIS_BLOCKED",
  "next_required_evidence": ["fresh_orderbook_snapshot", "complete_thesis_profile"],
  "human_message": "Risk blocked for market 597964: thesis profile is incomplete and orderbook data is 25h stale. Need fresh CLOB snapshot and coordinator to run thesis profile build.",
  "raw_payload": {}
}
```

### Existing data route for dialogue:
`/dashboard/api/v2/events` exists but shows only runtime.cycle events. A `/dashboard/api/v2/brain-dialogue` route does not exist. The data to power it (from no_trade_log, risk_decisions, exit_plans, eligibility_candidates) already exists in the DB.

---

## 12. SYSTEM ON / OFF Final Definition

Based on the actual repository reality, here is what SYSTEM ON and SYSTEM OFF should mean:

### SYSTEM ON
One action (or one API call sequence) that achieves:

1. **DB mode → PAPER** via `POST /runtime/mode/request` with `{"to_mode": "PAPER", "actor": "operator", "reason": "system_on"}`
2. **Neural mesh cycle wired into RefreshScheduler** — the intelligence stage must call:
   - RuntimeProducerEvidenceService.run()
   - RuntimeBrainProducerAdapter.run()
   - RuntimeCoordinatorDecisionService.run()
   - PositionThesisProfileService.build_for_decisions()
3. **Orderbook refresh wired into cycle** — per-cycle call to OrderbookSnapshotService for top-N markets
4. **Paper engine allowed by mode** — with DB = PAPER, `should_run_stage("paper")` returns true
5. **Signal market bindings refresh** — per-cycle or per-N-cycles to keep bindings fresh
6. Brain Dialogue Feed events published to event_log (optional but valuable)

When SYSTEM ON:
- Scheduler runs every ~70s
- Scanner fetches markets
- Neural mesh produces fresh signals, brain outputs, coordinator decisions
- Thesis profiles are built from coordinator decisions
- Risk evaluates with fresh orderbook + fresh thesis
- Exit evaluates with mid-price from fresh orderbook
- Eligibility gate evaluates with complete evidence
- Paper intents are created for eligible candidates
- Paper orders execute in simulation
- Event log shows full Brain Dialogue Feed

### SYSTEM OFF
One action that achieves:
- DB mode → KILL via `POST /runtime/kill` with `{"actor": "operator", "reason": "system_off"}`
- KILL mode blocks ALL permissions (can_collect_data=false, everything false)
- Scheduler would continue looping but each cycle would immediately log "blocked by kill switch" and do nothing
- No data intake, no signals, no paper activity

OR: `docker compose down` which stops all containers entirely.

The KILL mode path is cleaner for "system pause" — it keeps containers alive for inspection but blocks all activity.

---

## 13. Visual Component Map

```
SYSTEM ON / OFF CONTROL
═══════════════════════
StateGovernor (DB: system_state, current_mode=DATA_ONLY)
  controls: ALL runtime permissions
  API: /runtime/state, /runtime/mode/request, /runtime/kill
  status: ACTIVE but stuck at DATA_ONLY

══════════════════════════════════════════════════════════════

DATA COLLECTION LAYER (ACTIVE, every ~70s)
══════════════════════════════════════════
RefreshScheduler
  → MarketService.refresh()
    → GammaClient → [market data fetched]
    → DataFoundationService → market_snapshots_v2, liquidity_snapshots, fee_snapshots
    → EventBus → event_log: market.snapshot.created (100k+ events)
    → RuntimeIntelligenceService → news_raw_events (rare), whale_runs
    → [PAPER STAGE: BLOCKED — DATA_ONLY mode]

STATUS: 9,250+ cycles run. Markets actively fetched. Intelligence thin.

══════════════════════════════════════════════════════════════

NEURAL MESH (BUILT, NOT WIRED — last ran 2026-05-28)
════════════════════════════════════════════════════
RuntimeProducerEvidenceService (MANUAL API: /producers/runtime-evidence/run)
  reads: source_status, rules_analysis, market_snapshots
  writes: runtime_producer_evidence_items
  status: DORMANT, ran 1x

RuntimeBrainProducerAdapter (MANUAL API: /brain/runtime/run)
  reads: runtime_producer_evidence_items, neuron_signals
  writes: brain_outputs (148 total, stale)
  status: DORMANT, ran 1x

RuntimeCoordinatorDecisionService (MANUAL API: /coordinator/runtime/run)
  reads: brain_outputs
  writes: coordinator_decisions (112 total, stale)
  status: DORMANT, ran 1x

PositionThesisProfileService (MANUAL API: /thesis/profiles/build)
  reads: coordinator_decisions
  writes: position_thesis_profiles (0 — NEVER RAN)
  status: MISSING from automation

══════════════════════════════════════════════════════════════

DECISION PIPELINE (RUNS, BUT BLOCKS ON MISSING EVIDENCE)
═════════════════════════════════════════════════════════
RiskCoreService (runs but blocks)
  reads: coordinator_decisions, thesis_profiles (MISSING), orderbook_snapshots (STALE)
  writes: risk_decisions (100, all BLOCK)
  blockers: THESIS_BLOCKED, MISSING_FRESH_ORDERBOOK, MISSING_SIGNAL_MARKET_BINDING
  status: RUNS_BUT_BLOCKED

ExitFoundationService (runs but blocks)
  reads: risk_decisions (blocked), orderbook_snapshots (STALE)
  writes: exit_plans (100, all INSUFFICIENT_DATA)
  blockers: MISSING_MID_PRICE, MISSING_RISK_APPROVAL, THESIS_BLOCKED
  status: RUNS_BUT_BLOCKED

PaperEligibilityGateService (runs but blocks)
  reads: risk_decisions, exit_plans, thesis_profiles (MISSING), signal_market_links (STALE)
  writes: paper_eligibility_candidates (100, all BLOCKED)
  blockers: all of the above
  status: RUNS_BUT_BLOCKED

PaperIntentService (blocked by DB mode)
  reads: paper_eligibility_candidates
  writes: paper_intents (0)
  status: BLOCKED (DB mode DATA_ONLY + DB constraint)

══════════════════════════════════════════════════════════════

NEURONS (22 registered, 0 producing signals in 24h)
══════════════════════════════════════════════════
Market Neuron      → emits: source_status_observed → status: STALE (last 2026-05-28)
Orderbook Neuron   → emits: source_status_observed → status: STALE (last 2026-05-28)
Whale Neuron       → emits: source_status_observed → status: STALE (last 2026-05-28)
AI Neuron          → emits: source_status_observed → status: STALE (last 2026-05-28)
Rules Neuron       → emits: rules_resolution_status_observed → status: DEGRADED (last 2026-05-26)
News Neuron        → emits: source_status_observed → status: DISABLED
Social Neuron      → emits: source_status_observed → status: DISABLED
Fees Neuron        → no producer registered → status: MISSING
Liquidity Neuron   → no producer registered → status: MISSING
Time Neuron        → no producer registered → status: MISSING
All others (12)    → manual only → status: PARTIAL/MISSING

Consumer (brain_outputs): 148 stale outputs, 0 consumed by thesis

══════════════════════════════════════════════════════════════

DASHBOARD (ACTIVE, READS REAL DB)
══════════════════════════════════
FastAPI → dashboard HTML
/dashboard/api/v2/* → real DB queries, no mock data
overview: DEGRADED (shows the stale/missing reality correctly)
neurons: DEGRADED (0 active neurons, correctly reported)
paper-eligibility: real (100 blocked candidates, correctly reported)
paper-intents: real (0, correctly reported)
orderbook: real (22 stale, correctly reported)

══════════════════════════════════════════════════════════════

BRAIN DIALOGUE FEED: MISSING
═════════════════════════════
No component publishes structured dialogue events.
Nearest proxy: no_trade_log (has explanation field, blockers, reason).
event_log has cycle events but no brain decisions.
```

---

## 14. Test and Verification Audit

### Test file count
~300 test files across all phases. Each phase has: contract tests, repository tests, service tests, API tests, safety tests.

### Test coverage gaps for Brain Mesh life:
- No tests for "full automated cycle produces neuron signals" 
- No tests for "neural mesh auto-loop runs every N cycles"
- No tests for "SYSTEM ON triggers all layers"
- No tests for "SYSTEM OFF stops all activity"
- Tests exist for: individual signal contracts, binding logic, brain output logic, coordinator logic, risk logic, exit logic, eligibility logic, paper intent logic — but all as isolated unit tests, not as integration tests of the full chain running automatically.

### Key safe tests available (read-only):
```
tests/test_runtime_modes.py               — mode permission logic
tests/test_state_governor.py              — governor state transitions
tests/test_v2_20_system_truth_checks.py   — system truth assertions
tests/test_v2_20a_neural_mesh_readiness.py — mesh readiness checks
tests/test_v2_20b_runtime_readiness.py    — runtime readiness checks
```

These tests can be run safely. They use test DB and do not modify live state.

No tests were run in this audit (READ_ONLY_REVIEW mode).

---

## 15. Brutal Diagnosis

**1. Is POLYBOT a living Brain Mesh or a collection of parts?**
A collection of expertly built parts. The mesh exists on paper (code, DB tables, APIs, tests), but it does not form a living cycle. Data flows into the scanner. The brain never wakes up to read it.

**2. Does one ON action exist?**
NO. No single action starts everything.

**3. Does OFF fully stop everything?**
PARTIAL. KILL mode would block all permissions but the scheduler keeps looping silently. `docker compose down` stops completely but is infrastructure-level.

**4. Which components are alive?**
- RefreshScheduler: ALIVE
- MarketService (scanner + intelligence): ALIVE
- DataFoundationService: ALIVE
- EventBus (publisher only): ALIVE
- StateGovernor (guards): ALIVE
- FastAPI + all endpoints: ALIVE
- Dashboard (reads real DB): ALIVE
- Postgres + Redis: ALIVE

**5. Which components are silent?**
- All 22 neurons: SILENT (0 signals in 24h)
- RuntimeBrainProducerAdapter: SILENT since 2026-05-28
- RuntimeCoordinatorDecisionService: SILENT since 2026-05-28
- PositionThesisProfileService: NEVER SPOKE
- OpportunityCortex: NEVER SPOKE
- StrategyRouter: NEVER SPOKE
- CapitalAllocator: NEVER SPOKE
- Brain Dialogue Feed: NEVER EXISTED

**6. Which components are missing?**
- Brain Dialogue Feed
- Time Neuron (signal producer)
- Fees/Rewards Neuron (signal producer)
- Automated neural mesh loop (not built into scheduler)
- Automated orderbook refresh loop
- Automated signal-market binding refresh

**7. Which components speak but are not heard?**
- Event Bus: publishes 300k+ events. Nobody subscribes to generate brain outputs.
- risk_decisions: produced with detailed blockers. Eligibility gate hears it but no human/dashboard dialogue shows "risk said X to eligibility".
- exit_plans: produced with detailed blockers. Nobody produces human-readable summary.

**8. Which components hear but do not report?**
- RuntimeIntelligenceService: hears news/whale data, does not publish structured neuron dialogue
- RefreshScheduler: runs every cycle, logs at WARNING level when blocked, does not produce Brain Dialogue events

**9. Which components depend on manual triggering?**
- RuntimeBrainProducerAdapter
- RuntimeCoordinatorDecisionService
- PositionThesisProfileService
- OrderbookSnapshotService
- SignalMarketBindingService
- RulesNeuron analysis

**10. Why are candidates blocked?**
In priority order:
1. PositionThesisProfileService was never called → thesis_profiles = 0 → THESIS_BLOCKED in all downstream
2. Orderbook snapshots >24h stale → MISSING_FRESH_ORDERBOOK in risk, exit, eligibility
3. Signal market bindings stale → MISSING_SIGNAL_MARKET_BINDING, MISSING_SIDE
4. Risk cannot approve without thesis → RISK_NOT_APPROVED
5. Exit cannot compute without orderbook mid-price → EXIT_NOT_READY

**11. Why is no Paper intent created?**
Two-layer block:
- DB mode is DATA_ONLY → paper engine stage never executes
- Even if mode were PAPER: all 100 candidates are BLOCKED by evidence gaps
- Even if evidence were complete: DB constraint enforces paper_intent_allowed=false until PaperIntentService explicitly creates a valid intent

**12. Is the blocking correct or caused by missing runtime life?**
BOTH:
- DATA_ONLY mode block: VALID_SAFETY_BLOCK (intentional)
- THESIS_BLOCKED: caused by missing runtime life (PositionThesisProfileService never automated)
- MISSING_FRESH_ORDERBOOK: caused by missing runtime life (no orderbook loop)
- MISSING_SIGNAL_MARKET_BINDING: caused by missing runtime life (binding refresh not automated)

**13. What is the single biggest reason the system does not feel alive?**
**The neural mesh cycle (ProducerEvidence → BrainProducer → Coordinator → Thesis) is not wired into the automated scheduler loop.** Every 70 seconds the system fetches markets and does nothing with them from a brain perspective. The brain never wakes up.

**14. What is the second biggest reason?**
**The DB runtime mode is DATA_ONLY** — even if the brain mesh were wired, the paper engine would still not execute. The system's own governance is preventing it from taking any action.

**15. What is the smallest next implementation that would inject real life?**
See Section 16.

---

## 16. Smallest Correct Next Move

**This is a proposal only. No implementation in this audit.**

The minimum viable change to inject life without unsafe actions:

### Move 1: Wire the neural mesh cycle into the intelligence stage (ONE new function call)

In `MarketService.refresh()`, after the intelligence stage completes, call the runtime brain mesh cycle:
```python
# Inside MarketService.refresh(), after intelligence stage
if orchestrator.should_run_stage("intelligence"):
    # existing intelligence code ...
    # NEW: run neural mesh cycle
    self._neural_mesh_cycle.run(cycle_id=v2_cycle_id, top_markets=scored_markets[:10])
```

This `neural_mesh_cycle.run()` would call in sequence:
1. OrderbookSnapshotService.collect(market_ids) — collect fresh orderbook data
2. RuntimeProducerEvidenceService.run(cycle_id)
3. RuntimeBrainProducerAdapter.run(cycle_id)
4. RuntimeCoordinatorDecisionService.run(cycle_id)
5. PositionThesisProfileService.build_for_decisions(cycle_id)

This single wiring would make ALL of the following happen automatically every ~70 seconds:
- Fresh orderbook snapshots (fixes MISSING_FRESH_ORDERBOOK)
- Fresh neuron signals (fixes stale signals)
- Fresh brain outputs
- Fresh coordinator decisions
- Fresh position thesis profiles (fixes THESIS_BLOCKED)
- Fresh risk decisions (would approve if thesis + orderbook OK)
- Fresh exit plans (would complete if risk approved + orderbook fresh)
- Fresh eligibility evaluations (candidates could become ELIGIBLE)

### Move 2: Change DB mode to PAPER (one API call after Move 1 is tested)

```
POST /runtime/mode/request
{"to_mode": "PAPER", "actor": "operator", "reason": "enabling_paper_trading", "correlation_id": "system_on_2026"}
```

This enables the paper engine in the scheduler loop, allowing paper orders to be created for eligible candidates.

**Move 1 alone makes the system feel alive (brain thinks) without enabling trading.**  
**Move 1 + Move 2 makes the system trade on paper.**

Both moves are scoped, reversible, and do not touch any forbidden core areas.

---

## 17. GREEN / YELLOW / RED

**Status: GREEN**

- Audit completed: YES
- Report created: YES (this file)
- No unsafe actions taken: YES
- No code modified: YES
- No DB writes: YES (read-only SELECT only)
- No orders/fills/positions created: YES
- No paper/shadow/live enabled: YES
- No secrets printed: YES
- Candidate-level trace: YES (5 candidates analyzed)
- Component communication map: YES
- Runtime autonomy audit: YES
- SYSTEM ON/OFF reality answered: YES
- Brain Dialogue Feed gap answered: YES
- Evidence sufficient for next implementation: YES

### Safety checklist
- [x] KILL switch not touched
- [x] DATA_ONLY mode preserved (not changed)
- [x] No execution enabled
- [x] No paper execution enabled
- [x] No shadow execution enabled
- [x] No live execution enabled
- [x] No secrets inspected or printed
- [x] No destructive DB operations
- [x] No docker volume operations
- [x] No code changes

### Remaining risks
1. If mode is changed to PAPER before the neural mesh is wired, the paper engine will run but will create NO paper orders (all candidates blocked). This is safe but confusing.
2. The 147 stale neuron signals and 100 stale candidates should be re-evaluated when new signals are generated — old rows may conflict.
3. The `paper_intent_allowed=false` DB constraint means activation requires understanding the full PaperIntentService logic before assuming paper intents will auto-create.

---

*Audit executed by Claude Code. No code modified. No trading enabled. All commands: read-only.*
