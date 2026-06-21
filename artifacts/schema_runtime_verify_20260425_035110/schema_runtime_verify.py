from pathlib import Path
import os, json, traceback
from datetime import datetime, timezone, timedelta

ROOT = Path.cwd()
OUT = Path(os.environ["POLY_VERIFY_OUT"])
OUT.mkdir(parents=True, exist_ok=True)

def write(name, obj):
    p = OUT / name
    if isinstance(obj, str):
        p.write_text(obj, encoding="utf-8")
    else:
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

def load_env():
    env_path = ROOT / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k,v=line.split("=",1)
            k=k.strip()
            v=v.strip().strip('"').strip("'")
            env[k]=v
            os.environ.setdefault(k,v)
    return env

env = load_env()
dsn = os.getenv("DATABASE_URL") or "postgresql://polybot:polybot@127.0.0.1:55432/polybot"

summary = {
    "dsn_used": dsn,
    "env_exists": (ROOT / ".env").exists(),
    "anthropic_loaded": bool(os.getenv("ANTHROPIC_API_KEY")),
    "live_kill_switch": os.getenv("LIVE_KILL_SWITCH"),
}

print("\n=== 1. DB CONNECTION + TABLE DISCOVERY ===")
try:
    import psycopg
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database(), current_user, now()")
            db_info = cur.fetchone()
            summary["db_info"] = {
                "database": db_info[0],
                "user": db_info[1],
                "now": db_info[2],
            }
            print("DB OK:", db_info)

            cur.execute("""
                select table_schema, table_name
                from information_schema.tables
                where table_schema not in ('pg_catalog','information_schema')
                order by table_schema, table_name
            """)
            tables = [{"schema": r[0], "table": r[1]} for r in cur.fetchall()]
            summary["tables_found"] = tables
            print("Tables found:", len(tables))
            for t in tables:
                print(f"{t['schema']}.{t['table']}")

            wanted_keywords = [
                "market",
                "paper",
                "signal",
                "order",
                "position",
                "event",
                "whale",
                "intelligence",
                "ingestion",
                "external",
                "runtime",
                "digest",
            ]

            candidate_tables = []
            for t in tables:
                name = t["table"].lower()
                if any(k in name for k in wanted_keywords):
                    candidate_tables.append(t)

            counts = {}
            for t in candidate_tables:
                full = f'"{t["schema"]}"."{t["table"]}"'
                key = f'{t["schema"]}.{t["table"]}'
                try:
                    cur.execute(f"select count(*) from {full}")
                    counts[key] = cur.fetchone()[0]
                    print(f"COUNT {key}: {counts[key]}")
                except Exception as e:
                    counts[key] = f"ERROR: {type(e).__name__}: {e}"
                    print(f"COUNT {key}: {counts[key]}")

            summary["candidate_counts"] = counts

            columns = {}
            for t in candidate_tables:
                key = f'{t["schema"]}.{t["table"]}'
                cur.execute("""
                    select column_name, data_type
                    from information_schema.columns
                    where table_schema=%s and table_name=%s
                    order by ordinal_position
                """, (t["schema"], t["table"]))
                columns[key] = [{"column": r[0], "type": r[1]} for r in cur.fetchall()]
            summary["candidate_columns"] = columns

except Exception as e:
    summary["db_error"] = f"{type(e).__name__}: {e}"
    summary["db_trace"] = traceback.format_exc()
    print("DB ERROR:", summary["db_error"])

print("\n=== 2. RECENT LOG SCAN ONLY ===")
patterns_bad = [
    "JSONDecodeError",
    "runtime_intelligence_refresh_failed",
    "at least one market_id is required",
    "runtime_whale_refresh_skipped",
]
patterns_good = [
    "runtime_ai_digest_result",
    "runtime_whale_refresh_noop",
    "runtime_whale_refresh_complete",
]
patterns_all = patterns_bad + patterns_good

now = datetime.now()
cutoff = now - timedelta(hours=12)
matches = []

for base in [ROOT / "logs", ROOT / "artifacts"]:
    if not base.exists():
        continue
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in [".log", ".txt", ".json", ".md"]:
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if mtime < cutoff:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pat in patterns_all:
            if pat in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if pat in line:
                        matches.append({
                            "file": str(p),
                            "mtime": mtime.isoformat(),
                            "line": i,
                            "pattern": pat,
                            "text": line[:500],
                        })

bad_recent = [m for m in matches if m["pattern"] in patterns_bad]
good_recent = [m for m in matches if m["pattern"] in patterns_good]

summary["recent_log_matches"] = matches[:300]
summary["recent_bad_count"] = len(bad_recent)
summary["recent_good_count"] = len(good_recent)

print("Recent bad markers:", len(bad_recent))
for m in bad_recent[:50]:
    print(f"BAD {m['pattern']} | {m['file']}:{m['line']} | {m['text']}")

print("Recent good markers:", len(good_recent))
for m in good_recent[:50]:
    print(f"GOOD {m['pattern']} | {m['file']}:{m['line']} | {m['text']}")

print("\n=== 3. STATUS ===")
has_db = "db_error" not in summary
has_tables = len(summary.get("tables_found", [])) > 0
has_relevant_counts = len(summary.get("candidate_counts", {})) > 0

if has_db and has_tables and summary["recent_bad_count"] == 0:
    status = "GREEN_SCHEMA_DB"
elif has_db and has_tables:
    status = "YELLOW_RECENT_BAD_MARKERS_OR_NO_RUNTIME_PROOF"
else:
    status = "RED_DB_OR_SCHEMA"

summary["final_status"] = status

print(json.dumps({
    "final_status": status,
    "db_ok": has_db,
    "tables_found": len(summary.get("tables_found", [])),
    "candidate_tables_counted": len(summary.get("candidate_counts", {})),
    "recent_bad_count": summary["recent_bad_count"],
    "recent_good_count": summary["recent_good_count"],
}, indent=2, ensure_ascii=False))

write("summary.json", summary)
write("tables.json", summary.get("tables_found", []))
write("candidate_counts.json", summary.get("candidate_counts", {}))
write("candidate_columns.json", summary.get("candidate_columns", {}))
