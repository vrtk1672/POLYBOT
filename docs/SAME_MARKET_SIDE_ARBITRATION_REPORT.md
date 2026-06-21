# Same-Market Side Arbitration Report

## Purpose

Implement defense-aware same-market YES/NO arbitration for normal PAPER runtime so `SAME_MARKET_OPPOSING_ENTER_CONFLICT` no longer blocks every low-defense learning opportunity when one side has better evidence.

## Root Cause Audit

- Source file/function before repair: `app/services/paper_runtime_decisions.py::_arbitrate_same_market_opposing_enters`.
- Current behavior before repair: score-only arbitration. A strictly higher `opportunity_score` side stayed `ENTER`; equal scores caused both sides to be blocked with `SAME_MARKET_OPPOSING_ENTER_CONFLICT`.
- Stage A classification: `MISSING_DEFENSE_AWARE_ARBITRATION`, with `SCORE_COLLAPSE_TO_SAME_VALUE` as a frequent symptom.
- Typical conflicting markets: multiple current runtime markets, including `691547`, `597967`, `598936`, `610236`, `2354064`, `2365093`, and `597964`.
- Typical side scores: many sides collapse to `55.46`; market `691547` often has both sides at `61.99`.
- Available evidence: score, thesis/edge/exit states, orderbook age/freshness, best bid/ask, estimated liquidity, token verification, defense profile, warnings, and blockers.
- Missing evidence: no separate probability model or robust side-specific causal model for many rows. Exact ties remain unresolved at Defense 20 unless technical evidence separates the sides.

## Conflict Classifications

- `ARBITRATION_SELECTED_YES`
- `ARBITRATION_SELECTED_NO`
- `OPPOSING_SIDE_DEMOTED_BY_ARBITRATION`
- `SAME_MARKET_OPPOSING_SIDE_UNRESOLVED`
- `INTEGRITY_BLOCKER_PREVENTED_ARBITRATION`
- `TIE_BROKEN_BY_DEFENSE_ZERO`
- `TIE_BROKEN_BY_DETERMINISTIC_RULE`

## Arbitration Formula

The new `SameMarketSideArbitrator` scores each side using:

- opportunity score
- thesis support/watch/missing
- edge support
- exit readiness or fallback exit
- orderbook freshness and recency
- estimated liquidity/spread
- token/side evidence
- blocker severity
- integrity blockers

Integrity blockers cannot win arbitration.

## Defense-Aware Margin Rules

- Defense 100: margin >= 10
- Defense 80: margin >= 8
- Defense 60: margin >= 6
- Defense 40: margin >= 4
- Defense 20: margin >= 2
- Defense 0: margin >= 0, with deterministic tie-breaker

At Defense 20, exact ties without technical separation remain unresolved.

## Tie-Breaker Rules

Tie-breaker order:

1. fresher orderbook
2. better liquidity/spread
3. better exit readiness
4. better thesis state
5. stronger side-specific evidence
6. deterministic market/session hash at Defense 0 only

## Learning Ledger Fields

Created `same_market_side_arbitrations` with:

- `paper_session_id`
- `market_id`
- `defense_level`
- raw YES/NO scores
- YES/NO arbitration scores
- selected/rejected side
- margin/required margin
- tie-breaker
- outcome
- reason
- side evidence JSON

## Autopsy And Report Updates

- Added read-only API: `GET /dashboard/api/v2/control/arbitration-autopsy`.
- Added CLI: `.\tools\polybot.ps1 arbitration-autopsy [-limit 20]`.
- `report` now includes a same-market arbitration summary.
- Blocker autopsy maps `OPPOSING_SIDE_DEMOTED_BY_ARBITRATION`, `SAME_MARKET_OPPOSING_SIDE_UNRESOLVED`, and `INTEGRITY_BLOCKER_PREVENTED_ARBITRATION`.

## Tests Run

- `pytest tests/test_same_market_side_arbitration.py tests/test_defense_aware_arbitration.py tests/test_arbitration_learning_ledger.py tests/test_arbitration_autopsy.py tests/test_paper_defense_level.py tests/test_paper_intent_gate_idempotency.py -q` -> `7 passed, 5 skipped`.
- `pytest tests/test_paper_defense_blocker_policy.py tests/test_paper_defense_learning_ledger.py tests/test_enter_lifecycle_autopsy.py tests/test_blocker_autopsy.py tests/test_hunting_autopsy.py tests/test_paper_execution_adapter_runtime.py -q` -> `5 passed, 8 skipped`.
- `pytest tests/test_same_market_side_arbitration.py tests/test_defense_aware_arbitration.py tests/test_arbitration_learning_ledger.py tests/test_arbitration_autopsy.py tests/test_paper_defense_level.py tests/test_paper_intent_gate_idempotency.py tests/test_same_market_enter_arbitration.py tests/test_opposing_side_enter_resolution.py -q` -> `10 passed, 5 skipped`.
- `python -m compileall app tests` -> passed.

Skips were DB-fixture skips where `POLYBOT_DATABASE_URL` was unavailable to the local pytest process.

## Runtime Verification

Deployment:

- `docker compose build api` -> passed.
- `docker compose build migrate` -> passed.
- `docker compose run --rm migrate` -> applied `0148_same_market_side_arbitration.sql`.
- `docker compose up -d --no-deps api` -> passed.

20-minute Defense 20 run:

- Command: `.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20`.
- Session: `paper_session_20260619T231614Z_76892347`.
- Defense level: `20`.
- Arbitration conflicts recorded: `64`.
- Resolved conflicts: `9`.
- Unresolved conflicts: `55`.
- Current session paper intents/orders/fills/positions: `4/1/1/1`.
- Open positions after run: `0`.
- Realized PnL: `-3.40909`.
- Live/shadow/real: `0/0/0`.
- No duplicate eligibility crash.
- No simultaneous normal YES+NO position observed.

Example resolved conflict:

- Market `2354064`
- Defense `20`
- YES arbitration score `82.46`
- NO arbitration score `84.46`
- Required margin `2`
- Observed margin `2`
- Selected side `NO`
- Outcome `ARBITRATION_SELECTED_NO`

Example unresolved conflict:

- Market `691547`
- Defense `20`
- YES arbitration score `93.99`
- NO arbitration score `93.99`
- Required margin `2`
- Observed margin `0`
- Outcome `SAME_MARKET_OPPOSING_SIDE_UNRESOLVED`

## Safety Checklist

- PAPER only: YES
- Live orders untouched: YES
- Shadow orders untouched: YES
- Real orders untouched: YES
- No fake trades: YES
- No thresholds lowered outside Paper Defense: YES
- Integrity blockers remain hard: YES
- Both YES/NO not opened as normal trades: YES
- Current session counts remain scoped: YES
- Historical Paper data preserved: YES
- No destructive DB action: YES
- No secrets printed: YES

## Remaining Risks

- Many markets still have exactly tied side evidence at Defense 20. Those remain unresolved by design.
- `SOURCE_REFRESH_TRADING_MUTATION_DETECTED` appeared as a diagnostic latest error during verification; supervisor autopsy reported it did not block Paper entries.
- More side-specific evidence would improve arbitration quality for equal-score candidates.

## Status

YELLOW.

The arbitration repair is working and runtime verified, but 55 of 64 observed conflicts remained unresolved because the available side evidence was exactly tied. This is correct conservative behavior for Defense 20, not a runtime crash.

Safe to continue Defense 20 Paper sessions: YES.
