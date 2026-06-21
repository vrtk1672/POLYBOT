from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.services import risk_evidence_mesh as risk_mesh
from app.services.full_mesh_contract import mesh_response, validate_mesh_response
from app.services.full_mesh_registry import registry_by_name
from app.services.mesh_organ_adapters import query_organ
from app.services.source_backed_edge_engine import build_edge_thesis


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Conn:
    def __init__(
        self,
        *,
        tables: set[str],
        rows: dict[str, list[dict[str, Any]]],
        registry: list[dict[str, Any]] | None = None,
        creds: list[dict[str, Any]] | None = None,
    ) -> None:
        self.tables = tables
        self.rows = rows
        self.registry = registry or []
        self.creds = creds or []

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Result:
        if "to_regclass" in sql:
            table = str(params[0])
            return _Result([{"reg": table if table in self.tables else None}])
        if "FROM intelligence_source_registry" in sql:
            source_types = set(params[0])
            return _Result([row for row in self.registry if row["source_type"] in source_types])
        if "FROM intelligence_source_credentials_status" in sql:
            source_ids = set(params[0])
            return _Result([row for row in self.creds if row["source_id"] in source_ids])
        for table, rows in self.rows.items():
            if f"FROM {table}" in sql:
                return _Result(rows)
        return _Result([])


class _Factory:
    enabled = True

    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def connect(self) -> _Conn:
        return self._conn


def _identity() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-complete-audit",
        "market_id": "market-complete-audit",
        "condition_id": "condition-complete-audit",
        "side": "YES",
        "token_id": "token-yes",
        "correlation_id": "corr-complete-audit",
        "event_id": "event-complete-audit",
    }


def _record() -> dict[str, Any]:
    return {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-complete-audit",
        "market_id": "market-complete-audit",
        "condition_id": "condition-complete-audit",
        "side": "YES",
        "token_id": "token-yes",
    }


def _orderbook() -> dict[str, Any]:
    return {
        "orderbook_snapshot_id": "ob-complete-audit",
        "created_at": datetime.now(UTC),
        "best_ask": "0.42",
        "best_bid": "0.40",
        "spread": "0.02",
        "liquidity_score": "0.80",
    }


def _source_response(*, linked: bool = True, freshness_seconds: int = 10) -> dict[str, Any]:
    return mesh_response(
        neuron_name="signal_quality",
        neuron_type="SIGNAL",
        identity=_identity(),
        response_state="SUPPORTED",
        supports_side="YES",
        confidence=0.95,
        strength=0.95,
        freshness_seconds=freshness_seconds,
        source_backed=True,
        summary="Fixture directional source supports candidate side.",
        reason="Fixture source response is candidate linked.",
        source_records=[{"source_type": "neuron_signals", "source_record_id": "signal-complete-audit"}],
        metadata={
            "source_organ": True,
            "source_organ_runtime_state": "ACTIVE_CANDIDATE_SCOPED" if linked else "ACTIVE_MARKET_LEVEL_ONLY",
            "candidate_link_state": "CANDIDATE_LINKED_MARKET_SIDE" if linked else "MARKET_LEVEL_ONLY",
        },
    )


def test_registered_source_organs_have_auditable_runtime_status() -> None:
    registry = registry_by_name()

    for name in (
        "news",
        "whale",
        "social",
        "cross_market",
        "market_memory",
        "market_movement",
        "signal_quality",
        "signal_processing",
        "payout",
        "ai_reasoner",
    ):
        registration = registry[name]
        assert registration.safe_for_pre_paper_inquiry is True
        assert registration.adapter_name
        assert registration.neuron_type


def test_missing_config_reports_key_names_without_secret_values() -> None:
    conn = _Conn(
        tables={"social_market_links", "social_hype_scores", "intelligence_source_registry", "intelligence_source_credentials_status"},
        rows={"social_market_links": [], "social_hype_scores": []},
        registry=[
            {
                "source_id": "reddit_api",
                "source_type": "SOCIAL",
                "status": "MISSING_CREDENTIALS",
                "health_status": "BLOCKED_MISSING_CREDENTIALS",
                "required_env_vars": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
                "optional_env_vars": ["REDDIT_USER_AGENT"],
                "target_tables_json": [],
            }
        ],
        creds=[
            {"source_id": "reddit_api", "env_var": "REDDIT_CLIENT_ID", "required": True, "present": False},
            {"source_id": "reddit_api", "env_var": "REDDIT_CLIENT_SECRET", "required": True, "present": False},
        ],
    )

    response = query_organ(registry_by_name()["social"], identity=_identity(), bundle={}, connection_factory=_Factory(conn))

    validate_mesh_response(response)
    assert response["response_state"] == "UNAVAILABLE"
    assert response["metadata"]["source_organ_runtime_state"] == "UNAVAILABLE_MISSING_CONFIG"
    assert response["metadata"]["missing_config_keys"] == ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]
    assert "secret-value" not in str(response).lower()


def test_source_with_stale_rows_reports_stale_with_age() -> None:
    stale_time = datetime.now(UTC) - timedelta(seconds=2000)
    conn = _Conn(
        tables={"payout_odds_evaluations"},
        rows={
            "payout_odds_evaluations": [
                {
                    "evaluation_id": "payout-complete-audit",
                    "subject_id": "candidate-complete-audit",
                    "market_id": "market-complete-audit",
                    "side": "YES",
                    "token_id": "token-yes",
                    "risk_reward": "1.8",
                    "created_at": stale_time,
                }
            ]
        },
    )

    response = query_organ(registry_by_name()["payout"], identity=_identity(), bundle={}, connection_factory=_Factory(conn))

    validate_mesh_response(response)
    assert response["response_state"] == "STALE"
    assert response["blocker_code"] == "SOURCE_STALE"
    assert response["freshness_seconds"] >= 1900
    assert response["metadata"]["source_organ_runtime_state"] == "ACTIVE_CANDIDATE_SCOPED"


def test_market_level_source_is_visible_but_not_candidate_actionable() -> None:
    thesis = build_edge_thesis(_record(), {"orderbook": _orderbook(), "mesh_responses": [_source_response(linked=False)]})

    assert thesis["edge_state"] == "EDGE_WATCH"
    assert thesis["source_backed"] is False
    assert thesis["risk_usable"] is False


def test_candidate_linked_directional_source_reaches_risk_metadata() -> None:
    evidence = {"orderbook": _orderbook(), "mesh_responses": [_source_response(linked=True)]}

    classified = risk_mesh._classify(_record(), evidence)

    thesis = classified["edge_thesis"]
    assert thesis["edge_state"] == "EDGE_SUPPORTED"
    assert thesis["risk_usable"] is True
    assert thesis["source_organs_queried"] == 1
    assert thesis["directional_sources_found"] == 1
    assert classified["risk_blocker_subtype"] != "RISK_BLOCKED_NO_SOURCE_BACKED_EDGE"
