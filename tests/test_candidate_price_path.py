from __future__ import annotations

from datetime import timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.orderbook_price_readiness import CandidatePricePathService
from app.control_center.paper_readiness import PaperReadinessService
from app.control_center.runtime_supervisor import RuntimeSupervisorService
from app.db.connection import DatabaseConnectionFactory

_ORDERBOOK_TEST_SPEC = spec_from_file_location("_phase7_orderbook_test_helpers", Path(__file__).with_name("test_orderbook_price_readiness.py"))
assert _ORDERBOOK_TEST_SPEC and _ORDERBOOK_TEST_SPEC.loader
_ORDERBOOK_TEST_HELPERS = module_from_spec(_ORDERBOOK_TEST_SPEC)
_ORDERBOOK_TEST_SPEC.loader.exec_module(_ORDERBOOK_TEST_HELPERS)

_Governor = _ORDERBOOK_TEST_HELPERS._Governor
_Runtime = _ORDERBOOK_TEST_HELPERS._Runtime
_artifact_counts = _ORDERBOOK_TEST_HELPERS._artifact_counts
_prepare_case = _ORDERBOOK_TEST_HELPERS._prepare_case


def _candidate_item(candidate_id: str) -> dict[str, Any]:
    payload = CandidatePricePathService(connection_factory=DatabaseConnectionFactory()).get_candidate(candidate_id)
    assert payload is not None
    return payload["candidate"]


def test_fresh_matching_token_side_orderbook_is_candidate_price_ready(postgres_test_schema) -> None:
    candidate_id = _prepare_case("candidate-fresh")

    item = _candidate_item(candidate_id)

    assert item["candidate_price_path_state"] == "CANDIDATE_PRICE_READY"
    assert item["candidate_trusted_orderbook_state"] == "TRUSTED_FRESH_FOR_CANDIDATE"
    assert item["refresh_before_execution_state"] == "NOT_REQUIRED"


def test_global_fresh_wrong_token_does_not_become_candidate_price_ready(postgres_test_schema) -> None:
    candidate_id = _prepare_case("wrong-token", expected_token="right-token", seed_orderbook=False)
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                mid_price, spread, snapshot_at, collected_at, snapshot_status,
                is_stale, source, created_at
            )
            VALUES ('wrong-token-book', 'market-wrong-token', 'wrong-token', 'YES', 0.40, 0.41,
                    0.405, 0.01, %s, %s, 'OK', false, 'test', %s)
            """,
            (now, now, now),
        )

    item = _candidate_item(candidate_id)

    assert item["candidate_price_path_state"] != "CANDIDATE_PRICE_READY"
    assert item["candidate_price_path_state"] in {"CANDIDATE_MISSING_ORDERBOOK", "CANDIDATE_UNTRUSTED_ORDERBOOK"}


def test_missing_token_and_side_are_candidate_specific(postgres_test_schema) -> None:
    missing_token = _prepare_case("candidate-missing-token", expected_token=None, market_tokens=False)
    missing_side = _prepare_case("candidate-missing-side", side=None, expected_token=None, market_tokens=False, reset=False)

    assert _candidate_item(missing_token)["candidate_price_path_state"] == "CANDIDATE_MISSING_TOKEN"
    assert _candidate_item(missing_side)["candidate_price_path_state"] == "CANDIDATE_MISSING_SIDE"


def test_stale_candidate_orderbook_requires_refresh(postgres_test_schema) -> None:
    candidate_id = _prepare_case("candidate-stale", orderbook_age=timedelta(minutes=10))

    item = _candidate_item(candidate_id)

    assert item["candidate_price_path_state"] == "CANDIDATE_STALE_ORDERBOOK"
    assert item["refresh_before_execution_state"] == "REQUIRED"
    assert item["refresh_plan"]["can_refresh"] is True


def test_candidate_price_path_endpoint_is_read_only(postgres_test_schema) -> None:
    _prepare_case("candidate-readonly")
    before = _artifact_counts()
    app = FastAPI()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/candidate-price-path")

    assert response.status_code == 200
    payload = response.json()
    assert "candidate_price_ready" in payload["counts"]
    assert _artifact_counts() == before


def test_paper_readiness_includes_candidate_price_counts(postgres_test_schema) -> None:
    _prepare_case("paper-candidate-price", paper_simulation=False)

    payload = PaperReadinessService(
        connection_factory=DatabaseConnectionFactory(),
        governor=_Governor(),
        runtime_readiness=_Runtime(),
    ).get_readiness()

    assert payload["paper_simulation_state"] == "OFF"
    assert payload["paper_readiness_state"] == "BLOCKED"
    assert "candidate_price_ready_count" in payload["counts"]
    assert "candidate_targeted_refresh_state" in payload


class _CandidateOrderbookRefresher:
    def resolve(self, **kwargs) -> dict[str, Any]:
        return {
            "candidates_checked": 2,
            "trusted_matches_created": 0,
            "trusted_matches_refreshed": 1,
            "orderbook_snapshots_created": 1,
            "missing_orderbook_count": 0,
            "stale_count": 1,
            "token_mismatch_count": 0,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "safety_counts_before": {"paper_intents": 1, "paper_orders": 0, "paper_fills": 0, "paper_positions": 0, "live_orders": 0, "orders_v2": 0, "fills_v2": 0, "canonical_positions": 0},
            "safety_counts_after": {"paper_intents": 1, "paper_orders": 0, "paper_fills": 0, "paper_positions": 0, "live_orders": 0, "orders_v2": 0, "fills_v2": 0, "canonical_positions": 0},
            "rejected_reason_counts": [],
        }


def test_supervisor_candidate_targeted_refresh_uses_bounded_module() -> None:
    result = RuntimeSupervisorService(governor=_Governor(), candidate_orderbook_refresher=_CandidateOrderbookRefresher())._run_candidate_orderbook_refresher_module()

    assert result.module == "candidate_orderbook_refresher"
    assert result.status == "COMPLETED"
    assert result.counters["candidates_checked"] == 2
    assert result.counters["orderbook_snapshots_created"] == 1
    assert result.errors == []
