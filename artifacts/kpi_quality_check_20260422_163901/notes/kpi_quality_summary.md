# KPI Quality Verification

Canonical runtime KPI validation completed on 2026-04-22.

What was added:
- persisted-data-backed KPI and quality endpoint at /dashboard/api/kpi-quality
- dashboard overview now includes kpi_quality
- dashboard UI now renders a KPI / Quality section

Observed live runtime results:
- sample 1 and sample 2 both returned 200 for health, overview, kpi-quality, ranking, positions-orders, invalidation, and Telegram /status
- recent 5-cycle KPI window showed 12,500 opportunities seen, 50 runtime-ranked candidates, 100 ranking-policy candidates, and 100 paper signals
- recent 5-cycle paper activity showed 0 new orders and 0 new fills because all 100 signals were WOULD_BLOCK under the open-position cap reason open_orders_1_meet_exceed_live_max_open_positions_1
- quality distributions showed ranking tier REJECT=100, gate HARD_REJECT=100, trade classification NO_TRADE=52, bucket NO_BUCKET=100, invalidation WATCH=52, exit policy BLOCK_NEW_DEPLOYMENT=52, advisory WATCH=5, command intent WATCH_ONLY=5
- persisted paper lifecycle still exists and remains visible: one OPEN paper position and one FILLED paper order

Truthfulness notes:
- fill_rate and position_open_rate are null when there were no new orders in the measured window
- no profitability or win-rate claims are included because the current sample does not support them truthfully
