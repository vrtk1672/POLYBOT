# POLYBOT Full SYSTEM ON 30-Minute Paper Run Report

Run id: `full_system_on_30m_20260603T111502Z_8ef18e4d`

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

Log: `logs/observation/full_system_on_30m_20260603T111458Z.log`

## Summary

POLYBOT ran a full safe PAPER runtime observation for 30 minutes with SYSTEM ON. Real source-backed events were produced, orderbooks refreshed, mesh sessions and awareness updated, brain opinions and coordinator decisions advanced, and paper execution/exit gates were allowed to run normally.

No live trading, shadow live, order/write endpoint use, real-order mutation, paper order/fill/position mutation, fake data, or hard stop occurred. No new Paper trades opened because the existing paper path found no valid executable paper intents.

Phase status: `YELLOW`

Reason: the run completed safely but produced no Paper trades, security governance remains accepted-risk yellow, and five extra legacy runtime service calls in the runner were invoked with incorrect constructor arguments. The V3 mesh path still updated through source-to-neuron and watcher events.

## Preflight

Status: `SAFE_YELLOW`

Allowed warning:

- `SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR`

Clean checks:

- `/healthz`: OK
- API container: healthy
- Postgres: healthy
- Redis: healthy
- SYSTEM before run: OFF
- Runtime mode: PAPER
- live allowed: false
- shadow allowed: false
- source status: OK
- paper dashboard: `mock_data=false`
- paper lineage: OK
- capital reconciliation: OK
- active positions without fills: 0
- live orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0

## Timing

- Start UTC: `2026-06-03T11:15:02Z`
- End UTC: `2026-06-03T11:46:05Z`
- Start local: `2026-06-03 14:15:02 Asia/Jerusalem`
- End local: `2026-06-03 14:46:05 Asia/Jerusalem`
- Duration: about 31 minutes including preflight/finalization
- Active cycles: 16
- Sample interval target: 2 minutes

## Cycle Counts

- Source-to-neuron cycles: 16
- Fresh identity cycles: 16
- CLOB verification cycles: 16
- Live orderbook watcher cycles: 16
- Position watchdog cycles: 16
- Paper intent cycles: 16
- Paper execution cycles: 16
- Paper exit cycles: 16
- Capital brain cycles: 16

## Event Deltas

- `neural_events`: 109 -> 382, delta +273
- `NEWS_DETECTED`: +29
- `MARKET_REPRICING`: +16
- `ORDERBOOK_REFRESHED`: +176
- `SPREAD_CHANGED`: +20
- `LIQUIDITY_CHANGED`: +16
- `AI_CONTEXT_UPDATED`: +16
- `WHALE_DETECTED`: +0
- `PNL_CHANGED`: +0
- `TOKEN_BOOK_UNAVAILABLE`: +0
- `MARKET_RESOLVED`: +0
- `POSITION_EXIT_RISK`: +0
- `EXIT_REVIEW`: +0
- `HOLD_REVIEW`: +0

## Mesh / Brain / Coordinator

- `mesh_sessions`: 37 -> 53, delta +16
- `mesh_shared_awareness`: 37 -> 53, delta +16
- `mesh_brain_opinions`: 151 -> 231, delta +80
- `mesh_coordinator_decisions`: 27 -> 43, delta +16
- `mesh_conflict_records`: 34 -> 50, delta +16

Source-to-neuron reported, across cycles:

- sessions updated: 1148
- awareness domain updates: 3869
- brain opinions created: 800
- coordinator decisions created: 160

The durable table deltas are lower because several mesh records are updated/upserted by stable session identity rather than appended every time.

## Identity / Token / Watcher

- `fresh_market_identity_runs`: 2 -> 18, delta +16
- `fresh_market_identity_traces`: 100 -> 1700, delta +1600
- `FRESH_VERIFIED`: +0
- `STALE_MARKET`: +1600
- `fresh_candidate_seeds`: 10 -> 10, delta 0
- `clob_token_book_verification_runs`: 2 -> 18, delta +16
- `clob_token_book_verification_traces`: 40 -> 680, delta +640
- CLOB checks attempted by cycle summaries: 160
- CLOB books verified by cycle summaries: 136
- CLOB rejections: 24 `SPREAD_TOO_WIDE`
- stale candidates skipped by CLOB verification: 320
- `orderbook_snapshots`: 26094 -> 26646, delta +552
- `trusted_orderbook_evidence_links`: 303 -> 1064, delta +761
- `live_orderbook_watchlist`: 10 -> 10, delta 0
- `live_orderbook_watcher_runs`: 2 -> 18, delta +16
- `live_orderbook_watcher_traces`: 10 -> 170, delta +160
- watcher orderbooks refreshed by cycle summaries: 160

## Position Watchdog

- Open positions at start: 0
- Open positions at end: 0
- `position_token_locks`: 0 -> 0, delta 0
- `open_position_watchdog_runs`: 2 -> 18, delta +16
- `open_position_watchdog_traces`: 0 -> 0, delta 0
- `position_awareness`: 1 -> 1, delta 0
- `position_reactions`: 5 -> 5, delta 0

Each watchdog cycle returned `NO_OPEN_POSITIONS`, so no lock or position event was created.

## Paper / Capital

