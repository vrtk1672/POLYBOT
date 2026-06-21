# POLYBOT Full Dress Rehearsal 30m Report

- run_id: `active_30m_observation_20260603T130348Z`
- dress_log: `logs/observation/full_dress_rehearsal_30m_20260603T130348Z.log`
- source_runner_report: `docs/POLYBOT_ACTIVE_30M_OBSERVATION_REPORT_20260603T130348Z.md`
- status: `RED`
- stop_reason: `CAPITAL_RECONCILIATION_RED`
- security_governance_status: `YELLOW_ACCEPTED_BY_OPERATOR`
- started_at_utc: `2026-06-03T13:03:48.534339+00:00`
- stopped_at_utc: `2026-06-03T13:04:52.769582+00:00`
- duration: about 1 minute 4 seconds
- samples: 1
- active_cycles_completed: 1
- final_system_power: `OFF`
- runtime_mode: `PAPER`

## Preflight

Preflight was `SAFE-YELLOW`.

Blockers: none.

Allowed warnings:

- `SAFE_YELLOW_AI:['COMPLETED', 'OK', 'OLLAMA_TIMEOUT']`
- security governance remains `YELLOW_ACCEPTED_BY_OPERATOR`

Verified before start:

- `/healthz`: OK
- `/runtime/health`: `SAFE_STOPPED` while SYSTEM OFF
- SYSTEM: OFF and controllable
- runtime mode: PAPER
- live enabled: false
- shadow enabled: false
- dashboard truth endpoints: `mock_data=false`
- Paper lineage: OK
- capital reconciliation: OK before run
- active positions without fills: 0
- safe env audit: OK, raw values printed false

## Active Cycle Result

The run started SYSTEM ON and completed one active cycle before the hard stop.

Components that ran:

- source-to-neuron: OK
- fresh market identity: OK
- CLOB token book verification: OK
- live orderbook watcher: OK
- fresh seed paper path: OK
- open position watchdog: OK, but it ran before new Paper positions opened and checked 0 positions
- Paper execution: DEGRADED after creating Paper artifacts through official path
- Paper exits: OK

Cycle outputs:

- source-to-neuron events created: 7
- source-to-neuron sessions updated: 7
- source-to-neuron brain opinions created: 10
- source-to-neuron coordinator decisions created: 2
- fresh identity candidates checked: 100
- fresh identity stale candidates: 100
- CLOB checks attempted: 20
- CLOB books verified: 18
- CLOB snapshots created by verification: 18
- live watcher items checked: 20
- live watcher orderbooks refreshed: 20
- live watcher events published: 22
- fresh seed paper path seeds checked: 20
- fresh seed paper path converted candidates: 20
- fresh seed paper path new intents this cycle: 0

Fresh seed paper path blockers this cycle:

- `BLOCKED_NO_TRUSTED_ORDERBOOK`: 2
- `EXIT_NOT_READY`: 2
- `MISSING_EXECUTABLE_PRICE`: 4

## Event Deltas

Events created during the run:

- `ORDERBOOK_REFRESHED`: +21
- `SPREAD_CHANGED`: +3
- `NEWS_DETECTED`: +2
- `AI_CONTEXT_UPDATED`: +1
- `LIQUIDITY_CHANGED`: +1
- `MARKET_REPRICING`: +1

Total neural event delta: +29.

Mesh and brain deltas:

- mesh sessions: +4
- shared awareness endpoint count: +4 during sample, +11 DB records updated after run window
- brain opinions: +16 during sample, +55 DB opinions created after run window
- mesh coordinator decisions: +4 during sample, +11 DB decisions created after run window
- capital evaluations: +4

## Paper Movement

Paper moved through the official Paper path.

Before to after:

- paper intents: 20 -> 20
- paper orders: 9 -> 12, delta +3
- paper fills: 6 -> 9, delta +3
- paper positions: 9 -> 12, delta +3
- paper position closes: 6 -> 8, delta +2
- paper trade ledger: 12 -> 17, delta +5
- open paper positions: 0 -> 1
- closed paper positions: 6 -> 8

No real/live mutation:

