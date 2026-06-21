from __future__ import annotations

from app.services.query.full_system_run_query_service import (
    detect_duplicate_active_orders,
    evaluate_dashboard_payloads,
)


def test_duplicate_detector_groups_active_orders_by_market_side_engine() -> None:
    duplicates = detect_duplicate_active_orders(
        [
            {"order_id": "o1", "market_id": "m1", "side": "YES", "engine": "SAFE"},
            {"order_id": "o2", "market_id": "m1", "side": "YES", "engine": "SAFE"},
            {"order_id": "o3", "market_id": "m1", "side": "NO", "engine": "SAFE"},
        ]
    )

    assert duplicates == [
        {
            "market_id": "m1",
            "side": "YES",
            "engine": "SAFE",
            "count": 2,
            "order_ids": ["o1", "o2"],
        }
    ]


def test_dashboard_truth_accepts_stale_or_no_data_when_it_is_labeled() -> None:
    result = evaluate_dashboard_payloads(
        {
            "/dashboard/api/v2/overview": {
                "status": "OK",
                "stale": False,
                "data_source": {"mock_data": False},
                "errors": [],
            },
            "/dashboard/api/v2/learning": {
                "status": "NO_DATA",
                "stale": True,
                "data_source": {"mock_data": False},
                "errors": [],
            },
        }
    )

    assert result["ok"] is True
    assert result["stale_count"] == 1
    assert result["insufficient_or_degraded_count"] == 1


def test_dashboard_truth_rejects_mock_data_flags() -> None:
    result = evaluate_dashboard_payloads(
        {
            "/dashboard/api/v2/overview": {
                "status": "OK",
                "stale": False,
                "data_source": {"mock_data": True},
                "errors": [],
            }
        }
    )

    assert result["ok"] is False
    assert "/dashboard/api/v2/overview:mock_data_true" in result["violations"]
