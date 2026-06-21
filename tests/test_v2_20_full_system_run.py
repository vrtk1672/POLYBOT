from __future__ import annotations

import json

from app.services.query.full_system_run_query_service import (
    FullSystemRunQueryService,
    evaluate_no_live_mutation,
)


def test_run_report_builder_marks_pass_when_data_only_has_no_execution_mutation() -> None:
    service = FullSystemRunQueryService()
    before = {
        "live_orders": 0,
        "paper_orders": 4,
        "orders_v2": 2,
        "fills_v2": 1,
        "exit_intents": 1,
    }
    after = dict(before, event_log=10)

    report = service.build_report(
        run_id="run-test",
        run_type="data_only_smoke",
        mode="DATA_ONLY",
        started_at="2026-05-18T00:00:00+00:00",
        finished_at="2026-05-18T00:01:00+00:00",
        before_counts=before,
        after_counts=after,
        checkpoints=[{"checkpoint_ts": "now"}],
    )

    assert report["status"] == "PASS"
    assert report["safety_summary"]["ok"] is True
    json.dumps(report)


def test_run_report_builder_marks_fail_when_live_orders_change() -> None:
    service = FullSystemRunQueryService()
    before = {"live_orders": 0, "paper_orders": 0, "orders_v2": 0, "fills_v2": 0, "exit_intents": 0}
    after = {"live_orders": 1, "paper_orders": 0, "orders_v2": 0, "fills_v2": 0, "exit_intents": 0}

    report = service.build_report(
        run_id="run-test",
        run_type="paper_smoke",
        mode="PAPER",
        started_at="2026-05-18T00:00:00+00:00",
        finished_at="2026-05-18T00:01:00+00:00",
        before_counts=before,
        after_counts=after,
        checkpoints=[],
    )

    assert report["status"] == "FAIL"
    assert "live_orders_changed" in report["safety_summary"]["violations"]


def test_paper_safety_allows_internal_paper_shadow_growth() -> None:
    before = {"live_orders": 0, "paper_orders": 0, "orders_v2": 0, "fills_v2": 0, "exit_intents": 0}
    after = {"live_orders": 0, "paper_orders": 1, "orders_v2": 1, "fills_v2": 1, "exit_intents": 1}

    result = evaluate_no_live_mutation(before, after, "PAPER")

    assert result["ok"] is True
    assert result["violations"] == []


def test_data_only_safety_blocks_paper_execution_growth() -> None:
    before = {"live_orders": 0, "paper_orders": 0, "orders_v2": 0, "fills_v2": 0, "exit_intents": 0}
    after = {"live_orders": 0, "paper_orders": 0, "orders_v2": 1, "fills_v2": 0, "exit_intents": 0}

    result = evaluate_no_live_mutation(before, after, "DATA_ONLY")

    assert result["ok"] is False
    assert "orders_v2_created_in_data_only" in result["violations"]
