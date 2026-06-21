# POLYBOT V2 Roadmap

## Critical Priority Order

1. System control
2. Event Mesh
3. Data Truth
4. Cost-efficient AI
5. Full neurons
6. Memory
7. Opportunity
8. Engines
9. Capital
10. Risk
11. Execution
12. Exit
13. No-Trade
14. Dashboard
15. Learning
16. Paper
17. Shadow
18. Small Live

## Phase Template

Each phase must define goal, built components, DB impact, API impact, dashboard impact, tests, Definition of Done, dependencies, and do-not-do-yet warnings.

## V2.0 Core Runtime Foundation

- Goal: create one runtime authority for mode, permissions, cycle ledger, service health, and safe startup.
- Built: State Governor, Mode Manager, runtime contracts, runtime routes, health truth, safe startup.
- DB impact: `system_state`, `system_state_history`, `runtime_cycles_v2`, `service_health`, `runtime_incidents`.
- API impact: `/runtime/*`.
- Dashboard impact: runtime truth panel.
- Tests: modes, transitions, governor, orchestrator, API, integration guards.
- Definition of Done: safe startup to `DATA_ONLY`, KILL blocks trading, no live enabled.
- Dependencies: existing FastAPI/Postgres runtime.
- Do not do yet: Event Bus or live enablement.

## V2.1 Event Bus / Neural Mesh Foundation

- Goal: add event envelope, publish/subscribe contracts, and durable event recording.
- Built: event contracts, bus service, event repositories, foundational neuron registration.
- DB impact: event ledger and consumer checkpoint tables.
- API impact: read-only event inspection endpoints.
- Dashboard impact: event flow and consumer status.
- Tests: publish, consume, idempotency, ordering, replay, failure handling.
- Definition of Done: services can emit and consume events without trading behavior changes.
- Dependencies: V2.0 and V2.0.1 green.
- Do not do yet: implement all neurons or strategy engines.

## V2.2 Data Foundation Complete

- Goal: establish canonical data truth across markets, prices, orderbooks, liquidity, rules, and settlements.
- Built: normalized data contracts, repositories, ingestion validation, freshness checks.
- DB impact: canonical data tables and lineage metadata.
- API impact: data truth endpoints.
- Dashboard impact: freshness and coverage panels.
- Tests: schema, ingestion, stale data, malformed data, lineage.
- Definition of Done: missing or stale data produces explicit blocked/no-trade state.
- Dependencies: Event Bus foundation.
- Do not do yet: advanced AI interpretation.

## V2.3 Hybrid AI Brain

- Goal: add cost-aware AI interpretation and synthesis under strict controls.
- Built: AI task contracts, budget checks, model routing, result ledger.
- DB impact: AI runs, prompts metadata, outputs, costs, cache.
- API impact: AI status and audit endpoints.
- Dashboard impact: AI usage, cost, freshness, failures.
- Tests: budget limits, cache, fallback, no execution authority.
- Definition of Done: AI informs context but cannot trade or bypass risk.
- Dependencies: Data Foundation.
- Do not do yet: autonomous strategy routing.

## V2.4 News Neuron

- Goal: detect external news catalysts and market linkage.
- Built: news ingestion, dedupe, relevance scoring, event emissions.
- DB impact: news source, article, normalization, link tables.
- API impact: news/event query endpoints.
- Dashboard impact: catalyst panel.
- Tests: dedupe, relevance, stale news, source failure.
- Definition of Done: news can trigger context updates, not trades.
- Dependencies: Event Bus and Data Foundation.
- Do not do yet: trade from news alone.

## V2.5 Rules / Wording / Compliance Neuron

- Goal: evaluate market wording and resolution risk.
- Built: wording parser, ambiguity scoring, compliance notes.
- DB impact: rules analysis and wording risk tables.
- API impact: wording risk endpoints.
- Dashboard impact: wording warnings.
- Tests: ambiguous rules, missing rules, versioning.
- Definition of Done: high wording risk blocks or penalizes opportunities.
- Dependencies: Hybrid AI Brain.
- Do not do yet: legal advice or compliance automation.

## V2.6 Social / Hype Neuron

