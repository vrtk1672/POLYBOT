from pathlib import Path
import os, json
from datetime import datetime

ROOT = Path.cwd()
OUT = Path(os.environ["POLY_SMOKE_OUT"])

def load_env():
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k,v=line.split("=",1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()

import psycopg
dsn = os.getenv("DATABASE_URL") or "postgresql://polybot:polybot@127.0.0.1:55432/polybot"

tables = [
    "market_snapshots",
    "paper_runs",
    "paper_signals",
    "paper_orders",
    "paper_positions",
    "paper_position_events",
    "intelligence_ingestion_runs",
    "external_raw_events",
    "external_events_normalized",
    "event_interpretation_runs",
    "event_interpretations",
    "market_link_runs",
    "market_link_candidates",
    "whale_scan_runs",
    "whale_events",
    "whale_scoring_runs",
    "whale_market_scores",
    "alert_events",
]

result = {"captured_at": datetime.now().isoformat(), "counts": {}}

with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
    with conn.cursor() as cur:
        for t in tables:
            try:
                cur.execute(f'select count(*) from public."{t}"')
                result["counts"][t] = cur.fetchone()[0]
            except Exception as e:
                result["counts"][t] = f"ERROR: {type(e).__name__}: {e}"

print(json.dumps(result, indent=2, ensure_ascii=False))
(OUT / "before_counts.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
