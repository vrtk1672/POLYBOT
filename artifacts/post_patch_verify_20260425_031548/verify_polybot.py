from pathlib import Path
import os
import sys
import json
import subprocess
import traceback

ROOT = Path.cwd()
OUT = Path(os.environ.get("POLY_VERIFY_OUT", "artifacts/post_patch_verify_unknown"))
OUT.mkdir(parents=True, exist_ok=True)

def section(name):
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)

def write(name, data):
    p = OUT / name
    p.write_text(str(data), encoding="utf-8")

def run(cmd, name, timeout=120):
    section(f"RUN: {cmd}")
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        text = ""
        text += f"COMMAND: {cmd}\n"
        text += f"EXIT_CODE: {r.returncode}\n\n"
        text += "--- STDOUT ---\n"
        text += r.stdout or ""
        text += "\n--- STDERR ---\n"
        text += r.stderr or ""
        write(name, text)
        print(text)
        return r.returncode, text
    except Exception as e:
        text = f"COMMAND: {cmd}\nEXCEPTION: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        write(name, text)
        print(text)
        return 999, text

results = {}

section("1. ENV CHECK")
env_path = ROOT / ".env"
print("ENV exists:", env_path.exists())

env = {}
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

safe_env = {
    "DATABASE_URL": os.getenv("DATABASE_URL"),
    "RUNTIME_MODE": os.getenv("RUNTIME_MODE"),
    "EXECUTION_BACKEND": os.getenv("EXECUTION_BACKEND"),
    "LIVE_ENABLED": os.getenv("LIVE_ENABLED"),
    "LIVE_KILL_SWITCH": os.getenv("LIVE_KILL_SWITCH"),
    "ANTHROPIC_API_KEY_LOADED": bool(os.getenv("ANTHROPIC_API_KEY")),
    "ANTHROPIC_API_KEY_PREVIEW": (os.getenv("ANTHROPIC_API_KEY", "")[:8] + "...") if os.getenv("ANTHROPIC_API_KEY") else None,
}
print(json.dumps(safe_env, indent=2, ensure_ascii=False))
write("env_check.json", json.dumps(safe_env, indent=2, ensure_ascii=False))

results["env_exists"] = env_path.exists()
results["anthropic_loaded"] = bool(os.getenv("ANTHROPIC_API_KEY"))

section("2. PYTHON IMPORT CHECK")
imports = [
    "psycopg",
    "dotenv",
    "pytest",
]
for mod in imports:
    try:
        __import__(mod)
        print(f"[OK] import {mod}")
        results[f"import_{mod}"] = True
    except Exception as e:
        print(f"[FAIL] import {mod}: {type(e).__name__}: {e}")
        results[f"import_{mod}"] = False

section("3. POSTGRES CONNECTION CHECK")
dsn = os.getenv("DATABASE_URL") or "postgresql://polybot:polybot@127.0.0.1:55432/polybot"
print("DSN:", dsn)

try:
    import psycopg
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("select now()")
            print("[OK] DB connected:", cur.fetchone()[0])
    results["db_connected"] = True
except Exception as e:
    print("[FAIL] DB connection:", type(e).__name__, e)
    results["db_connected"] = False

section("4. COMPILE CHECK")
compile_cmd = (
    '.venv\\Scripts\\python.exe -m py_compile '
    'app\\services\\runtime_intelligence.py '
    'app\\services\\whale_scoring.py '
    'tests\\test_runtime_intelligence.py '
    'tests\\test_phase5d_whale_scoring.py'
)
code, text = run(compile_cmd, "compile_check.txt", timeout=120)
results["compile_ok"] = code == 0

section("5. FOCUSED TESTS")
pytest_cmd = (
    '.venv\\Scripts\\python.exe -m pytest '
    'tests\\test_runtime_intelligence.py '
    'tests\\test_phase5d_whale_scoring.py '
    'tests\\test_market_service.py '
    'tests\\test_phase2_signal_paper.py '
    'tests\\test_phase2_execution_aware_paper.py '
    '-q'
)
code, text = run(pytest_cmd, "focused_tests.txt", timeout=180)
results["pytest_ok"] = code == 0

section("6. MIGRATION")
mig_cmd = 'powershell -ExecutionPolicy Bypass -File scripts\\migrate_runtime.ps1'
code, text = run(mig_cmd, "migration.txt", timeout=180)
results["migration_ok"] = code == 0

section("7. DB COUNTS")
counts = {}
if results.get("db_connected"):
    try:
        import psycopg
        tables = [
            "markets",
            "paper_signals",
            "paper_orders",
            "paper_positions",
            "paper_position_events",
            "intelligence_ingestion_runs",
            "external_events_normalized",
            "whale_events",
            "whale_market_scores",
        ]
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                for t in tables:
                    try:
                        cur.execute(f"select count(*) from {t}")
                        counts[t] = cur.fetchone()[0]
                        print(f"{t}: {counts[t]}")
                    except Exception as e:
                        counts[t] = f"ERROR: {type(e).__name__}: {e}"
                        print(f"{t}: {counts[t]}")
    except Exception as e:
        print("[FAIL] DB counts:", type(e).__name__, e)
else:
    print("[SKIP] DB not connected")

write("db_counts.json", json.dumps(counts, indent=2, ensure_ascii=False))
results["db_counts"] = counts

section("8. OLD FAILURE SCAN")
patterns = [
    "JSONDecodeError",
    "runtime_intelligence_refresh_failed",
    "at least one market_id is required",
    "runtime_whale_refresh_skipped",
    "runtime_ai_digest_result",
    "runtime_whale_refresh_noop",
    "runtime_whale_refresh_complete",
]
scan_roots = [ROOT / "logs", ROOT / "artifacts"]
matches = []

for base in scan_roots:
    if not base.exists():
        continue
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in [".log", ".txt", ".json", ".md"]:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in patterns:
            if pat in txt:
                lines = txt.splitlines()
                for i, line in enumerate(lines, start=1):
                    if pat in line:
                        matches.append({
                            "file": str(p),
                            "line": i,
                            "pattern": pat,
                            "text": line[:500],
                        })

for m in matches[:200]:
    print(f"{m['pattern']} | {m['file']}:{m['line']} | {m['text']}")
if len(matches) > 200:
    print(f"... truncated, total matches: {len(matches)}")

write("failure_scan.json", json.dumps(matches, indent=2, ensure_ascii=False))

old_bad = [
    m for m in matches
    if m["pattern"] in [
        "JSONDecodeError",
        "runtime_intelligence_refresh_failed",
        "at least one market_id is required",
        "runtime_whale_refresh_skipped",
    ]
]
results["old_failure_matches"] = len(old_bad)
results["new_good_markers"] = len([
    m for m in matches
    if m["pattern"] in [
        "runtime_ai_digest_result",
        "runtime_whale_refresh_noop",
        "runtime_whale_refresh_complete",
    ]
])

section("9. FINAL STATUS")
critical = [
    results.get("env_exists"),
    results.get("db_connected"),
    results.get("compile_ok"),
    results.get("pytest_ok"),
    results.get("migration_ok"),
]

if all(critical) and results.get("old_failure_matches", 0) == 0:
    status = "GREEN"
elif results.get("compile_ok") and results.get("db_connected"):
    status = "YELLOW"
else:
    status = "RED"

results["final_status"] = status

print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
write("summary.json", json.dumps(results, indent=2, ensure_ascii=False, default=str))

print("\nFINAL_STATUS:", status)
print("SUMMARY_FILE:", OUT / "summary.json")
