from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.full_mesh_contract import identity_from_bundle, validate_mesh_response
from app.services.full_mesh_registry import registry_by_name
from app.services.mesh_organ_adapters import query_organ


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Conn:
    def __init__(self, *, tables: set[str], rows: dict[str, list[dict[str, Any]]], registry: list[dict[str, Any]] | None = None, creds: list[dict[str, Any]] | None = None) -> None:
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
    return identity_from_bundle(
        {
            "candidate_id": "candidate-1",
            "market_id": "m1",
            "condition_id": "cond1",
            "side": "YES",
            "token_id": "token-yes",
            "correlation_id": "corr-1",
            "event_id": "event-1",
        }
    )


def test_existing_source_organs_are_registered() -> None:
    registry = registry_by_name()

    for name in ("news", "whale", "social", "market_memory", "signal_quality", "signal_processing", "payout", "cross_market", "ai_reasoner"):
        assert name in registry


def test_candidate_linked_news_row_becomes_mesh_response() -> None:
    conn = _Conn(
        tables={"news_impact_scores", "intelligence_source_registry", "intelligence_source_credentials_status"},
        rows={
            "news_impact_scores": [
                {
                    "impact_id": "impact-1",
                    "market_id": "m1",
                    "direction": "YES",
                    "strength": 0.92,
                    "confidence": 0.91,
                    "already_priced_in": 0.0,
                    "ttl_seconds": 5400,
                    "reason": "fixture source supports candidate side",
                    "created_at": datetime.now(UTC),
                }
            ]
        },
        registry=[{"source_id": "newsapi", "source_type": "NEWS", "status": "READY", "health_status": "READY", "required_env_vars": ["NEWS_API_KEY"], "optional_env_vars": [], "target_tables_json": []}],
        creds=[{"source_id": "newsapi", "env_var": "NEWS_API_KEY", "required": True, "present": True}],
    )

    response = query_organ(registry_by_name()["news"], identity=_identity(), bundle={}, connection_factory=_Factory(conn))

    validate_mesh_response(response)
    assert response["response_state"] == "SUPPORTED"
    assert response["supports_side"] == "YES"
    assert response["metadata"]["source_organ_runtime_state"] == "ACTIVE_CANDIDATE_SCOPED"
    assert response["metadata"]["candidate_link_state"] == "CANDIDATE_LINKED_MARKET_SIDE"
    assert response["source_records"][0]["source_record_id"] == "impact-1"


def test_missing_source_config_reports_key_names_only() -> None:
    conn = _Conn(
        tables={"social_market_links", "social_hype_scores", "intelligence_source_registry", "intelligence_source_credentials_status"},
        rows={"social_market_links": [], "social_hype_scores": []},
        registry=[{"source_id": "reddit_api", "source_type": "SOCIAL", "status": "MISSING_CREDENTIALS", "health_status": "BLOCKED_MISSING_CREDENTIALS", "required_env_vars": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"], "optional_env_vars": ["REDDIT_USER_AGENT"], "target_tables_json": []}],
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
    assert "super-secret" not in str(response).lower()


def test_market_level_only_source_response_is_visible_but_not_candidate_scoped() -> None:
    conn = _Conn(
        tables={"whale_events", "intelligence_source_registry"},
        rows={
            "whale_events": [
                {
                    "whale_event_id": "whale-1",
                    "market_id": "m1",
                    "side": None,
                    "side_or_outcome": None,
                    "size_usd": 50000,
                    "event_time": datetime.now(UTC),
                    "detection_reason_text": "fixture market-level flow",
                }
            ]
        },
        registry=[{"source_id": "polymarket_clob_public_trades", "source_type": "WHALE", "status": "READY_NO_KEY", "health_status": "READY_NO_KEY", "required_env_vars": [], "optional_env_vars": [], "target_tables_json": []}],
    )

    response = query_organ(registry_by_name()["whale"], identity=_identity(), bundle={}, connection_factory=_Factory(conn))

    validate_mesh_response(response)
    assert response["metadata"]["source_organ_runtime_state"] == "ACTIVE_MARKET_LEVEL_ONLY"
    assert response["metadata"]["candidate_link_state"] == "MARKET_LEVEL_ONLY"
    assert response["strength"] == 0.0
