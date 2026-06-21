# Paper Eligibility Diversity Expansion Report

## Purpose

Broaden POLYBOT's PAPER eligibility and runtime decision visibility beyond the single dominant market/side (`691547 YES`) without faking thesis, faking eligibility, weakening duplicate protection, or creating a separate paper-specific decision brain.

## Current Bottleneck Summary

Before repair, the execution chain worked, but the eligibility funnel narrowed sharply:

- Paper Observation policy reviews: 73 rows, all `691547 YES OBSERVATION_POLICY_ELIGIBLE`.
- Current PAPER runtime decisions: 1 unique market/side.
- Current blocker: `DUPLICATE_OPEN_PAPER_EXPOSURE` on `691547 YES`.
- Non-691547 Mesh-reviewed rows existed but were invisible to policy/runtime because policy refresh only imported `PAPER_OBSERVATION` rows.

## Funnel Audit By Stage

Pre-repair DB audit:

| Stage | Rows | Unique Markets | Unique Market/Side Pairs |
| --- | ---: | ---: | ---: |
| Market universe | 1004 | 1004 | 1004 market-level |
| Source event links | 2905 | 158 | 181 |
| Triggers | 182 | 9 | 11 |
| Proactive seeds | 1781 | 13 | 31 |
| Targeted revalidations | 2211 | 44 | market-level |
| Mesh-reviewed seeds | 1769 | 13 | 31 |
| EDGE_SUPPORTED | 979 | 9 | 17 |
| THESIS_SUPPORTED | 703 | 1 | 2 |
| THESIS_WATCH | 250 | 8 | 15 |
| THESIS_MISSING | 816 | 13 | 27 |
| PAPER_OBSERVATION band | 703 | 1 | 2 |
| Policy reviews | 73 | 1 | 1 |
| Current runtime decisions | 1 | 1 | 1 |

## Why 691547 YES Dominated

`691547 YES` dominated because it was the only market/side with persisted `PAPER_OBSERVATION` rows that passed policy eligibility. The Stage 7 policy source query selected only `psr.opportunity_decision_band='PAPER_OBSERVATION'`, so non-691547 rows that were Mesh-reviewed but `HARD_BLOCKED`, `THESIS_WATCH`, or `THESIS_MISSING` were silently absent from policy review and PAPER runtime decisions.

## Why Non-691547 Candidates Failed

Top non-691547 Mesh-reviewed rows were mostly:

- `EDGE_SUPPORTED`
- `THESIS_WATCH`
- score `55.46`
- `opportunity_decision_band=HARD_BLOCKED`
- `risk_state=RISK_OK`
- `capital_state=CAPITAL_WATCH`
- `exit_state=EXIT_READY`
- `lifecycle_state=DATA_ONLY_RESEARCH`
- hard blocker `missing_dynamic_hold_time`

Top non-691547 blockers:

- `missing_dynamic_hold_time`: 266
- side/token/watch-only blockers on SIDE_UNKNOWN seeds
- `missing_trade_thesis`: 25
- `exit_not_ready`: 25
- low score versus observation threshold

## Thesis Coverage Findings

The repair does not synthesize thesis. `THESIS_WATCH` remains not eligible, but it is now persisted as `OBSERVATION_POLICY_WATCH` when safety-hard blockers are absent. `THESIS_MISSING` remains `OBSERVATION_POLICY_INCOMPLETE`.

## Actionability Gap Findings

Non-691547 rows mainly fail because they are below the observation threshold, have `THESIS_WATCH`, and carry `missing_dynamic_hold_time`. They are now visible as WATCH/BLOCK/INCOMPLETE decisions with exact required-to-pass context instead of disappearing before the runtime decision layer.

## Policy Review Source Coverage Findings

Policy review now reads:

- existing `PAPER_OBSERVATION` rows
- Mesh-reviewed rows with `EDGE_SUPPORTED`
- Mesh-reviewed rows with a non-null opportunity score

This broadens review coverage while preserving eligibility gates.

## Decision Selector Findings

PAPER runtime decisions now consume all policy states:

- `OBSERVATION_POLICY_ELIGIBLE` can become ENTER if no hard blockers remain.
- `OBSERVATION_POLICY_WATCH` becomes WATCH, not ENTER.
- `OBSERVATION_POLICY_BLOCKED` and `OBSERVATION_POLICY_INCOMPLETE` become BLOCK.

Decision grouping by market/side and duplicate exposure protection remain active.

## Fixes Made

- Broadened `PaperObservationPolicyReviewService` source query beyond only `PAPER_OBSERVATION`.
- Reclassified `THESIS_WATCH` non-dominant rows as WATCH when blockers are watch/actionability blockers rather than safety-hard blockers.
- Kept `THESIS_MISSING` rows incomplete.
- Updated `PaperRuntimeDecisionService` to emit WATCH/BLOCK rows for non-enterable policy states.
- Kept last-mile orderbook refresh limited to policy-eligible candidates near ENTER.
- Added system overview decision diversity diagnostics.

## Tests Run

- Focused: `5 passed, 5 skipped`
- Related: `11 passed, 4 skipped`
- Broad targeted: `25 passed, 16 skipped, 2292 deselected`
- Compile: passed

## Deployment

- `docker compose build api`
- `docker compose up -d --no-deps api`
- No DB migration required.

## Controlled PAPER Runtime Verification

Pre-run:

- policy reviews: 982 after refresh
- eligible/watch/incomplete: 703 / 250 / 29
- runtime current unique markets: 9
- runtime current unique market/side pairs: 17
- paper intents/orders/fills/positions: 25 / 16 / 13 / 16
- open paper positions: 1

Runtime result:

- events: 2630 -> 2784
- linked events: 1326 -> 1386
- triggers: 182 -> 189
- seeds: 1781 -> 1816
- Mesh reviewed: 982 -> 1002
- paper intents: 25 -> 26
- paper orders: 16 -> 17
- paper fills: 13 -> 14
- paper positions: 16 -> 17
- open paper positions: 1 -> 1
- live orders: 0 -> 0
- shadow orders: 0 -> 0
- real orders: 0 -> 0

Runtime decisions after verification:

- current runtime decisions: 16
- ENTER: 1
- WATCH: 14
- BLOCK: 1
- unique markets: 9
- unique market/side pairs: 16
- concentration score: 0.0625

## Paper Ledger Result

One natural paper entry occurred through the normal decision pipeline. The current open paper position is `691547 YES`, size `10`, average entry `0.390000`, mark `0.340000`.

## Live / Shadow Safety

LIVE and SHADOW remained blocked. No live, shadow, or real orders were created.

## Remaining Blockers

- Non-dominant candidates are visible now, but most are WATCH because score is below threshold and `missing_dynamic_hold_time` remains.
- Policy review remains the diversity bottleneck: 31 Mesh market/side pairs -> 17 policy market/side pairs.
- Further real eligibility requires thesis/dynamic hold-time support for non-news triggers, not lower safety thresholds.

## Status

GREEN for diversity visibility and policy/runtime input coverage.

PARTIAL for broader autonomous PAPER entries because non-dominant candidates are still mostly WATCH, not ENTER.

## Recommended Next Action

Build dynamic hold-time / exit-thesis support for non-news trigger families (`MARKET_MOVEMENT`, `PAYOUT_DISCREPANCY`, `SIGNAL_QUALITY`) so existing `EDGE_SUPPORTED / THESIS_WATCH` rows can become genuinely thesis-supported when evidence warrants it.