- Goal: measure attention, narrative velocity, and hype risk.
- Built: social source connectors, hype scoring, trend events.
- DB impact: social signals and source metadata.
- API impact: hype signal endpoints.
- Dashboard impact: social/hype panel.
- Tests: source failure, dedupe, stale signals.
- Definition of Done: hype improves context and risk scoring.
- Dependencies: Event Bus.
- Do not do yet: chase hype without liquidity and risk checks.

## V2.7 Whale Neuron

- Goal: upgrade whale activity into structured predictive context.
- Built: whale detection, profile updates, behavior classification.
- DB impact: whale profiles, activity, classification tables.
- API impact: whale context endpoints.
- Dashboard impact: whale pressure and reversal panels.
- Tests: large trade detection, false positives, profile updates.
- Definition of Done: whale context emits events and penalties/boosts.
- Dependencies: Data Foundation.
- Do not do yet: copy whale trades blindly.

## V2.8 Market / Orderbook / Liquidity / Time / Fees Neurons

- Goal: complete market microstructure intelligence.
- Built: neurons for price, orderbook, liquidity, time, fees, rewards.
- DB impact: orderbook snapshots, liquidity metrics, fee/reward tables.
- API impact: microstructure endpoints.
- Dashboard impact: liquidity, spread, time, and fee panels.
- Tests: wide spread, slippage, stale orderbook, time lockup.
- Definition of Done: bad liquidity or time-adjusted ROI can force `NO_TRADE`.
- Dependencies: Data Foundation.
- Do not do yet: execution routing.

## V2.9 Market Memory V2

- Goal: persist learned market behavior and historical setup outcomes.
- Built: memory contracts, similarity lookup, outcome feedback.
- DB impact: memory, setup, outcome, and feature tables.
- API impact: memory query endpoints.
- Dashboard impact: historical analog panel.
- Tests: retrieval, updates, stale memory, data lineage.
- Definition of Done: memory influences context but remains auditable.
- Dependencies: neurons emitting reliable truth.
- Do not do yet: black-box learning-only decisions.

## V2.10 Context Brain + Capital Brain

- Goal: synthesize full market context and capital state.
- Built: context assembler, capital availability and recycling logic.
- DB impact: context snapshots and capital state tables.
- API impact: context/capital endpoints.
- Dashboard impact: capital brain panel.
- Tests: conflicting signals, capital lockup, concentration.
- Definition of Done: context and capital decisions are explainable.
- Dependencies: Market Memory and core neurons.
- Do not do yet: execute trades.

## V2.11 Opportunity Cortex

- Goal: score opportunities using full edge, risk, timing, liquidity, and capital context.
- Built: opportunity score contracts, ranking, no-trade reasons.
- DB impact: opportunity snapshots and scoring breakdowns.
- API impact: opportunity endpoints.
- Dashboard impact: opportunity cortex panel.
- Tests: score components, penalties, no-trade, explainability.
- Definition of Done: opportunity output is decision-ready but not executable.
- Dependencies: Context Brain and Capital Brain.
- Do not do yet: strategy execution.

## V2.12 Strategy Router + Engines

- Goal: route opportunities into strategy engines.
- Built: SAFE, STRIKE, CONVEX, MAKER, HUNT, MOONSHOT_BASKET, REINVEST, NO_TRADE engines.
- DB impact: strategy decisions and engine metadata.
- API impact: strategy decision endpoints.
- Dashboard impact: strategy panel.
- Tests: engine selection, fallback, no-trade routing.
- Definition of Done: every opportunity has strategy or no-trade rationale.
- Dependencies: Opportunity Cortex.
- Do not do yet: live execution.

## V2.13 Capital Allocator V2 + Reinvest Brain

- Goal: allocate capital with recycling, sizing, and exposure rules.
- Built: allocator, reinvest rules, budget partitions.
- DB impact: allocation ledger and capital buckets.
- API impact: allocation endpoints.
- Dashboard impact: allocation and exposure panel.
- Tests: caps, recycling, reserve preservation, drawdown.
- Definition of Done: proposed size is bounded and explainable.
- Dependencies: Strategy Router.
- Do not do yet: bypass Risk Governor.

## V2.14 Risk Gate + Risk Governor

