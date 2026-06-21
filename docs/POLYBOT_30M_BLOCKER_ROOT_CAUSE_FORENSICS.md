# POLYBOT 30m Run Blocker Root-Cause Forensics

Date: 2026-06-04

Security governance status: `YELLOW_ACCEPTED_BY_OPERATOR`

Audit mode: read-only. No code, migration, runtime, Paper, live, shadow, balance, order, fill, position, or capital mutation was performed.

## Short Summary

The 30m run produced no Paper trades because every lifecycle governance decision created during the run was `HARD_BLOCK`.

The blocker counts reported by dashboards are cumulative raw governance rows, not unique current failures. During the actual 30m run window there were 998 governance decisions, all `HARD_BLOCK`, covering 170 unique subjects and 10 markets.

Root cause is mixed:

- Risk is correctly blocking many invalid candidate records because market identity/linkage/orderbook evidence is missing or thesis is blocked.
- Same-market blocking is over-blocking: no same-market guard decisions were created during the 30m run, and lifecycle governance reused stale same-market guard decisions from roughly 11 hours earlier.
- Freshness blocking is partly correct and partly calibration/order-sensitive: old sources correctly expire, but some orderbook snapshots became stale at 185-208 seconds against a 180-second TTL.
- Capital was not a current-run blocker. The `CAPITAL_BLOCKED` count is historical.

Status: `YELLOW`. Blockers are understood, but implementation calibration is needed before another runtime validation is useful.

## Run Trace

- run id: `active_30m_observation_20260604T115905Z`
- report: `docs/POLYBOT_CONTROLLED_30M_PAPER_RUN_POST_FRESHNESS_CALIBRATION_REPORT_20260604T115905Z.md`
- log: `logs/observation/controlled_30m_paper_run_post_freshness_calibration_20260604T115905Z.log`
- duration: 1806.4 seconds
- cycles: 10
- source-to-neuron cycles: 10, all `OK`
- freshness governance cycles: 10, all `OK`
- lifecycle governance cycles: 10, all `OK`
- paper intent cycles: 10, all `OK`
- paper execution cycles: 10, all `NO_VALID_PAPER_INTENTS`
- SYSTEM final state: `OFF`
- hard stop: `NO`
- Paper artifacts created: `0`

Per-cycle lifecycle governance created about 100 `HARD_BLOCK` rows:

- 12:00Z: 98
- 12:03Z through 12:27Z: 100 each cycle

No `WATCH_FOR_CONFIRMATION`, `ACTIONABLE_SMALL_PAPER`, or `ACTIONABLE_STANDARD_PAPER` rows were created during the run window.

## Raw vs Unique Blocker Counts

Run-window blockers, not cumulative dashboard totals:

| Blocker | Raw rows | Unique subjects | Unique markets | Avg repeats/subject |
| --- | ---: | ---: | ---: | ---: |
| `STALE_PAYOUT_ODDS` | 724 | 94 | 10 | 7.70 |
| `STALE_CAPITAL_EFFICIENCY` | 584 | 80 | 10 | 7.30 |
| `RISK_BLOCKED` | 540 | 140 | 2 | 3.86 |
| `STALE_CAPITAL_EVALUATION` | 518 | 84 | 2 | 6.17 |
| `RISK_BLOCKED_LINEAGE` | 500 | 138 | 1 | 3.62 |
| `RISK_BLOCKED_NO_EDGE` | 500 | 138 | 1 | 3.62 |
| `STALE_EXIT_PLAN` | 498 | 32 | 10 | 15.56 |
| `STALE_RISK_DECISION` | 498 | 32 | 10 | 15.56 |
| `SAME_MARKET_OPPOSING_SIDE_BLOCK` | 458 | 30 | 8 | 15.27 |
| `STALE_SAME_MARKET_GUARD` | 458 | 30 | 8 | 15.27 |
| `STALE_ORDERBOOK` | 338 | 34 | 10 | 9.94 |
| `STALE_EXIT_HOLD` | 264 | 60 | 1 | 4.40 |
| `STALE_PAPER_INTENT` | 140 | 14 | 7 | 10.00 |
| `RISK_BLOCKED_SPREAD` | 40 | 2 | 1 | 20.00 |
| `STALE_LIFECYCLE_PLAN` | 18 | 18 | 9 | 1.00 |

