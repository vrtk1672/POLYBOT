from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from app.services.query.full_system_run_query_service import (
    DASHBOARD_ENDPOINTS,
    FullSystemRunQueryService,
    evaluate_no_live_mutation,
    json_default,
    utc_now_iso,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")


def run_smoke(args: argparse.Namespace) -> int:
    service = FullSystemRunQueryService()
    run_id = f"v2_20_{args.mode.lower()}_{uuid4().hex[:10]}"
    started_at = utc_now_iso()
    before = service.fetch_count_snapshot()
    checkpoints: list[dict] = []
    deadline = time.monotonic() + max(args.duration_seconds, 0)

    while True:
        checkpoints.append(service.collect_checkpoint(base_url=args.base_url))
        if time.monotonic() >= deadline:
            break
        time.sleep(max(args.interval_seconds, 1))

    after = service.fetch_count_snapshot()
    finished_at = utc_now_iso()
    report = service.build_report(
        run_id=run_id,
        run_type=args.run_type,
        mode=args.mode,
        started_at=started_at,
        finished_at=finished_at,
        before_counts=before,
        after_counts=after,
        checkpoints=checkpoints,
    )
    out_path = Path(args.out_dir) / f"{run_id}.json"
    _write_json(out_path, report)
    print(json.dumps({"report_path": str(out_path), "status": report["status"]}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def checkpoint(args: argparse.Namespace) -> int:
    service = FullSystemRunQueryService()
    print(json.dumps(service.collect_checkpoint(base_url=args.base_url), indent=2, default=json_default))
    return 0


def verify_no_live_mutation(args: argparse.Namespace) -> int:
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    result = evaluate_no_live_mutation(before, after, args.mode)
    print(json.dumps(result, indent=2, default=json_default))
    return 0 if result["ok"] else 2


def counts(args: argparse.Namespace) -> int:
    service = FullSystemRunQueryService()
    payload = service.fetch_count_snapshot()
    if args.out:
        _write_json(Path(args.out), payload)
    print(json.dumps(payload, indent=2, default=json_default))
    return 0


def verify_duplicates_orphans(args: argparse.Namespace) -> int:
    service = FullSystemRunQueryService()
    payload = service.detect_duplicates_orphans()
    print(json.dumps(payload, indent=2, default=json_default))
    return 0 if payload.get("ok", False) else 2


def verify_dashboard_truth(args: argparse.Namespace) -> int:
    service = FullSystemRunQueryService()
    results = service.fetch_endpoints(args.base_url, DASHBOARD_ENDPOINTS)
    payloads = {
        endpoint: result.payload or {}
        for endpoint, result in results.items()
        if result.ok and result.payload is not None
    }
    truth = service.collect_checkpoint(base_url=args.base_url)["dashboard_truth"]
    output = {
        "truth": truth,
        "endpoints": {endpoint: result.to_dict() for endpoint, result in results.items()},
    }
    print(json.dumps(output, indent=2, default=json_default))
    return 0 if truth["ok"] and len(payloads) == len(DASHBOARD_ENDPOINTS) else 2


def verify_ai_cost_cache(args: argparse.Namespace) -> int:
    service = FullSystemRunQueryService()
    payload = service.fetch_ai_cost_cache()
    print(json.dumps(payload, indent=2, default=json_default))
    return 0 if payload.get("status") in {"OK", "NO_DATA"} and payload.get("bounded", True) is not False else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="POLYBOT V2.20 full-system verification helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("run-smoke")
    smoke.add_argument("--mode", required=True, choices=["DATA_ONLY", "PAPER"])
    smoke.add_argument("--run-type", default="smoke")
    smoke.add_argument("--duration-seconds", type=int, default=60)
    smoke.add_argument("--interval-seconds", type=int, default=30)
    smoke.add_argument("--base-url", default="http://127.0.0.1:8000")
    smoke.add_argument("--out-dir", default="run_reports/v2_20")
    smoke.set_defaults(func=run_smoke)

    check = sub.add_parser("checkpoint")
    check.add_argument("--base-url", default="http://127.0.0.1:8000")
    check.set_defaults(func=checkpoint)

    count = sub.add_parser("counts")
    count.add_argument("--out")
    count.set_defaults(func=counts)

    no_live = sub.add_parser("verify-no-live-mutation")
    no_live.add_argument("--before", required=True)
    no_live.add_argument("--after", required=True)
    no_live.add_argument("--mode", required=True, choices=["DATA_ONLY", "PAPER"])
    no_live.set_defaults(func=verify_no_live_mutation)

    dup = sub.add_parser("verify-duplicates-orphans")
    dup.set_defaults(func=verify_duplicates_orphans)

    dash = sub.add_parser("verify-dashboard-truth")
    dash.add_argument("--base-url", default="http://127.0.0.1:8000")
    dash.set_defaults(func=verify_dashboard_truth)

    ai = sub.add_parser("verify-ai-cost-cache")
    ai.set_defaults(func=verify_ai_cost_cache)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