- Goal: formalize per-decision and system-wide risk authority.
- Built: Risk Gate, Risk Governor, exposure limits, drawdown rules, certification.
- DB impact: risk decisions, limits, incidents, approvals.
- API impact: risk state and approval endpoints.
- Dashboard impact: risk governor panel.
- Tests: kill, cooldown, caps, correlation, wording risk, missing data.
- Definition of Done: no trade can proceed without risk approval.
- Dependencies: V2.0 runtime modes and allocator.
- Do not do yet: live by default.

## V2.15 Execution Cortex V2

- Goal: execute approved actions through a guarded execution layer.
- Built: execution intents, adapters, idempotency, dry-run/live separation.
- DB impact: execution intents, order attempts, adapter responses.
- API impact: execution audit endpoints.
- Dashboard impact: execution panel.
- Tests: idempotency, rejection, mode blocks, adapter failure.
- Definition of Done: execution is safe, audited, and mode-checked.
- Dependencies: Risk Governor.
- Do not do yet: broad live launch.

## V2.16 Exit Cortex V2

- Goal: manage exits, reductions, invalidation, and profit-taking.
- Built: exit plans, exit signals, reduction logic.
- DB impact: exit plan and exit decision tables.
- API impact: exit endpoints.
- Dashboard impact: exit cortex panel.
- Tests: no entry without exit, invalidation, liquidity loss.
- Definition of Done: every position has monitored exit logic.
- Dependencies: Execution Cortex.
- Do not do yet: ignore original thesis.

## V2.17 No-Trade Intelligence

- Goal: make no-trade decisions first-class and learnable.
- Built: no-trade reason taxonomy, scoring, feedback.
- DB impact: no-trade ledger.
- API impact: no-trade query endpoints.
- Dashboard impact: no-trade intelligence panel.
- Tests: missing data, bad liquidity, weak edge, ambiguous rules.
- Definition of Done: no-trade is auditable and improves future behavior.
- Dependencies: Opportunity, Risk, Exit.
- Do not do yet: treat no-trade as failure.

## V2.18 Dashboard V2

- Goal: build an operator-grade truth surface.
- Built: runtime, neurons, opportunity, risk, execution, exit, learning panels.
- DB impact: none unless dashboard audit tables are needed.
- API impact: dashboard V2 endpoints.
- Dashboard impact: full V2 UI.
- Tests: truth only, no mock state, permissions, responsiveness.
- Definition of Done: dashboard reflects real DB/runtime truth.
- Dependencies: prior V2 truth layers.
- Do not do yet: fake controls.

## V2.19 Feedback / Learning Loop

- Goal: learn from outcomes, errors, missed trades, and no-trades.
- Built: feedback contracts, outcome ingestion, score calibration.
- DB impact: feedback and learning tables.
- API impact: learning endpoints.
- Dashboard impact: feedback panel.
- Tests: outcome matching, calibration, no black-box override.
- Definition of Done: learning improves scoring without bypassing safety.
- Dependencies: Memory, Opportunity, Execution, Exit.
- Do not do yet: autonomous self-modifying risk rules.

## V2.20 Paper Full System

- Goal: run full V2 in paper mode.
- Built: end-to-end paper path through neurons, brains, strategies, risk, execution, exit.
- DB impact: paper full-system run ledgers.
- API impact: paper run endpoints.
- Dashboard impact: paper validation dashboard.
- Tests: full paper cycle, no live orders, auditability.
- Definition of Done: full system can run safely without live actions.
- Dependencies: V2.0-V2.19.
- Do not do yet: live submission.

## V2.21 Shadow Live

- Goal: run live-like decisions without sending real orders.
- Built: shadow live execution simulation and comparison.
- DB impact: shadow decisions and simulated order tables.
- API impact: shadow endpoints.
- Dashboard impact: shadow/live comparison.
- Tests: no live sends, shadow fidelity, risk blocks.
- Definition of Done: live-like behavior is measured without real orders.
- Dependencies: Paper Full System green.
- Do not do yet: small live.

## V2.22 Small Live

- Goal: allow tightly constrained live execution after certification.
- Built: certification, live caps, operator approvals, emergency controls.
- DB impact: live certification and approval audit.
- API impact: live approval and status endpoints.
- Dashboard impact: live control and risk dashboard.
- Tests: certification, kill, cooldown, caps, no-env-live, incident handling.
- Definition of Done: small live is explicit, limited, observable, and reversible.
- Dependencies: Shadow Live green and Risk Governor certification.
- Do not do yet: scale, attack mode, or unattended broad live.
