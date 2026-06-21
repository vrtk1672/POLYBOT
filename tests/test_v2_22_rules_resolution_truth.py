from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.data_foundation.market_registry import MarketRegistry
from app.data_foundation.market_rules_store import MarketRulesStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.rules_neuron.service import RulesNeuronService
from app.services.rules_resolution_truth import PRIORITY_MARKET_FAMILIES, RulesResolutionTruthService


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def _seed_market(
    market_id: str,
    *,
    question: str = "Will the election result be certified?",
    category: str = "politics",
    market_family: str = "POLITICS_MACRO",
    rules: str | None = "Resolves according to https://www.fec.gov/ before 2026-11-10T00:00:00Z.",
    resolution_source_url: str | None = "https://www.fec.gov/",
) -> None:
    registry = MarketRegistry()
    registry.upsert_market(
        registry.normalize_market(
            {
                "id": market_id,
                "question": question,
                "category": category,
                "market_family": market_family,
                "active": True,
                "clobTokenIds": ["yes", "no"],
                "endDate": "2026-11-10T00:00:00Z",
            }
        )
    )
    if rules is not None or resolution_source_url is not None:
        store = MarketRulesStore()
        store.upsert_rules(
            store.extract_rules(
                {
                    "description": rules,
                    "resolutionSourceUrl": resolution_source_url,
                    "endDate": "2026-11-10T00:00:00Z",
                },
                market_id=market_id,
            )
        )


def test_explicit_resolution_source_extraction(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(
        "explicit-source",
        rules="Resolve by official source.",
        resolution_source_url="https://www.fec.gov/",
    )

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT resolution_source_status, resolution_source_type, resolution_source_url, resolution_source_confidence FROM market_rules WHERE market_id=%s",
            ("explicit-source",),
        ).fetchone()

    assert row["resolution_source_status"] == "EXPLICIT"
    assert row["resolution_source_type"] == "EXPLICIT"
    assert row["resolution_source_url"] == "https://www.fec.gov/"
    assert float(row["resolution_source_confidence"]) >= 0.85


def test_rules_derived_resolution_source_extraction(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(
        "rules-derived-source",
        rules="This market will resolve to Yes. The resolution source for this market will be official information from the Federal Reserve.",
        resolution_source_url=None,
    )

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT resolution_source_status, resolution_source_type, resolution_source, resolution_source_evidence FROM market_rules WHERE market_id=%s",
            ("rules-derived-source",),
        ).fetchone()

    assert row["resolution_source_status"] == "RULES_DERIVED"
    assert row["resolution_source_type"] == "RULES_DERIVED"
    assert "Federal Reserve" in row["resolution_source"]
    assert "resolution source" in row["resolution_source_evidence"].lower()


