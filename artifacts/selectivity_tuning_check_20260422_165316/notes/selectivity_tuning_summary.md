# Selectivity Tuning Verification

Canonical runtime selectivity tuning completed on 2026-04-22.

Root cause classification:
- legitimate discipline: same-market exposure blocking once a paper position already exists in that market; lower-ranked candidates skipped after one higher-ranked candidate would enter
- accidental over-blocking: paper-mode execution adapter leaked open paper positions into the Stage 4 open-order feed, so the global LIVE_MAX_OPEN_POSITIONS gate treated one existing position as a permanent open-order cap hit
- stale-state artifact: the rolling KPI window still includes one earlier runtime cycle dominated by the old open-order-cap reason, even though the latest sampled cycles are showing same-market blocks and successful new entries instead
- threshold miscalibration: not changed in this step
- paper/live mode mismatch: corrected by aligning paper open-order inspection with the same open-order semantics used by the live execution policy

Before KPI snapshot:
- ranking_policy_selectable=0
- ranking_policy_rejected=100
- paper_would_enter=0
- paper_would_block=100
- paper_orders_created=0
- paper_orders_filled=0
- paper_positions_opened=0
- top_paper_block_reason=open_orders_1_meet_exceed_live_max_open_positions_1

After KPI snapshot:
- ranking_policy_selectable=0
- ranking_policy_rejected=100
- paper_would_enter=3
- paper_would_block=46
- paper_orders_created=3
- paper_orders_filled=3
- paper_positions_opened=3
- top_paper_block_reasons now reflect a mixed, more disciplined picture: open_orders_1... remained in one older cycle still inside the 5-cycle window, while the latest cycles show same_market_exposure blocks plus lower_ranked_after_would_enter skips after successful entries

Observed paper impact:
- new filled paper orders for markets 1929170, 1731344, and 1980863
- open paper positions now visible for 1517835, 1929170, 1731344, and 1980863
- runtime stayed responsive and KPI endpoint remained healthy throughout validation