The dashboard's top counts are raw cumulative event counts. They should be supplemented with unique subject and unique market counts.

## Blocker Breakdown

| Blocker | Run-window result | Forensic classification |
| --- | --- | --- |
| `RISK_BLOCKED` | 540 raw / 140 unique subjects | Mostly justified lineage/data-quality block, with source-timestamp coupling issues |
| `SAME_MARKET_OPPOSING_SIDE_BLOCK` | 458 raw / 30 unique subjects | Stale same-market guard artifact / over-blocking |
| `CAPITAL_BLOCKED` | 0 current-run rows; 4 historical rows | Not a current blocker |
| `STALE_PAYOUT_ODDS` | 724 raw / 94 unique subjects | Mixed: old sources plus repeated old subject evaluation |
| `STALE_CAPITAL_EFFICIENCY` | 584 raw / 80 unique subjects | Mixed: old sources plus repeated old subject evaluation |
| `STALE_CAPITAL_EVALUATION` | 518 raw / 84 unique subjects | Mostly old-source artifact; fresh capital evals existed in run |
| `STALE_EXIT_PLAN` | 498 raw / 32 unique subjects | Old plan/source artifact for repeated fresh seeds/intents |
| `STALE_RISK_DECISION` | 498 raw / 32 unique subjects | Old risk source artifact for repeated fresh seeds/intents |
| `MISSING_EXECUTABLE_PRICE` | 0 in run-window risk/exit/no-trade tables | Not observed |
| `EXIT_NOT_READY` | 0 in run-window risk/exit/no-trade tables | Not observed |
| `WATCH_FOR_CONFIRMATION` | 0 created in run; 300 cumulative old rows | Not a run-window output |
| `REFRESH_REQUIRED` | Present as Paper dashboard blockers: `REFRESH_REQUIRED_BEFORE_EXECUTION=420` | Valid old-intent execution block |
| `NO_VALID_PAPER_INTENTS` | 10 Paper execution cycles | Expected because governance allowed no executable intents |

## Risk Blocked Forensics

Risk decisions created during the run:

- total: 100
- decision/status: all `BLOCK` / `BLOCKED`
- markets: `691547` plus null-market candidates

Risk reason groups:

- 60 records: `MISSING_FRESH_ORDERBOOK`, `MISSING_MARKET_ID`, `MISSING_MARKET_LINK`, `MISSING_SIGNAL_MARKET_BINDING`, `THESIS_BLOCKED`
- 40 records: `MISSING_MARKET_LINK`, `THESIS_BLOCKED`

Governance risk blocker subtypes:

- `RISK_BLOCKED_LINEAGE`: 500 raw / 138 unique
- `RISK_BLOCKED_NO_EDGE`: 500 raw / 138 unique
- `RISK_BLOCKED_SPREAD`: 40 raw / 2 unique

Risk sample classes:

- Null-market paper candidates are justified critical blocks: no market ID, no market link, no signal-market binding, no fresh orderbook.
- Market `691547` candidates are mostly justified blocks because risk says `MISSING_MARKET_LINK` and `THESIS_BLOCKED`.
- Market `2354064` fresh seed YES/NO has `SPREAD_TOO_WIDE`, spread `0.03`, and spread risk score `1.0`; this is justified.

Important timestamp issue:

Some joined risk decisions showed negative age relative to governance when joined by `risk_decision_id`, meaning the current row with that ID was updated after the lifecycle governance row. This suggests mutable/reused source IDs or source timestamp coupling. The risk block may be valid, but lifecycle governance should store the exact source timestamp/version it evaluated.

Answer: Risk is mostly blocking for valid critical reasons, but source-version/timestamp precision needs improvement.

## Same-Market Forensics

Same-market guard rows created during the 30m run:

- `0`

Same-market guard table range:

- earliest: `2026-06-03T22:58:43Z`
- latest: `2026-06-04T01:08:58Z`

Lifecycle governance rows during the 30m run reused old same-market guard decisions. The reused decisions were about 40,690-42,404 seconds old.

Examples:

- Market `2365092`: batch YES/NO conflict from old same-market guard row, no open positions, no active capital locks, no recent closes.
- Markets `2365093`, `597967`, `610236`, `666655`, `677404`: stale guard rows referenced old `CREATED` paper intents from `2026-06-03T12:34:05Z` as active exposure.
- Market `691547`: stale guard rows reported only batch opposite candidates; no open positions, no active intents, no active locks.

Current old intents:

- 14 `CREATED` intents remain.
- They are 84,268 to 401,537 seconds old at run end.
- Freshness correctly blocks them with `STALE_PAPER_INTENT` / `REFRESH_REQUIRED_BEFORE_EXECUTION`.

Answer: Same-Market Guard is not blocking because of current real active exposure. It is over-blocking because lifecycle plans consume stale same-market guard decisions and still propagate `SAME_MARKET_OPPOSING_SIDE_BLOCK`.

## Capital Blocked Forensics

Run-window lifecycle governance rows with `CAPITAL_BLOCKED`:

- `0`

Cumulative/historical `CAPITAL_BLOCKED` rows:

- 4 rows, all from `2026-06-03T22:23:22Z`
- market: `691547`
- subjects: two paper candidates and two paper intents

Capital Brain during the 30m run:

- `CAPITAL_SUPPORT`: 21
- `CAPITAL_BLOCK`: 2
- Capital blocks were due `Estimated required capital exceeds available balance`, with `REQUIRED_GT_AVAILABLE`.

The capital blocks did not appear as current lifecycle governance blockers.

Answer: Capital is not preventing current Paper action. The dashboard `CAPITAL_BLOCKED=4` is historical cumulative state.

## Stale Source Forensics

Freshness checks created during the run:

- `freshness_governance_checks`: 816 before, 3674 after, delta `2858`

Run-window stale source groups:

| Source | Status | TTL | Raw | Unique subjects | Avg age seconds | Max age seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `ORDERBOOK_SNAPSHOT` | FRESH | 180 | 600 | 96 | 15.9 | 26 |
| `ORDERBOOK_SNAPSHOT` | STALE | 180 | 180 | 20 | 194.3 | 208 |
| `ORDERBOOK_SNAPSHOT` | EXPIRED | 180 | 34 | 34 | 50802.3 | 84157 |
| `RISK_DECISION` | FRESH | 600 | 158 | 138 | 6.3 | 9 |
| `RISK_DECISION` | EXPIRED | 600 | 32 | 32 | 42165.7 | 42317 |
| `EXIT_PLAN` | FRESH | 600 | 158 | 138 | 6.1 | 9 |
| `EXIT_PLAN` | EXPIRED | 600 | 32 | 32 | 42165.6 | 42317 |
| `PAYOUT_ODDS` | FRESH | 600 | 113 | 109 | 211.7 | 555 |
| `PAYOUT_ODDS` | STALE | 600 | 32 | 32 | 1227.8 | 1621 |
| `PAYOUT_ODDS` | EXPIRED | 600 | 70 | 70 | 44217.2 | 71118 |
| `CAPITAL_EFFICIENCY` | FRESH | 600 | 253 | 123 | 96.0 | 554 |
| `CAPITAL_EFFICIENCY` | STALE | 600 | 32 | 32 | 1226.1 | 1619 |
| `CAPITAL_EFFICIENCY` | EXPIRED | 600 | 56 | 56 | 36515.4 | 64290 |
| `SAME_MARKET_GUARD` | EXPIRED | 600 | 30 | 30 | 42245.4 | 42404 |
| `PAPER_INTENT` | EXPIRED | 600 | 14 | 14 | 81597.6 | 84144 |

Interpretation:

- Old intents and same-market guard rows are correctly detected as expired.
- Some stale payout/capital/exit-hold rows are old subjects repeatedly evaluated.
- Orderbook staleness at 185-208 seconds is a TTL/cycle-order edge. TTL is 180 seconds, but the run cadence and selected source snapshot can exceed that before governance checks it.

Answer: stale blocking is caused by correct old-data detection plus a smaller freshness TTL/cycle-order bug for orderbook snapshots.

## Closest-To-Actionable Review

The top closest subject was:

- plan: `trade_lifecycle_02b0df64a6d45db7b195b5dfb387f3ef`
- subject: `FRESH_SEED:fresh_seed_597964_NO`
- market: `597964`
- side: `NO`
- actionability: `HARD_BLOCK`
- plan status: `PARTIAL`
- strategy: `REPRICING_CANDIDATE`
- critical blockers: `STALE_EXIT_PLAN`, `STALE_ORDERBOOK`, `STALE_RISK_DECISION`
- optional missing: `FAIR_PROBABILITY_MISSING`, `MEMORY_CONTEXT_MISSING`, `WHALE_CONTEXT_MISSING`
- context-dependent missing: `EXIT_HOLD_MISSING`, `SAME_MARKET_GUARD_MISSING`, `TIME_TO_RESOLUTION_MISSING`
- capital status: `CAPITAL_WATCH`
- one thing preventing actionability: refresh stale risk/exit/orderbook sources, then produce fresh same-market and exit-hold context
- would become actionable if only refreshed: unknown; it still needs same-market guard and exit-hold evaluation
- recommended action: refresh then re-evaluate

The next closest subjects were mostly paper candidates with null market IDs and risk blockers:

- blockers: `RISK_BLOCKED`, `RISK_BLOCKED_LINEAGE`, `RISK_BLOCKED_NO_EDGE`
- risk blockers: `MISSING_FRESH_ORDERBOOK`, `MISSING_MARKET_ID`, `MISSING_MARKET_LINK`, `MISSING_SIGNAL_MARKET_BINDING`, `THESIS_BLOCKED`
- recommendation: keep blocked; fix upstream lineage/linking before considering Paper

No subject was truly one safe step from `ACTIONABLE_SMALL_PAPER`.

## Duplicate / Repeat Analysis

The high blocker counts are inflated by repeated evaluations.

Examples:

- `RISK_BLOCKED`: 540 raw, 140 unique subjects, avg 3.86 repeats.
- `SAME_MARKET_OPPOSING_SIDE_BLOCK`: 458 raw, 30 unique subjects, avg 15.27 repeats.
- `STALE_RISK_DECISION`: 498 raw, 32 unique subjects, avg 15.56 repeats.
- `STALE_PAPER_INTENT`: 140 raw, 14 unique intents, exactly 10 repeats each.

The dashboard should show:

- raw blocker events,
- unique blocked subjects,
- unique markets,
- repeats per subject,
- latest-cycle-only counts.

Without this split, cumulative raw counts overstate the number of distinct blocked opportunities.

## What Is Justified

1. Null-market paper candidates should not trade.
2. Missing market link and missing signal-market binding are hard blockers.
3. `THESIS_BLOCKED` from Risk should remain hard.
4. `SPREAD_TOO_WIDE` on market `2354064` is a valid risk block.
5. Old paper intents should require refresh before execution.
6. Old same-market guard decisions should not authorize Paper.
7. Capital reconciliation is OK and capital is not currently blocking action.
8. Paper execution correctly returned `NO_VALID_PAPER_INTENTS`.
9. No stale data authorized a Paper artifact.
10. No Paper path bypass was found.

## What Is Over-Blocking

1. Lifecycle governance propagates stale `SAME_MARKET_OPPOSING_SIDE_BLOCK` from old guard decisions.
2. Same-market guard did not refresh during the 30m run.
3. Old `CREATED` paper intents appear in stale same-market exposure snapshots as active intent conflicts.
4. Batch YES/NO conflict decisions from old guard rows still affect current plans.
5. Cumulative dashboard counts make historical `CAPITAL_BLOCKED` look current.

## What Is Stale Artifact

1. `STALE_SAME_MARKET_GUARD`: all same-market guard rows are pre-run.
2. `STALE_PAPER_INTENT`: 14 old intents.
3. `STALE_RISK_DECISION` and `STALE_EXIT_PLAN`: 32 unique subjects using old source rows.
4. `STALE_PAYOUT_ODDS` / `STALE_CAPITAL_EFFICIENCY`: old subjects and repeated old evaluations.
5. `STALE_ORDERBOOK`: partly old snapshots, partly 185-208 second TTL edge.

## What Is Unknown

1. Whether fresh same-market guard would clear most current same-market blockers.
2. Whether market `597964_NO` would become actionable after fresh risk/exit/orderbook/same-market rebuild.
3. Whether the repeated `691547` candidate feed is intentionally still active or should be retired as historical.
4. Whether lifecycle source refs should be immutable source versions rather than latest mutable IDs.

## Top 20 Findings

