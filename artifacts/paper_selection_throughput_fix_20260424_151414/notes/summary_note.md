# Paper Selection Throughput Fix

Before fix clean rerun:
- paper_signals=60
- would_enter=3
- would_block=3
- would_skip=54
- paper_orders=3
- paper_positions=3
- dominant skip reason=lower_ranked_after_would_enter

After fix clean rerun:
- paper_signals=40
- would_enter=3
- would_block=37
- would_skip=0
- paper_orders=3
- paper_positions=3
- dominant block reasons=paper_safe capacity reached after filling 3 slots

Interpretation:
paper-safe now uses available free slots in the same cycle instead of wasting them behind lower_ranked_after_would_enter. The next visible bottleneck is bounded paper-safe capacity, not selection ordering.
