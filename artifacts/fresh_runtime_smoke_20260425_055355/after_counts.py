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

before = json.loads((OUT / "before_counts.json").read_text(encoding="utf-8"))
before_counts = before["counts"]

tables = list(before_counts.keys())
after = {"captured_at": datetime.now().isoformat(), "counts": {}, "delta": {}}

with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
    with conn.cursor() as cur:
        for t in tables:
            try:
                cur.execute(f'select count(*) from public."{t}"')
                c = cur.fetchone()[0]
                after["counts"][t] = c
                b = before_counts.get(t)
                after["delta"][t] = c - b if isinstance(b, int) else None
            except Exception as e:
                after["counts"][t] = f"ERROR: {type(e).__name__}: {e}"
                after["delta"][t] = None

print(json.dumps(after, indent=2, ensure_ascii=False))
(OUT / "after_counts.json").write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding="utf-8")
