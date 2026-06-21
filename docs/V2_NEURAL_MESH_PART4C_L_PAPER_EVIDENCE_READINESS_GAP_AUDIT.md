# V2 Neural Mesh Part 4C-L: Paper Evidence Readiness Gap Closure Audit

## 1. Purpose
This phase is a read-only Paper readiness gap audit. It maps the remaining technical blockers between the current runtime Neural Mesh and a safe, fully evidenced Paper mode.

This audit does not implement Paper, does not create orders, does not create order intents, does not create fills or positions, and does not modify runtime mode.

## 2. Current Runtime Chain
Runtime verification on 2026-05-28 found the application healthy and dashboard truth available:

| Layer | Status | Current truth |
| --- | --- | --- |
| Runtime Producer Evidence | READY / PARTIAL | Runtime evidence loop exists; run table has 1 row. Producer health still reports degraded and missing/silent producer blockers. |
| Runtime Signals | PARTIAL | `neuron_signals=147`. Runtime signals exist, but signal freshness, linkage, and lineage blockers remain. |
| Signal Quality | PARTIAL | `signal_quality_evaluations=108`. `SIGNAL_QUALITY_GATE_BLOCKED` remains active. |
| Signal Processing | PARTIAL | `signal_processing_states=108`. Paper eligibility remains zero. |
| Link Coverage | BLOCKED | `signal_market_links=20`, `signal_position_links=0`, `SIGNAL_LINKING_TOO_LOW` remains active. |
| Lineage Coverage | BLOCKED | `signal_lineage_coverage_analysis=108`, `SIGNAL_LINEAGE_COVERAGE_LOW` remains active. |
| Dry Run Provenance | READY | `dry_run_provenance_analysis=407`; dry-run evidence is separated and blocked from Paper. |
| Producer Health | PARTIAL | Producer health exists, but producer health blockers remain active. |
| Runtime Brain Outputs | READY | `brain_outputs=148`; runtime=100, dry-run=48. |
| Runtime Coordinator Decisions | READY | `coordinator_decisions=112`; runtime=100, dry-run=12 by dashboard/runtime split. |
| Mesh Blockers | READY | `/dashboard/api/v2/mesh-blockers` returns `mock_data=false`, `paper_ready=false`, `overall_status=BLOCKED`. |
| Dashboard Mesh | READY | `/dashboard/api/v2/mesh` includes runtime brain and runtime coordinator layers. |
| 4C Regression Tests | READY | 46 consolidated 4C tests passed in this audit phase. |

## 3. Runtime Verification Snapshot
Read-only endpoint checks:

| Endpoint | HTTP | Key result |
| --- | ---: | --- |
| `/healthz` | 200 | `status=ok` |
| `/runtime/health` | 200 | `current_mode=DATA_ONLY` |
| `/dashboard/api/v2/mesh` | 200 | `mock_data=false`, `paper_ready=false`, `overall_status=BLOCKED` |
| `/dashboard/api/v2/mesh-blockers` | 200 | `mock_data=false`, active blockers=17 |
| `/dashboard/api/v2/runtime-brain` | 200 | runtime Brain Outputs=100, dry-run Brain Outputs=48 |
| `/dashboard/api/v2/runtime-coordinator` | 200 | runtime Coordinator Decisions=100, dry-run Coordinator Decisions=12 |

Safety counters from DB/runtime truth:

| Counter | Value |
| --- | ---: |
| `paper_orders` | 0 |
| `shadow_orders` | 0 |
| `live_orders` | 0 |
| `order_intents` | absent |
| `paper_positions` | 0 |
| `positions` | 0 |
| `paper_fills` | absent |
| `fills_v2` | 1 pre-existing historical row |
| `execution_allowed_true` | 0 |
| `paper_ready` | false |

## 4. Paper Blocker Inventory
The active blocker set from `/dashboard/api/v2/mesh-blockers` is:

- `DRY_RUN_EVIDENCE_BLOCKED_FROM_PAPER`
- `ENV_PERSISTED_KILL_SWITCH_MISMATCH`
- `ENV_PERSISTED_MODE_MISMATCH`
- `EXECUTION_NOT_ALLOWED`
- `EXPECTED_NEURONS_SILENT`
- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `NO_RISK_CORE`
- `NO_THESIS_PROFILES`
- `ORDERBOOK_SNAPSHOTS_MISSING`
- `PRODUCERS_DRY_RUN_ONLY`
- `PRODUCER_HEALTH_DEGRADED`
- `PRODUCER_RUNTIME_EVIDENCE_MISSING`
- `SIGNALS_STALE_HIGH`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `SIGNAL_LINKING_TOO_LOW`
- `SIGNAL_QUALITY_GATE_BLOCKED`