- Paper trades opened: NO
- Paper trades closed: NO
- `paper_intents`: 6 -> 6, delta 0
- `paper_orders`: 9 -> 9, delta 0
- `paper_fills`: 6 -> 6, delta 0
- `paper_positions`: 9 -> 9, delta 0
- `paper_position_closes`: 6 -> 6, delta 0
- `paper_trade_ledger`: 12 -> 12, delta 0
- `paper_capital_ledger`: 1 -> 17, delta +16
- `paper_daily_pnl`: 2 -> 2, delta 0
- current balance: 1000.00 -> 1000.00
- available balance: 1000.00 -> 1000.00
- locked balance: 0.00 -> 0.00
- open exposure: 0.00 -> 0.00
- dashboard realized PnL: 23.55 -> 23.55
- capital account realized PnL: 0.00 -> 0.00
- unrealized PnL: 0.00 -> 0.00

The `paper_capital_ledger` delta was 16 zero-value `UNREALIZED_PNL_MARK` rows from the active runtime refresh. No balance or exposure changed.

## Why No Paper Trades Happened

The paper path ran normally, but no executable intent passed all required gates.

Observed blockers / conditions:

- `paper_execution` returned `NO_VALID_PAPER_INTENTS` in all 16 cycles.
- Current paper dashboard top blockers after run:
  - `MISSING_TRUSTED_ORDERBOOK`: 2760
  - `INTENT_ALREADY_EXECUTED`: 2046
- Fresh identity recovery sampled old candidate population and recorded `STALE_MARKET` for all 1600 checked traces.
- CLOB verification correctly skipped stale candidates and verified current fresh seed books instead.
- Position watchdog had no active open positions to monitor.

No thresholds were loosened and no Paper trade was forced.

## Runtime Step Notes

Successful every cycle:

- source-to-neuron
- deterministic side evidence
- fresh market identity
- CLOB token book verification
- trusted orderbook resolution
- live orderbook watcher
- capital brain
- paper eligibility
- post-side risk/exit readiness
- paper intents
- paper execution
- paper exit loop
- paper unrealized refresh
- position watchdog
- brain dialogue

Runner invocation errors every cycle:

- `RuntimeProducerEvidenceService.__init__()` received unsupported `system_power`
- `RuntimeBrainAdapterService.__init__()` received unsupported `system_power`
- `RuntimeCoordinatorDecisionService.__init__()` received unsupported `system_power`
- `RiskCoreService.__init__()` received unsupported `system_power`
- `ExitFoundationService.__init__()` received unsupported `system_power`

These were runner-call errors, not trading mutations. V3 mesh sessions, awareness, brain opinions, and coordinator decisions still updated through the source-to-neuron and watcher paths.

## Safety Before / After

- `live_orders`: 0 -> 0
- `orders_v2`: 1 -> 1
- `fills_v2`: 1 -> 1
- canonical `positions`: 0 -> 0
- active positions without fills: 0 -> 0
- fills without orders: 0 -> 0
- closed paper positions: 6 -> 6
- quarantined positions: 3 -> 3
- live enabled: false throughout
- shadow enabled: false throughout
- hard stop: not triggered
- final SYSTEM state: OFF

## Secret Exposure Check

- Raw `.env` was not printed.
- Raw `docker compose config` was not printed.
- Security endpoint returned `mock_data=false`.
- Safe guard status: OK.
- Docs secret scan: OK.
- Unsafe secret-printing patterns found by endpoint: none.
- Governance remains `YELLOW_ACCEPTED_BY_OPERATOR` until credential rotation is completed or formally accepted long-term.

## Tests / Validation

No source code changed during this mission, so pytest suites were not rerun.

Runtime validations performed:

- `/healthz`: OK before and after run.
- `/system/power`: OFF before, ON during run, OFF after run.
- Paper dashboard after run: `mock_data=false`, lineage OK, capital reconciliation OK.
- Security dashboard after run: no raw values returned, docs scan OK.
- Run log parsed successfully from `logs/observation/full_system_on_30m_20260603T111458Z.log`.

## Answers

1. Did SYSTEM ON really run? YES.
2. Was runtime mode PAPER? YES.
3. Did source-to-neuron cycles run? YES, 16 cycles.
4. Which sources produced data? News/RSS or NewsAPI path, Gamma market repricing, CLOB orderbook/spread/liquidity, AI context via fallback, and paper PnL refresh path.
5. Which neurons emitted events? News, Market, Orderbook, Liquidity, AI Context. Whale and PnL did not create new deltas.
6. How many events were created by type? See Event Deltas.
7. Did mesh sessions update? YES, +16 durable sessions.
8. Did shared awareness update? YES, +16 durable awareness rows.
9. Did brain opinions update? YES, +80 durable opinions.
10. Did coordinator decisions update? YES, +16 durable decisions.
11. Did capital brain evaluate? YES, 16 cycles.
12. Did watcher run? YES, 16 cycles.
13. Did position watchdog run? YES, 16 cycles, no open positions.
14. Did Paper intents/orders/fills/positions change? No new intents/orders/fills/positions.
15. Did balance change? NO.
16. Did PnL change? NO.
17. Paper trades happened? NO.
18. Top no-trade blockers? stale candidate identity, missing trusted orderbook, already-executed intents, no valid executable intents.
19. Safety status? Clean.
20. Final SYSTEM state? OFF.

## Remaining Risks

- The current candidate population remains dominated by stale market identities.
- Fresh CLOB seed books are real and verified, but they are not yet feeding a Paper-eligible candidate path strongly enough to produce executable intents.
- The run-loop helper should be corrected before reuse so legacy runtime producer/brain/coordinator/risk/exit calls are invoked with their repository-native constructors.
- Security governance remains accepted-risk yellow until rotation is completed or formally accepted as a standing risk.

## Recommended Next Step

Fix the run-loop service invocation shapes, then do a shorter controlled SYSTEM ON PAPER cycle that focuses on turning current fresh seed/watchlist intelligence into candidate/risk/exit/eligibility truth without touching live or shadow paths.