1. The 30m run created 998 lifecycle governance decisions, all `HARD_BLOCK`.
2. No actionable governance decisions were created in the run window.
3. Dashboard blocker totals are cumulative raw rows, not unique failures.
4. `RISK_BLOCKED` was 540 raw but 140 unique subjects.
5. `SAME_MARKET_OPPOSING_SIDE_BLOCK` was 458 raw but only 30 unique subjects.
6. Same-market guard created zero rows during the 30m run.
7. Same-market blockers came from stale guard rows created around 00:40-01:08Z.
8. Stale same-market rows referenced old intents from 2026-06-03 as active exposure.
9. There were no open positions at run time.
10. There were no active capital locks at run time.
11. Capital was not a current lifecycle blocker.
12. Four `CAPITAL_BLOCKED` rows are historical, not run-window blockers.
13. Risk generated 100 new blocks during the run.
14. Risk block reasons were missing market/link/orderbook binding or thesis blocked.
15. Some risk decision joins show source timestamp/version ambiguity.
16. `STALE_ORDERBOOK` includes a TTL edge at 185-208 seconds with TTL 180.
17. Old intents were correctly blocked from execution with refresh-required semantics.
18. Paper execution ran every cycle and found no valid intents.
19. Optional missing context did not cause Paper authorization or appear as sole hard block.
20. The closest plan is still not actionable; it requires refresh and missing context generation.

## Top 20 Recommended Fixes

1. Force same-market guard refresh inside the active cycle before trade lifecycle build.
2. Do not let stale same-market guard `BLOCK` propagate as current `SAME_MARKET_OPPOSING_SIDE_BLOCK`; represent it only as `STALE_SAME_MARKET_GUARD`.
3. Add active-intent TTL filtering to lifecycle consumption of same-market summaries, not only guard generation.
4. Mark old unexecuted paper intents as `REFRESH_REQUIRED` or `EXPIRED_FOR_EXECUTION` in read model, without deleting them.
5. Add latest-cycle and unique-subject blocker counts to lifecycle governance dashboard.
6. Add unique-market blocker counts to dashboard.
7. Add raw-vs-unique counts to freshness governance dashboard.
8. Add same-market exposure type breakdown: open position, active intent, batch conflict, recent close, old history, stale artifact.
9. Rebuild same-market guard decisions for current fresh seeds every cycle.
10. Increase orderbook TTL from 180s or align cycle cadence/check ordering so valid snapshots are not stale at 185-208s.
11. Prefer the freshest verified orderbook source when lifecycle plans select source refs.
12. Store immutable source timestamp/version in lifecycle plan source refs.
13. Prevent lifecycle plans from joining mutable risk decision IDs without source timestamp/version.
14. Retire or quarantine old repeated candidate subjects that have null market IDs.
15. Add a no-trade archival policy for old Paper candidates/intents that cannot become executable.
16. Split Risk `THESIS_BLOCKED` from `NO_EDGE` and lineage blockers in dashboard summaries.
17. Add a closest-to-actionable endpoint with critical blockers, stale blockers, and one required next action.
18. Add a run-window filter to dashboard blocker panels.
19. Add execution-level old-intent refresh summary by market/side.
20. Re-run 10m only after same-market refresh ordering and orderbook TTL/cycle ordering are fixed.

## Recommended Next Implementation Phase

Recommended phase:

`Same-Market Fresh Refresh + Source Freshness Ordering Fix`

Scope:

- refresh same-market guard before lifecycle/governance every cycle,
- prevent stale same-market guard blockers from acting like current exposure,
- align orderbook freshness TTL with actual cycle timing,
- add raw/unique/latest-cycle blocker dashboard counts,
- preserve old intents as historical but make refresh-required status explicit.

## Readiness

4h run useful now: `NO`

Reason: it would likely repeat the same stale same-market and orderbook TTL behavior and accumulate more raw blocker rows without changing actionability.

10m rerun useful now: `NO`

Reason: a shorter rerun would validate safety again, but it would not answer the blocker problem until same-market refresh ordering and orderbook TTL/source selection are fixed.

## Phase Status

Status: `YELLOW`

Blockers are now understood, and no bypass/safety issue was found. Calibration/fix work is required before another validation run should be expected to produce actionable Paper decisions.