Detailed blocker map:

| Blocker | Active | Severity | Evidence | Why it blocks Paper | Dependency | Recommended next phase | Expected fix output | Acceptance criteria | Executor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ORDERBOOK_SNAPSHOTS_MISSING` | true | CRITICAL | `orderbook_snapshots` exists with 0 rows | No fresh bid/ask/spread/liquidity evidence exists for Paper candidate validation. | Runtime market/source truth | 4C-M Orderbook Snapshot Foundation | Fresh persisted orderbook snapshots with staleness checks | Non-executing snapshots exist, are fresh, linked to markets, dashboard shows count > 0 | Codex |
| `NO_RISK_CORE` | true | CRITICAL | risk evidence tables absent/0, `risk_gate_runs=0` | Paper cannot size, cap, or reject candidates safely without enforced risk decisions. | Orderbook + thesis + candidate truth | 4C-P Risk Core Foundation | Risk decisions/gate runs for Paper candidates | Every Paper candidate has blocking/enforcing risk decision; no bypass | Codex |
| `NO_EXIT_FOUNDATION` | true | CRITICAL | `exit_plans=0`, exit foundation evidence absent | No entry can be Paper-ready without an exit plan. | Thesis + risk + candidate truth | 4C-Q Exit Foundation | Exit plans for Paper candidates | Every candidate/intent requires an exit plan before Paper intent | Codex |
| `NO_PAPER_ELIGIBLE_SIGNALS` | true | CRITICAL | signal quality/processing paper eligible counts are 0 | No signal currently satisfies Paper evidence requirements. | link, lineage, freshness, orderbook, risk, exit | 4C-R Paper Eligibility Gate | Explicit Paper eligibility candidates | Candidates exist only when all evidence contracts pass | Codex |
| `SIGNAL_LINKING_TOO_LOW` | true | HIGH | `signal_market_links=20`, `neuron_signals=147` | Most signals cannot be mapped to a market, so they cannot become Paper candidates. | Market identifiers, matcher evidence | 4C-N Signal / Market Binding Recovery | Higher trusted market-link coverage, no forced weak links | Link coverage improves; weak evidence remains review-only | Claude Code |
| `SIGNALS_STALE_HIGH` | true | HIGH | mesh blocker active; stale signal layers report high stale counts | Stale signals should not drive Paper candidate creation. | producer freshness, source cadence | 4C-M / 4C-N | fresh runtime signal generation and stale filtering | Paper gate rejects stale signals; dashboard stale count decreases | Claude Code |
| `SIGNAL_QUALITY_GATE_BLOCKED` | true | HIGH | mesh blocker active; `can_feed_paper=0` | Quality gate blocks all current signals from Paper evidence. | link, lineage, freshness, evidence completeness | 4C-R Paper Eligibility Gate | hard gate that explains each failure | All candidates carry pass/fail reasons | Codex |
| `SIGNAL_LINEAGE_COVERAGE_LOW` | true | HIGH | lineage coverage layer active blocker | Signals cannot fully prove origin/payload/producer. | producer metadata and raw payload refs | 4C-N / 4C-R | complete lineage for candidate signals | Candidate signals have producer/source/correlation/raw payload/generated_from | Claude Code |
| `ENV_PERSISTED_MODE_MISMATCH` | true | HIGH | runtime blocker active; env mode differs from persisted mode | Operator intent and persisted governor truth disagree. Paper certification cannot rely on ambiguous mode. | State Governor/operator decision | Certification prep after gates | explicit reconciled DATA_ONLY/PAPER certification state | mismatch resolved only by audited operator action | Codex / Operator |
| `ENV_PERSISTED_KILL_SWITCH_MISMATCH` | true | HIGH | runtime blocker active | Kill-switch truth differs between env and persisted state. | State Governor/operator decision | Certification prep after gates | single authoritative kill truth | mismatch resolved only by audited operator action | Codex / Operator |
| `EXECUTION_NOT_ALLOWED` | true | CRITICAL for Paper, INFO as safety | runtime permissions cannot run Paper engine | Correctly prevents execution until Paper is certified. | Paper eligibility, risk, exit, intent engine | 4C-S / 4C-T | Paper execution permission remains gated | false until Paper engine is certified; never flips in 4C-L | Codex |
| `ORDER_INTENTS_ABSENT` | true as gap, not current failure | INFO / future critical | `order_intents` absent | No Paper intent gate exists. This is desired before Paper but must be built later. | Paper eligibility + risk + exit | 4C-S Paper Intent Gate | paper-only intent table and service | intents require thesis/risk/exit/orderbook refs | Codex |
| `PAPER_ORDERS_ZERO` | true as safety info | INFO | `paper_orders=0` | Good safety now; later Paper must write only simulated orders. | Paper intent gate | 4C-T Paper Execution Engine | paper-only order rows | orders link to intents; no live mutation | Codex |
| `PAPER_FILLS_ZERO` | true as gap; `paper_fills` absent | INFO / future critical | `paper_fills` absent, `fills_v2=1` old row | Paper needs a simulated fill ledger that is separate from real/live fills. | Paper execution engine | 4C-T / 4C-U / 4C-V | paper fill records and ledger | paper fills are simulated, auditable, and linked to Paper orders | Codex |
| `PAPER_POSITIONS_ZERO` | true as safety info | INFO / future critical | `paper_positions=0`, `positions=0` | Good safety now; Paper eventually needs simulated positions with exit plans. | Paper fills + exit | 4C-T / 4C-U | paper positions linked to exit plans | no orphan Paper positions | Codex |
| `NO_THESIS_PROFILES` | true | HIGH | `position_thesis_profiles=0` | Paper candidates need a thesis contract before simulated exposure. | linked signals + coordinator decision | 4C-O Thesis Profile Foundation | thesis profiles for candidates | every candidate/position has thesis_id | Claude Code / Codex |
| `NO_PAPER_INTENT_GATE` | true as audited gap | CRITICAL | `paper_intents` and `order_intents` absent | No safe intent boundary exists between coordinator output and Paper engine. | eligibility + risk + exit + orderbook | 4C-S Paper Intent Gate | paper intent gate and audit rows | cannot create intent without thesis/risk/exit/orderbook | Codex |
| `NO_PAPER_EXECUTION_ENGINE` | true as audited gap | CRITICAL | Paper simulator exists in legacy/runtime services, but no certified 4C Paper execution gate | Paper order creation must be canonical, simulated, and gated. | paper intents | 4C-T Paper Execution Engine | paper-only execution service | writes only paper tables; no live/shadow; tests prove counters | Codex |
| `NO_PAPER_EXIT_LOOP` | true as audited gap | CRITICAL | exit plan tables exist but no Paper exit loop evidence | Paper positions require monitored exits. | exit foundation + paper positions | 4C-U Paper Exit Loop | simulated exit lifecycle | Paper exits close positions through paper-only path | Codex |
| `NO_PAPER_PNL_LEDGER` | true as audited gap | HIGH | `paper_pnl_ledger` absent | Paper cannot be evaluated without PnL ledger truth. | paper fills + positions + exits | 4C-V Paper PnL + Ledger Truth | paper PnL ledger | no fake PnL; ledger reconciles orders/fills/positions | Codex |
| `NO_NO_TRADE_LEDGER` | partial | MEDIUM | `no_trade_log` exists with 0 rows | NO_TRADE is first-class but the current runtime coordinator outcomes are not yet ledgered as Paper readiness refusals. | coordinator + paper eligibility gate | 4C-X No-Trade Ledger | no-trade records for blocked candidates | every rejected candidate has durable reason | Claude Code / Codex |

## 5. Paper Readiness Dependency Map
| Dependency | Status | Why | Upstream | Downstream | Next action |
| --- | --- | --- | --- | --- | --- |
| Runtime Producer Evidence | READY / PARTIAL | Runtime evidence exists, but producer health remains degraded. | Sources/adapters | Runtime Signals | Keep as input; do not enable Paper. |
| Runtime Signals | PARTIAL | Signals exist but stale/linkage/lineage gaps remain. | Runtime producer evidence | Brain Outputs, signal gates | Improve freshness and binding. |
| Runtime Brain Outputs | READY | 100 runtime Brain Outputs exist, non-executing. | Runtime Signals | Runtime Coordinator | Preserve; do not create orders. |
| Runtime Coordinator Decisions | READY | 100 runtime Coordinator Decisions exist, all non-executing. | Runtime Brain Outputs | Paper candidate analysis | Preserve; continue to block execution. |
| Signal / Market Binding | BLOCKED | Link ratio remains too low. | Signals, markets | Orderbook, thesis, eligibility | 4C-N binding recovery. |
| Orderbook Snapshot Truth | MISSING | `orderbook_snapshots=0`. | linked markets | risk, exit, eligibility | 4C-M orderbook foundation. |
| Thesis Profile | MISSING | `position_thesis_profiles=0`. | coordinator outputs, linked markets | risk, exit, paper intent | 4C-O thesis foundation. |
| Risk Core | MISSING | risk evidence absent/0. | orderbook, thesis, eligibility | paper intent, execution allow | 4C-P risk foundation. |
| Exit Foundation | MISSING | `exit_plans=0`. | thesis, risk, orderbook | paper intent and exit loop | 4C-Q exit foundation. |
| Paper Eligibility Gate | MISSING | no `paper_eligibility` or candidates. | signals, orderbook, thesis, risk, exit | paper intents | 4C-R eligibility gate. |
| Paper Intent Gate | MISSING | no `paper_intents` or `order_intents`. | eligibility, risk, exit | paper execution | 4C-S paper intent gate. |
| Paper Execution Engine | MISSING / LEGACY PARTIAL | legacy/runtime simulator exists, but not certified in 4C chain. | paper intents | paper orders/fills/positions | 4C-T paper execution. |
| Paper Exit Loop | MISSING | no Paper exit lifecycle evidence. | paper positions + exit plans | PnL ledger | 4C-U paper exit loop. |
| Paper PnL Ledger | MISSING | no `paper_pnl_ledger`. | paper orders/fills/positions/exits | dashboard, soak | 4C-V ledger truth. |
| Paper Dashboard | PARTIAL | mesh blockers exist, Paper-specific dashboard is missing. | paper ledgers | operator certification | 4C-W Paper dashboard. |
| Paper Regression Suite | PARTIAL | old paper tests exist, full 4C Paper regression suite missing. | all Paper components | soak | 4C-Y regression suite. |
| 24h Paper Soak | BLOCKED | cannot soak without Paper engine and ledger. | full Paper stack | Shadow readiness | 4C-Z soak. |

## 6. DB / Table Gap Audit
Read-only DB table audit:

| Table or equivalent | Exists | Rows | Owner/service observed | Safe to reuse | Migration needed |
| --- | --- | ---: | --- | --- | --- |
| `orderbook_snapshots` | yes | 0 | Data foundation / market technical | yes | likely no, but freshness fields may need extension |
| `thesis_profiles` | no | n/a | none | no | no if `position_thesis_profiles` remains canonical |
| `position_thesis_profiles` | yes | 0 | `PositionThesisService` | yes | no for foundation, maybe extensions later |
| `risk_decisions` | no | n/a | none | no | likely yes |
| `risk_gate_runs` | yes | 0 | risk routes/services | partial | maybe extension for Paper candidate IDs |
| `exit_plans` | yes | 0 | exit routes/services | yes | maybe extension for Paper candidate IDs |
| `paper_eligibility` | no | n/a | none | no | yes |
| `paper_ready_candidates` | no | n/a | none | no | yes |
| `paper_intents` | no | n/a | none | no | yes |
| `order_intents` | no | n/a | none | no | only if chosen as canonical name |
| `paper_orders` | yes | 0 | `runtime_paper_trading` / paper repositories | yes | maybe extension for intent IDs |
| `paper_fills` | no | n/a | none | no | yes |
| `paper_positions` | yes | 0 | paper repositories | yes | maybe extension for exit plan linkage |
| `paper_trades` | no | n/a | none | no | maybe, if separate from fills/orders |
| `paper_pnl_ledger` | no | n/a | none | no | yes |
| `no_trade_log` | yes | 0 | no-trade services | yes | maybe extension for Paper candidate refs |
| `signal_market_links` | yes | 20 | impact graph / link coverage | yes | no |
| `runtime_coordinator_decisions` | no | n/a | represented in `coordinator_decisions` | yes via metadata | no |
| `runtime_brain_outputs` | no | n/a | represented in `brain_outputs` | yes via metadata | no |
| `brain_outputs` | yes | 148 | Brain Output services | yes | no |
| `coordinator_decisions` | yes | 112 | Coordinator services | yes | no |
| `runtime_brain_producer_runs` | yes | 1 | runtime brain adapter | yes | no |
| `runtime_coordinator_runs` | yes | 1 | runtime coordinator | yes | no |

Additional safety tables:

| Table | Exists | Rows |
| --- | --- | ---: |
| `paper_positions` | yes | 0 |
| `positions` | yes | 0 |
| `shadow_orders` | yes | 0 |
| `live_orders` | yes | 0 |
| `fills_v2` | yes | 1 pre-existing historical row |

## 7. API Gap Audit
| Area | Exists | Current route | Missing route proposal | Read-only or mutating | Executor |
| --- | --- | --- | --- | --- | --- |
| Dashboard mesh | yes | `/dashboard/api/v2/mesh` | none | read-only | n/a |
| Mesh blockers | yes | `/dashboard/api/v2/mesh-blockers` | none | read-only | n/a |
| Runtime producer evidence | yes | `/dashboard/api/v2/runtime-producer-evidence`, `/producers/runtime-evidence/run` | none | read-only dashboard, mutating evidence run | n/a |
| Runtime brain | yes | `/dashboard/api/v2/runtime-brain`, `/brain/runtime/run` | none | read-only dashboard, mutating brain run | n/a |
| Runtime coordinator | yes | `/dashboard/api/v2/runtime-coordinator`, `/coordinator/runtime/run` | none | read-only dashboard, mutating coordinator run | n/a |
| Signal quality | yes | `/dashboard/api/v2/signal-quality`, `/signals/quality/*` | none | mixed | n/a |
| Signal processing | yes | `/dashboard/api/v2/signal-processing`, `/signals/processing/*` | none | mixed | n/a |
| Link coverage | yes | `/dashboard/api/v2/link-coverage`, `/signals/link-coverage/*` | none | mixed | n/a |
| Lineage coverage | yes | `/dashboard/api/v2/lineage-coverage`, `/signals/lineage-coverage/*` | none | mixed | n/a |
| Dry-run provenance | yes | `/dashboard/api/v2/dry-run-provenance` | none | read-only dashboard | n/a |
| Producer health | yes | `/dashboard/api/v2/producer-health` | none | read-only dashboard | n/a |
| Orderbook | partial | `/markets/{market_id}/orderbook/latest`, `/data-foundation/coverage` | `/dashboard/api/v2/orderbook-snapshots` | read-only; collector later mutating | Codex |
| Thesis | yes | `/dashboard/api/v2/thesis`, `/thesis/*` | Paper-candidate thesis route later | mixed | Claude Code / Codex |
| Risk | partial | `/dashboard/api/v2/risk`, `/risk/*` | `/paper/risk/evaluate`, `/dashboard/api/v2/paper-risk` | mutating risk run + read-only dashboard | Codex |
| Exit | partial | `/dashboard/api/v2/exits`, `/exits/*` | `/paper/exits/evaluate`, `/dashboard/api/v2/paper-exits` | mutating exit run + read-only dashboard | Codex |
| Paper eligibility | no | none | `/paper/eligibility/evaluate`, `/dashboard/api/v2/paper-eligibility` | mutating local evaluation + read-only dashboard | Codex |
| Paper intents | no | none | `/paper/intents/create`, `/paper/intents/recent` | mutating paper-only | Codex |
| Paper execution | partial legacy | `/execution/paper/simulate` | `/paper/execution/run`, `/dashboard/api/v2/paper-execution` | mutating paper-only | Codex |
| Paper positions | partial | dashboard positions/orders legacy | `/paper/positions/recent`, `/dashboard/api/v2/paper-positions` | read-only and paper-only mutation via engine | Codex |
| Paper PnL | no | none | `/dashboard/api/v2/paper-pnl` | read-only plus ledger updater | Codex |
| No-trade | yes | `/dashboard/api/v2/no-trade`, `/no-trade/*` | `/paper/no-trade/recent` | read-only plus candidate logging | Claude Code / Codex |

## 8. Test Gap Audit
Existing relevant tests:

- 4C consolidated regression tests exist and pass.
- Runtime producer evidence tests exist.
- Runtime brain adapter tests exist.
- Runtime coordinator tests exist.
- Mesh blockers tests exist.
- Dashboard mesh tests exist.
- Signal quality, processing, link coverage, lineage coverage, dry-run provenance, and producer health tests exist.
- Older orderbook, risk, exit, no-trade, paper execution simulator tests exist.

Missing or incomplete Paper-readiness test groups:

| Test group | Status | Needed before Paper |
| --- | --- | --- |
| Orderbook snapshot freshness tests | partial old coverage | Must prove fresh persisted snapshots and stale rejection. |
| Thesis profile candidate tests | partial | Must require thesis for every Paper candidate. |
| Risk core Paper candidate tests | missing in 4C chain | Must prove risk decisions are enforced before intents. |
| Exit foundation Paper candidate tests | missing in 4C chain | Must prove exit plans are required before intents. |
| Paper eligibility tests | missing | Must prove only fully evidenced candidates pass. |
| Paper intent gate tests | missing | Must prove intents require signal, market, orderbook, thesis, risk, exit. |
| Paper execution tests | partial legacy | Must prove paper-only orders/fills/positions and no live mutations. |
| Paper exit tests | missing in full Paper chain | Must prove exits close Paper positions safely. |
| Paper PnL ledger tests | missing | Must prove ledger reconciles simulated fills/positions. |
| No-trade ledger tests | partial | Must prove blocked candidates log durable NO_TRADE reasons. |
| Paper full regression suite | missing | Must cover all Paper gates together. |
| Soak readiness tests | missing | Must verify 24h Paper run criteria and safety invariants. |

## 9. Recommended Build Order
### 4C-M Orderbook Snapshot Foundation
Goal: persist fresh, non-executing orderbook snapshots for linked runtime markets.
Why now: Orderbook is a root blocker for risk, exit, and Paper eligibility.
Resolves: `ORDERBOOK_SNAPSHOTS_MISSING`.
Likely files: data foundation services, orderbook repositories, dashboard services, tests.
DB: maybe reuse `orderbook_snapshots`; extend only if freshness/evidence fields missing.
APIs: `/dashboard/api/v2/orderbook-snapshots`.
Tests: freshness, stale rejection, no orders.
Risk: medium because market data can influence later Paper gates.
Executor: Codex.
GREEN: fresh snapshots exist, dashboard truth updated, no Paper/execution mutation.

### 4C-N Signal / Market Binding Recovery
Goal: improve trusted signal-to-market binding without force-linking.
Why now: Paper candidates cannot exist without market identity.
Resolves: `SIGNAL_LINKING_TOO_LOW`, `SIGNALS_NOT_LINKED`, part of `NO_PAPER_ELIGIBLE_SIGNALS`.
Files: link coverage, impact graph, signal metadata, dashboard.
DB: likely no new core truth; maybe binding audit extensions.
APIs: link coverage review/apply with strict audit if needed.
Tests: weak suggestions remain suggestions, safe links require evidence.
Risk: medium because false links poison Paper.
Executor: Claude Code for focused implementation; Codex review if applying links.
GREEN: trusted link coverage improves, weak links blocked, Paper still false.

### 4C-O Thesis Profile Foundation
Goal: create non-executing thesis profiles for Paper candidates.
Why now: No entry without thesis.
Resolves: `NO_THESIS_PROFILES`.
Files: position thesis service/repository/dashboard.
DB: reuse `position_thesis_profiles`; extend if candidate refs missing.
APIs: Paper candidate thesis read/evaluate routes.
Tests: every candidate requires thesis; no orders.
Risk: medium.
Executor: Claude Code or Codex.
GREEN: thesis profiles exist for eligible candidates only, no execution mutation.

### 4C-P Risk Core Foundation
Goal: enforce risk decisions for Paper candidates.
Why now: Paper intent cannot exist without risk approval/block.
Resolves: `NO_RISK_CORE`, part of `EXECUTION_NOT_ALLOWED`.
Files: risk services/routes/repositories, mesh blockers.
DB: risk decisions or risk gate run extensions.
APIs: `/paper/risk/evaluate`, dashboard paper risk.
Tests: missing risk blocks, risk rejection logs no-trade, no orders.
Risk: high; Codex.
GREEN: every candidate has enforceable risk decision; no bypass.

### 4C-Q Exit Foundation
Goal: produce exit plans before Paper intent.
Why now: No entry without exit plan.
Resolves: `NO_EXIT_FOUNDATION`.
Files: exit services/routes/repositories, mesh blockers.
DB: reuse/extend `exit_plans`.
APIs: `/paper/exits/evaluate`, dashboard paper exits.
Tests: missing exit blocks; exit plan required by intent gate.
Risk: high; Codex.
GREEN: every candidate has exit plan or explicit NO_TRADE block.

### 4C-R Paper Eligibility Gate
Goal: classify Paper-ready candidates from runtime coordinator decisions.
Why now: It is the boundary before intents.
Resolves: `NO_PAPER_ELIGIBLE_SIGNALS`, quality/link/lineage/orderbook/risk/exit blockers when data passes.
Files: new paper eligibility service/repository/routes/dashboard.
DB: `paper_eligibility` or `paper_ready_candidates`.
APIs: evaluate/recent/dashboard.
Tests: full evidence required, dry-run rejected, stale rejected.
Risk: high; Codex.
GREEN: candidates pass only with all evidence; `paper_ready` still false until full certification.

### 4C-S Paper Intent Gate
Goal: create paper-only intents from eligible candidates.
Why now: It separates coordinator from paper execution.
Resolves: `NO_PAPER_INTENT_GATE`, `ORDER_INTENTS_ABSENT`.
Files: paper intent service/repository/routes/dashboard.
DB: `paper_intents` or canonical `order_intents`.
APIs: create/recent/audit.
Tests: intent requires thesis/risk/exit/orderbook; no orders by intent creation alone.
Risk: high; Codex.
GREEN: paper intents exist safely; no orders until execution phase.

### 4C-T Paper Execution Engine
Goal: convert paper intents into simulated paper orders/fills/positions only.
Why now: execution must remain paper-only and auditable.
Resolves: `NO_PAPER_EXECUTION_ENGINE`, `PAPER_ORDERS_ZERO`, `PAPER_FILLS_ZERO`, `PAPER_POSITIONS_ZERO` when run.
Files: runtime paper trading, paper repositories/routes/dashboard.
DB: paper fill/trade extensions likely needed.
APIs: `/paper/execution/run`, dashboard.
Tests: no live/shadow, no signing, no orphan rows.
Risk: high; Codex.
GREEN: paper tables mutate only in Paper simulation; live remains zero.

### 4C-U Paper Exit Loop
Goal: monitor and close simulated Paper positions using exit plans.
Why now: Paper positions cannot be allowed without exit lifecycle.
Resolves: `NO_PAPER_EXIT_LOOP`.
Files: exit and paper position services.
DB: exit event/closure links.
APIs: paper exit loop run/dashboard.
Tests: exits close paper positions; no live mutation.
Risk: high; Codex.
GREEN: simulated exits are auditable and linked to plans.

### 4C-V Paper PnL + Ledger Truth
Goal: calculate durable Paper PnL from simulated orders/fills/positions/exits.
Why now: Paper performance must be inspectable.
Resolves: `NO_PAPER_PNL_LEDGER`.
Files: paper ledger service/repository/dashboard.
DB: `paper_pnl_ledger`.
APIs: dashboard paper pnl.
Tests: ledger reconciliation, no fake PnL.
Risk: medium/high; Codex.
GREEN: ledger reconciles all simulated lifecycle rows.

### 4C-W Paper Dashboard Full
Goal: expose Paper readiness and Paper run truth.
Why now: operators need truth before soak.
Resolves: dashboard gaps.
Files: dashboard services/routes/UI.
DB: no new source truth expected.
APIs: dashboard paper overview.
Tests: `mock_data=false`, blocker visibility, safety counters.
Risk: medium.
Executor: Claude Code after APIs stabilize.
GREEN: dashboard shows Paper truth without fake readiness.

### 4C-X No-Trade Ledger
Goal: persist NO_TRADE outcomes for blocked Paper candidates.
Why now: NO_TRADE is first-class and must be measurable.
Resolves: `NO_NO_TRADE_LEDGER`.
Files: no-trade services/routes/dashboard.
DB: reuse/extend `no_trade_log`.
APIs: paper no-trade dashboard.
Tests: every rejected candidate logs a reason.
Risk: medium.
Executor: Claude Code; Codex if integrated into gates.
GREEN: blocked candidates have durable explanations.

### 4C-Y Paper Full Regression Suite
Goal: prove the full Paper evidence chain and safety invariants.
Why now: Required before soak.
Resolves: test coverage gap.
Files: tests only plus fixtures.
DB: no new source truth.
APIs: no new routes.
Tests: full chain, safety, dashboard, no live.
Risk: medium.
Executor: Codex.
GREEN: full suite passes consistently.

### 4C-Z 24h Paper Soak
Goal: run a 24h Paper-only soak with full evidence and ledgers.
Why now: Final certification evidence before Shadow discussion.
Resolves: soak gap.
Files: scripts/reports/docs.
DB: no new schema expected.
APIs: dashboard verification.
Tests: soak monitor and post-run audit.
Risk: high operational.
Executor: Codex / Operator.
GREEN: 24h report proves Paper-only operation, no live mutation, stable dashboards, reconciled ledger.

## 10. Paper-Ready Definition
POLYBOT is Paper-ready only when all of these are true:

- Runtime producers are active and not only dry-run.
- Runtime Signals exist with complete producer/source/correlation/raw payload/generated_from metadata.
- Runtime Brain Outputs exist and are generated only from runtime Signals.
- Runtime Coordinator Decisions exist and remain non-executing until Paper gates approve.
- Signal/market bindings are trusted and evidence-backed.
- Signal lineage is complete enough for candidate evidence.
- Orderbook snapshots exist, are fresh, and are linked to candidate markets.
- Thesis profiles exist for every Paper candidate.
- Risk decisions exist, are enforced, and can block candidates.
- Exit plans exist, are enforced, and can block candidates.
- Paper eligibility candidates exist only when every upstream evidence requirement passes.
- Paper intents can be created safely and require thesis, risk decision, exit plan, orderbook snapshot, signal/market binding, and coordinator decision.
- Paper execution engine exists and mutates only canonical paper tables.
- Paper exit loop works and closes simulated positions through paper-only paths.
- Paper PnL ledger reconciles simulated orders, fills, positions, and exits.
- No live orders are created.
- No shadow orders are created until Shadow phase.
- No real fills are created.
- Dashboard endpoints return `mock_data=false`.
- Full Paper regression suite is green.
- 24h Paper soak is green.

## 11. Safety Invariants
Non-negotiable invariants:

- `live_orders=0`.
- `shadow_orders=0` until a separate Shadow phase.
- No real orders.
- No signing.
- No private keys printed or used.
- No live execution.
- `paper_only=true` for Paper simulation.
- Every Paper intent requires `thesis_id`, `risk_decision_id`, `exit_plan_id`, and `orderbook_snapshot_id`.
- Every Paper order must be linked to a Paper intent.
- Every Paper position must have an exit plan.
- No orphan Paper positions.
- No fake PnL.
- No mock dashboard success.
- Missing data means `NO_TRADE`.
- State Governor is never bypassed.
- Risk Gate is never bypassed.
- `paper_ready` remains false until all critical blockers are inactive and certification evidence exists.
- `execution_allowed` remains false until certified Paper execution phase explicitly changes only Paper simulation behavior.

## 12. Tests Run
Commands run during this audit:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py -q
```

Result: `46 passed, 1 warning in 170.37s`.

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_brain_adapter_contract.py tests/test_v2_runtime_brain_adapter_service.py tests/test_v2_runtime_brain_adapter_api.py tests/test_v2_dashboard_runtime_brain.py tests/test_v2_runtime_brain_adapter_safety.py tests/test_v2_runtime_coordinator_contract.py tests/test_v2_runtime_coordinator_service.py tests/test_v2_runtime_coordinator_api.py tests/test_v2_dashboard_runtime_coordinator.py tests/test_v2_runtime_coordinator_safety.py -q
```

Result: `25 passed, 1 warning in 195.94s`.

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_v2_mesh_blockers_contract.py tests/test_v2_mesh_blockers_service.py tests/test_v2_mesh_blockers_api.py tests/test_v2_dashboard_mesh_blockers.py tests/test_v2_mesh_blockers_safety.py tests/test_v2_dashboard_mesh.py -q
```

Result: `17 passed, 1 warning in 82.08s`.

Warnings were FastAPI/TestClient deprecation warnings, not audit failures.

## 13. What Must Remain False
Until Paper is truly safe:

- `paper_ready=false`
- `execution_allowed_true=0`
- `order_intents` absent or 0
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- new fills created by 4C phases = 0
- positions = 0
- live trading disabled
- no signing path active

## 14. Next Five Build Prompts
1. V2 Neural Mesh Part 4C-M: Orderbook Snapshot Foundation.
2. V2 Neural Mesh Part 4C-N: Signal / Market Binding Recovery.
3. V2 Neural Mesh Part 4C-O: Thesis Profile Foundation.
4. V2 Neural Mesh Part 4C-P: Risk Core Foundation.
5. V2 Neural Mesh Part 4C-Q: Exit Foundation.

## 15. Final Audit Status
GREEN.

The audit is complete, blockers and dependencies are mapped, no unsafe mutations were made, `paper_ready=false`, `execution_allowed_true=0`, no orders/intents/fills/positions/live actions were created, and the requested regression checks passed.
