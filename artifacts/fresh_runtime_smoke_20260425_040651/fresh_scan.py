from pathlib import Path
import os, json
from datetime import datetime, timedelta

ROOT = Path.cwd()
OUT = Path(os.environ["POLY_SMOKE_OUT"])

start = datetime.fromisoformat(os.environ["POLY_SMOKE_START_TS"])
bad_patterns = [
    "JSONDecodeError",
    "runtime_intelligence_refresh_failed",
    "at least one market_id is required",
    "runtime_whale_refresh_skipped",
]
good_patterns = [
    "runtime_ai_digest_result",
    "runtime_whale_refresh_noop",
    "runtime_whale_refresh_complete",
    "AI_INTELLIGENCE_DIGEST",
]
all_patterns = bad_patterns + good_patterns

matches = []
scan_roots = [OUT, ROOT / "logs"]

for base in scan_roots:
    if not base.exists():
        continue
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in [".log", ".txt", ".json", ".md"]:
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if mtime < start:
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pat in all_patterns:
            if pat in txt:
                for i, line in enumerate(txt.splitlines(), 1):
                    if pat in line:
                        matches.append({
                            "file": str(p),
                            "line": i,
                            "pattern": pat,
                            "text": line[:500],
                        })

bad = [m for m in matches if m["pattern"] in bad_patterns]
good = [m for m in matches if m["pattern"] in good_patterns]

before = json.loads((OUT / "before_counts.json").read_text(encoding="utf-8"))
after = json.loads((OUT / "after_counts.json").read_text(encoding="utf-8"))

important_delta = {
    k: v for k, v in after["delta"].items()
    if k in [
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
    ]
}

runtime_growth = any((v or 0) > 0 for v in important_delta.values())

if len(bad) == 0 and runtime_growth:
    status = "GREEN_FRESH_RUNTIME"
elif len(bad) == 0:
    status = "YELLOW_NO_FRESH_GROWTH_BUT_NO_OLD_FAILURE"
else:
    status = "RED_OLD_FAILURE_REPRODUCED"

summary = {
    "status": status,
    "bad_count": len(bad),
    "good_count": len(good),
    "important_delta": important_delta,
    "bad_matches": bad[:100],
    "good_matches": good[:100],
}

print(json.dumps(summary, indent=2, ensure_ascii=False))
(OUT / "fresh_runtime_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
