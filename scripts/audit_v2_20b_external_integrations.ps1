param()

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    $env:POLYBOT_DATABASE_URL = if ($env:POLYBOT_DATABASE_URL) { $env:POLYBOT_DATABASE_URL } else { "postgresql://polybot:polybot@127.0.0.1:55432/polybot" }
    @'
import json
import os
import shutil

from app.db.config import get_database_settings
from app.db.connection import DatabaseConnectionFactory

tables = {
    "news_sources": "updated_at",
    "news_raw_events": "collected_at",
    "social_sources": "updated_at",
    "social_raw_events": "collected_at",
    "whale_sources": "updated_at",
    "whale_events": "event_time",
    "markets_v2": "updated_at",
    "market_snapshots_v2": "snapshot_at",
    "orderbook_snapshots": "snapshot_at",
    "liquidity_snapshots": "snapshot_at",
    "fee_snapshots": "snapshot_at",
}

def table_summary(conn, table, ts_col):
    exists = conn.execute("SELECT to_regclass(%s) AS r", (table,)).fetchone()["r"] is not None
    if not exists:
        return {"exists": False, "count": 0, "latest_at": None}
    cols = [r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
        (table,),
    ).fetchall()]
    if ts_col in cols:
        row = conn.execute(f"SELECT COUNT(*) AS c, MAX({ts_col}) AS latest FROM {table}").fetchone()
        return {"exists": True, "count": int(row["c"] or 0), "latest_at": str(row["latest"]) if row["latest"] else None}
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    return {"exists": True, "count": int(row["c"] or 0), "latest_at": None}

payload = {
    "ollama_binary": shutil.which("ollama"),
    "env_presence": {
        name: bool(os.getenv(name))
        for name in [
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "NEWS_API_KEY",
            "TWITTER_API_KEY",
            "REDDIT_CLIENT_ID",
            "TELEGRAM_BOT_TOKEN",
            "DISCORD_BOT_TOKEN",
            "POLYBOT_DATABASE_URL",
            "POLY_API_KEY",
            "POLY_API_SECRET",
            "POLY_API_PASSPHRASE",
        ]
    },
    "tables": {},
}

try:
    factory = DatabaseConnectionFactory(get_database_settings())
    with factory.connect() as conn:
        payload["tables"] = {table: table_summary(conn, table, ts) for table, ts in tables.items()}
except Exception as exc:
    payload["db_error"] = str(exc)

print(json.dumps(payload, indent=2, default=str))
'@ | python -m uv run python -
} finally {
    Pop-Location
}
