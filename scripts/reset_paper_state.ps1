$ErrorActionPreference = "Stop"

$databaseUrl = $env:POLYBOT_DATABASE_URL
if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
    $databaseUrl = "postgresql://polybot:polybot@127.0.0.1:55432/polybot"
}

$env:POLYBOT_DATABASE_URL = $databaseUrl

@'
import os
import psycopg

conninfo = os.environ["POLYBOT_DATABASE_URL"]

paper_tables = (
    "paper_order_events",
    "paper_position_events",
    "paper_orders",
    "paper_positions",
    "paper_signals",
    "paper_runs",
)

with psycopg.connect(conninfo) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            select 'paper_runs' as table_name, count(*) as count from paper_runs
            union all select 'paper_signals', count(*) from paper_signals
            union all select 'paper_orders', count(*) from paper_orders
            union all select 'paper_order_events', count(*) from paper_order_events
            union all select 'paper_positions', count(*) from paper_positions
            union all select 'paper_position_events', count(*) from paper_position_events
            order by table_name
            """
        )
        before = cur.fetchall()

        cur.execute(
            "truncate table "
            + ", ".join(paper_tables)
            + " restart identity"
        )

        cur.execute(
            """
            select 'paper_runs' as table_name, count(*) as count from paper_runs
            union all select 'paper_signals', count(*) from paper_signals
            union all select 'paper_orders', count(*) from paper_orders
            union all select 'paper_order_events', count(*) from paper_order_events
            union all select 'paper_positions', count(*) from paper_positions
            union all select 'paper_position_events', count(*) from paper_position_events
            order by table_name
            """
        )
        after = cur.fetchall()

print("paper reset complete")
print("before:")
for table_name, count in before:
    print(f"  {table_name}: {count}")
print("after:")
for table_name, count in after:
    print(f"  {table_name}: {count}")
'@ | python -m uv run python -
