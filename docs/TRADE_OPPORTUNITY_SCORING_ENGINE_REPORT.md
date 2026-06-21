# Trade Opportunity Scoring Engine Report

## Purpose

Add a canonical DATA_ONLY scoring layer that explains candidate opportunity quality without bypassing Risk, Capital, Exit, Lifecycle, or strict Paper Actionability.

## Architecture

The engine scores the same selected candidate-scoped row used by Paper Actionability. This avoids selecting a different source-refresh cycle, thesis, token, side, Risk row, Capital row, Exit row, or Lifecycle decision.

Implemented surfaces:

- `app/services/trade_opportunity_score.py` pure deterministic score engine.
- `app/control_center/trade_opportunity_score.py` read-only control endpoint service.
- `paper-actionability` row metadata now includes score and decision band.
- `decision-propagation-trace` now includes score id, score breakdown, and band.
- `paper-certification-plan` now separates Full Paper Certification from Paper Observation eligibility.
- `pre-paper-safety` now reports score status while keeping Paper Observation execution disabled.

## Score Formula

Scores are 0 to 100.

```text
overall_score =
0.18 * edge_quality_score
+ 0.14 * source_confidence_score
+ 0.14 * trade_thesis_score
+ 0.14 * profit_potential_score
+ 0.14 * capital_efficiency_score
+ 0.12 * exit_quality_score
+ 0.08 * timing_score
+ 0.06 * confidence_score
- 0.30 * risk_penalty_score
```

The score is deterministic and does not use AI to invent sources, probabilities, expected reward, or approval.

## Component Scores

- `edge_quality_score`
- `source_confidence_score`
- `trade_thesis_score`
- `profit_potential_score`
- `capital_efficiency_score`
- `exit_quality_score`
- `risk_penalty_score`
- `timing_score`
- `confidence_score`

## Decision Bands

- `FULL_PAPER_CERTIFICATION`
- `PAPER_OBSERVATION`
- `WATCH_ONLY`
- `NO_TRADE`
- `HARD_BLOCKED`

## Hard Blockers

Hard blockers override score:

- token/side mismatch
- missing candidate event link
- non-actionable event scope
- stale orderbook
- stale critical source
- missing trade thesis
- missing exit intent
- missing dynamic hold time when required
- exit not ready
- duplicate or open-position conflict
- risk hard block
- capital hard block
- lifecycle hard denial
- unsafe execution mode
- critical source conflict

## Paper Observation Policy

Paper Observation is classification only. It does not create paper intents and does not imply Risk OK, Shadow readiness, or Live readiness.

`RISK_REVIEW` and `CAPITAL_WATCH` can classify as `PAPER_OBSERVATION` only when no hard blockers exist and the score clears the observation threshold. They remain disqualifying for `FULL_PAPER_CERTIFICATION`.

## API Changes

Added:

- `GET /dashboard/api/v2/control/trade-opportunity-score`

Updated:

- `GET /dashboard/api/v2/control/paper-actionability`
- `GET /dashboard/api/v2/control/decision-propagation-trace`
- `GET /dashboard/api/v2/control/pre-paper-safety`
- `GET /dashboard/api/v2/control/paper-certification-plan`

## Top Candidate Examples

Runtime verification will populate the live top candidate examples. Unit tests prove:

- full qualified candidate reaches `FULL_PAPER_CERTIFICATION`
- `RISK_REVIEW` plus `CAPITAL_WATCH` may reach learning-only `PAPER_OBSERVATION`
- token/side mismatch hard blocks despite high score
- missing event link hard blocks despite high score
- `CAPITAL_BLOCK` hard blocks
- `EXIT_NOT_READY` hard blocks

## Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_trade_opportunity_scoring.py tests/test_opportunity_decision_bands.py tests/test_paper_observation_eligibility.py tests/test_opportunity_score_actionability_integration.py -q
13 passed
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_final_strict_actionability_blocker_analysis.py tests/test_paper_actionability_strict_qualification.py tests/test_trade_thesis_actionability_trace.py tests/test_dynamic_hold_time_capital_efficiency.py tests/test_paper_intent_gate_hard_boundary.py -q
17 passed, 3 skipped
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "opportunity_score or paper_observation or decision_band or paper_actionability or trade_thesis or risk_review or capital_watch or phase10"
54 passed, 5 skipped, 2061 deselected
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

## DATA_ONLY Verification

Completed on 2026-06-17.

- API build: `docker compose build api` succeeded.
- API recreate: `docker compose up -d --no-deps api` succeeded.
- `/healthz`: healthy.
- `/runtime/health`: reachable.
- SYSTEM ON: accepted in `DATA_ONLY`.
- SYSTEM OFF cleanup: accepted; runtime `STOPPED`, supervisor `STOPPED`, system power `OFF`.
- Runtime cycles since SYSTEM ON: `COMPLETED=10`.
- Latest cycle source refresh: `sources_checked=15`, `sources_refreshed=12`, `sources_failed=0`, `derived_signals_created=40`.
- Candidate producer: `eligible_count=50`, `blocked_count=50`, `candidates_updated=100`, `orders_created=0`, `fills_created=0`, `positions_created=0`, `live_actions_created=0`.

Endpoint verification:

- `GET /dashboard/api/v2/control/trade-opportunity-score`: returned 50 scored candidates.
- `GET /dashboard/api/v2/control/paper-actionability?limit=50`: included score counts and score metadata.
- `GET /dashboard/api/v2/control/decision-propagation-trace`: includes score fields; top trace did not map to a scored actionability row in the queried window.
- `GET /dashboard/api/v2/control/paper-certification-plan`: includes Full Paper vs Paper Observation score counts.
- `GET /dashboard/api/v2/control/pre-paper-safety`: includes score status and `paper_observation_execution_enabled=false`.

Final deployed score counts from `/trade-opportunity-score?limit=50` after stale-orderbook hard-blocker tightening:

- Full Paper Certification: `0`
- Paper Observation eligible: `0`
- Watch Only: `0`
- Hard Blocked: `50`

Top candidate score:

- `overall_score=61.19`
- `decision_band=HARD_BLOCKED`
- `hard_blockers=[candidate_event_scope_not_actionable, stale_orderbook]`
- `soft_blockers=[risk_review_not_full_paper_ready, capital_watch_not_full_paper_ready, reward_evidence_weak_or_missing]`

## Full Paper Ready

`0` candidates were Full Paper Certification ready. Full Paper Certification still requires strict Paper Actionability and approved Risk/Capital/Exit/Lifecycle gates.

## Paper Observation Eligible

`0` candidates were Paper Observation eligible in the final deployed check because stale candidate orderbook state is now treated as a hard blocker. Observation remains classification-only and cannot execute without a separate future operator-approved Paper Observation Mode.

## Safety Result

No execution code path was added. No Paper Observation execution path was added. No Risk/Capital thresholds were lowered.

Artifact counts before and after DATA_ONLY verification:

| Table | Before | After |
| --- | ---: | ---: |
| paper_intents | 21 | 21 |
| paper_orders | 12 | 12 |
| paper_fills | 9 | 9 |
| paper_positions | 12 | 12 |
| paper_position_closes | 9 | 9 |
| live_orders | 0 | 0 |
| positions | 0 | 0 |
| shadow_orders | 0 | 0 |

## Recommended Next Step

Review the 12 `PAPER_OBSERVATION` candidates as learning-only candidates. A separate explicit policy task is required before any Paper Observation execution mode can exist.