- live orders: 0 -> 0
- orders_v2: 1 -> 1
- fills_v2: 1 -> 1
- canonical positions: 0 -> 0
- real orders current: 1 -> 1

## Trade Details

Opened and closed:

1. `037d14fa-7ced-59aa-9a79-26f02a4da6b7`
   - market: `691547`
   - side: YES
   - source intent: `paper_intent_eligibility_exit_risk_thesis_fresh_seed_coord_fresh_seed_691547_YES`
   - entry: 0.730000
   - quantity: 6.849300
   - exit: 0.290000
   - exit reason: `STOP_LOSS`
   - realized PnL: -3.013692
   - exit plan: `exit_risk_thesis_fresh_seed_coord_fresh_seed_691547_YES`
   - risk decision: `risk_thesis_fresh_seed_coord_fresh_seed_691547_YES`

2. `37cc2678-fc51-5d0b-8cb8-6d1a91985df8`
   - market: `691547`
   - side: NO
   - source intent: `paper_intent_eligibility_exit_risk_thesis_fresh_seed_coord_fresh_seed_691547_NO`
   - entry: 0.730000
   - quantity: 6.849300
   - exit: 0.710000
   - exit reason: `TAKE_PROFIT`
   - realized PnL: -0.136986
   - exit plan: `exit_risk_thesis_fresh_seed_coord_fresh_seed_691547_NO`
   - risk decision: `risk_thesis_fresh_seed_coord_fresh_seed_691547_NO`

Opened and still open:

3. `7668d890-0fe3-5aa3-bc32-996a2f121da2`
   - market: `598936`
   - side: YES
   - source intent: `paper_intent_eligibility_exit_risk_thesis_fresh_seed_coord_fresh_seed_598936_YES`
   - entry: 0.016000
   - quantity: 10.000000
   - mark: 0.012000
   - unrealized PnL: -0.040000
   - status: OPEN

## Capital

Before:

- current balance: 1000.000000
- available balance: 1000.000000
- locked balance: 0.000000
- open exposure: 0.000000
- realized PnL: 23.550000
- unrealized PnL: 0.000000

After:

- current balance: 996.849322
- available balance: 996.849322
- locked balance: 0.000000
- open exposure: 0.000000
- realized PnL: -3.150678
- unrealized PnL endpoint: -0.040000
- account unrealized PnL: 0.000000
- capital reconciliation: RED
- reconciliation error: `OPEN_EXPOSURE_MISMATCH`

Capital ledger rows created:

- 3 position open ledger rows
- 2 close ledger rows

Capital account ledger rows created include releases and realized PnL for the two closed positions, but the remaining open position has no retained locked balance/open exposure in the account summary. That caused the hard stop.

## Position Watchdog

The watchdog ran in the active cycle before Paper execution created the new open position.

- positions checked: 0
- locks created: 0
- position token locks after run: 0
- watchdog events: 0

The new open Paper position therefore has no position token lock yet.

## Hard Stop

Hard stop triggered correctly:

- reason: `CAPITAL_RECONCILIATION_RED`
- exact reconciliation error: `OPEN_EXPOSURE_MISMATCH`
- SYSTEM OFF command succeeded
- final `system_state.system_power`: OFF

This was the correct behavior under the rehearsal hard-stop rules. Continuing would have allowed an open Paper position to remain active while capital accounting reported no locked/open exposure.

## Safety Status

- live enabled: false
- shadow enabled: false
- live orders: 0
- real orders delta: 0
- orders_v2 delta: 0
- fills_v2 delta: 0
- canonical positions delta: 0
- paper lineage active status: OK
- active positions without fills: 0
- mock dashboard data: false
- secrets exposed: false
- fake orderbooks: not detected
- fake AI context: not detected

## Final Status

The dress rehearsal did not complete 30 minutes. It started safely, ran one real active Paper cycle, created real Paper simulation artifacts through the official path, then hard-stopped safely on capital reconciliation RED.

Phase status: `RED`.

Recommended next step: fix paper capital reconciliation for open positions so locked balance/open exposure remains coherent after Paper execution and partial/early Paper Exit activity, then rerun the 30-minute dress rehearsal from SYSTEM OFF.
