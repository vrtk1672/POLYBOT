# Paper Flow Verification

Canonical runtime proof completed on 2026-04-22.

Observed behavior:
- canonical migration path succeeded with no pending migrations
- canonical runtime started and stayed responsive across three timed probe samples
- paper signal flow advanced into one persisted paper order and one persisted open paper position
- paper order lifecycle persisted CREATED -> FILLED order events
- paper position lifecycle persisted OPENED plus repeated MARKED events during later refresh cycles
- dashboard positions/orders and audit APIs returned paper activity on every timed sample
- Telegram positions command stayed responsive while paper activity was present

Before counts:
- paper_runs=12
- paper_signals=240
- paper_orders=0
- paper_order_events=0
- paper_positions=0
- paper_position_events=0

After counts:
- paper_runs=15
- paper_signals=300
- paper_orders=1
- paper_order_events=2
- paper_positions=1
- paper_position_events=5