def test_ambiguous_resolution_source_extraction_does_not_become_ok(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(
        "ambiguous-source",
        rules=(
            "This market will resolve to Yes. The resolution source for this market will be "
            "official information from the government, however a consensus of credible reporting will also suffice."
        ),
        resolution_source_url=None,
    )
    RulesNeuronService(connection_factory=DatabaseConnectionFactory()).analyze_market_rules(
        "ambiguous-source",
        log_no_trade_block=False,
    )

    with _client() as client:
        payload = client.get("/dashboard/api/v2/rules").json()
    by_market = {item["market_id"]: item for item in payload["markets"]}

    assert payload["mock_data"] is False
    assert by_market["ambiguous-source"]["resolution_source_status"] == "AMBIGUOUS"
    assert by_market["ambiguous-source"]["resolution_source_type"] == "AMBIGUOUS"
    assert by_market["ambiguous-source"]["hard_block"] is False
    assert payload["status"] == "DEGRADED"


def test_priority_market_families_are_officially_selected() -> None:
    assert PRIORITY_MARKET_FAMILIES == ("POLITICS_MACRO", "SPORTS")


def test_missing_rules_creates_warning_and_rules_no_trade_block(postgres_test_schema) -> None:
    run_migrations()
    _seed_market("rules-missing", rules=None, resolution_source_url=None)

    result = RulesNeuronService(connection_factory=DatabaseConnectionFactory()).analyze_market_rules(
        "rules-missing"
    )

    assert result.rules_text_present is False
    assert result.recommendation == "NO_TRADE"
    assert result.wording_risk >= 0.85
    with DatabaseConnectionFactory().connect() as conn:
        blocks = conn.execute(
            """
            SELECT block_type, severity
            FROM compliance_blocks
            WHERE market_id = %s AND active = true
            ORDER BY id DESC
            """,
            ("rules-missing",),
        ).fetchall()
        no_trade = conn.execute(
            """
            SELECT primary_reason, source_layer, insufficient_data, insufficient_data_reasons_json
            FROM no_trade_log
            WHERE market_id = %s AND source_layer = 'rules'
            ORDER BY id DESC
            LIMIT 1
            """,
            ("rules-missing",),
        ).fetchone()
    block_by_type = {block["block_type"]: block for block in blocks}
    assert block_by_type["MISSING_RULES"]["severity"] == "BLOCKING"
    assert no_trade["primary_reason"] == "bad_rules"
    assert no_trade["source_layer"] == "rules"
    assert no_trade["insufficient_data"] is True
    assert "missing_rules" in no_trade["insufficient_data_reasons_json"]


def test_missing_resolution_source_creates_warning_not_exception(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(
        "source-missing",
        rules="Resolves by final official certification before 2026-11-10T00:00:00Z.",
        resolution_source_url=None,
    )

    result = RulesNeuronService(connection_factory=DatabaseConnectionFactory()).analyze_market_rules(
        "source-missing",
        log_no_trade_block=False,
    )

    assert result.rules_text_present is True
    assert result.resolution_source_present is False
    assert result.source_verification_status in {"UNVERIFIED", "WARNING", "UNKNOWN"}
    assert result.recommendation in {"PENALIZE_HEAVILY", "REVIEW_REQUIRED", "NO_TRADE"}
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT resolution_source_status, resolution_source_hard_block FROM market_rules WHERE market_id=%s",
            ("source-missing",),
        ).fetchone()
    assert row["resolution_source_status"] == "MISSING"
    assert row["resolution_source_hard_block"] is False


def test_ambiguous_wording_sets_wording_risk(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(
        "ambiguous-wording",
        rules=(
            "Resolves according to https://www.fec.gov/ if the result is announced before "
            "end of day and final official confirmation is reported."
        ),
    )

    result = RulesNeuronService(connection_factory=DatabaseConnectionFactory()).analyze_market_rules(
        "ambiguous-wording",
        log_no_trade_block=False,
    )

    assert result.wording_risk > 0.40
    terms = {item["term"] for item in result.ambiguous_terms}
    assert {"announced", "reported"} <= terms


def test_dashboard_rules_endpoint_shows_real_rule_risk(postgres_test_schema) -> None:
    run_migrations()
    _seed_market("rules-dashboard-ok")
    _seed_market("rules-dashboard-risk", rules=None, resolution_source_url=None)
    service = RulesNeuronService(connection_factory=DatabaseConnectionFactory())
    service.analyze_market_rules("rules-dashboard-ok", log_no_trade_block=False)
    service.analyze_market_rules("rules-dashboard-risk")

    with _client() as client:
        response = client.get("/dashboard/api/v2/rules")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["selected_market_families"] == ["POLITICS_MACRO", "SPORTS"]
    assert payload["coverage"]["analyzed_markets"] >= 2
    by_market = {item["market_id"]: item for item in payload["markets"]}
    assert by_market["rules-dashboard-risk"]["no_trade_blocked"] is True
    assert by_market["rules-dashboard-risk"]["rules_text_present"] is False
    assert by_market["rules-dashboard-ok"]["rules_analysis_present"] is True
    assert "explicit_resolution_source_count" in payload["coverage"]
    assert "derived_resolution_source_count" in payload["coverage"]
    assert "ambiguous_resolution_source_count" in payload["coverage"]
    assert "missing_resolution_source_count" in payload["coverage"]


def test_rules_truth_refresh_is_idempotent_and_uses_test_db(postgres_test_schema) -> None:
    run_migrations()
    _seed_market(
        "refresh-politics",
        rules="This market will resolve to Yes. The resolution source for this market will be official information from the government.",
        resolution_source_url=None,
    )
    svc = RulesResolutionTruthService(connection_factory=DatabaseConnectionFactory())

    first = svc.refresh_rules_truth(limit=10, allow_ai=False)
    second = svc.refresh_rules_truth(limit=10, allow_ai=False)

    assert first["status"] == "OK"
    assert second["status"] == "OK"
    assert second["failed"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        db_name = conn.execute("SELECT current_database() AS db").fetchone()["db"]
        live_orders = conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]
        no_trade_rows = conn.execute("SELECT COUNT(*) AS count FROM no_trade_log WHERE source_layer='rules'").fetchone()["count"]
    assert db_name == "polybot_test"
    assert live_orders == 0
    assert no_trade_rows == 0
