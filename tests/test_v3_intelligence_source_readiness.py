from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.intelligence_sources.catalog import PROVIDER_CATALOG
from app.intelligence_sources.service import IntelligenceSourceReadinessService
from app.main import create_app
from app.stage4.config import Stage4Settings


def _prepare() -> None:
    run_migrations()


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
        if not exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) AS count FROM " + table).fetchone()["count"] or 0)


def _clear_provider_env(monkeypatch) -> None:
    for source in PROVIDER_CATALOG:
        for env_var in (*source.required_env_vars, *source.optional_env_vars):
            monkeypatch.delenv(env_var, raising=False)


def test_registry_loads(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)

    summary = IntelligenceSourceReadinessService().dashboard_summary()

    assert summary["mock_data"] is False
    assert summary["total_sources"] >= 15
    assert _count("intelligence_source_registry") >= 15


def test_missing_credentials_reported(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)

    report = IntelligenceSourceReadinessService().requirements_report()
    missing = set(report["missing_requirements"][idx]["env_var"] for idx in range(len(report["missing_requirements"])))

    assert "NEWS_API_KEY" in missing
    assert "X_BEARER_TOKEN" in missing
    assert "OPENAI_API_KEY" in missing
    assert "POLYMARKET_CLOB_API_KEY" in missing


def test_secrets_not_exposed(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("NEWS_API_KEY", "super-secret-news-key")
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-openai-key")

    payload = IntelligenceSourceReadinessService().validate_endpoint()
    serialized = json.dumps(payload, sort_keys=True, default=str)

    assert "super-secret-news-key" not in serialized
    assert "super-secret-openai-key" not in serialized
    assert payload["secrets_exposed"] is False


def test_mock_provider_health_works(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)

    payload = IntelligenceSourceReadinessService().health_report()
    mock = next(item for item in payload["health"] if item["source_id"] == "mock_intelligence_provider")

    assert mock["health_status"] == "READY_NO_KEY"
    assert mock["metadata"]["production_intelligence"] is False


def test_rss_provider_registered_without_key(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)

    payload = IntelligenceSourceReadinessService().validate_endpoint()
    rss = next(item for item in payload["providers"] if item["source_id"] == "news_rss_public")

    assert rss["credential_status"] == "NOT_REQUIRED"
    assert rss["readiness_status"] == "READY_NO_KEY"
    assert rss["neural_event_type"] == "NEWS_DETECTED"


def test_official_v37_env_names_are_recognized(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)
    env = {
        "POLYMARKET_CLOB_API_KEY": "key",
        "POLYMARKET_CLOB_SECRET": "secret",
        "POLYMARKET_CLOB_PASSPHRASE": "passphrase",
        "POLYMARKET_CLOB_HOST": "https://clob.polymarket.com",
        "REDDIT_CLIENT_ID": "reddit-id",
        "REDDIT_CLIENT_SECRET": "reddit-secret",
        "REDDIT_USER_AGENT": "polybot-test/0.1",
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "telegram-hash",
        "TELEGRAM_BOT_TOKEN": "telegram-token",
        "TELEGRAM_CHANNELS": "channel-a,channel-b",
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_CHANNELS": "channel-1",
    }

    providers = IntelligenceSourceReadinessService(env=env).validate_endpoint()["providers"]
    clob = next(item for item in providers if item["source_id"] == "polymarket_clob_authenticated_readonly")
    reddit = next(item for item in providers if item["source_id"] == "reddit_api")
    telegram = next(item for item in providers if item["source_id"] == "telegram_public_channels")
    discord = next(item for item in providers if item["source_id"] == "discord_optional")
    stage4 = Stage4Settings(_env_file=None, **env)

    assert clob["credential_status"] == "CREDENTIALS_PRESENT"
    assert reddit["credential_status"] == "CREDENTIALS_PRESENT"
    assert telegram["credential_status"] == "CREDENTIALS_PRESENT"
    assert "REDDIT_USER_AGENT" not in reddit["missing_optional_env_vars"]
    assert "TELEGRAM_CHANNELS" not in telegram["missing_optional_env_vars"]
    assert "DISCORD_CHANNELS" not in discord["missing_optional_env_vars"]
    assert stage4.poly_api_key == "key"
    assert stage4.poly_api_secret == "secret"
    assert stage4.poly_api_passphrase == "passphrase"
    assert stage4.poly_clob_host == "https://clob.polymarket.com"


def test_dashboard_returns_mock_data_false(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/intelligence-sources")

    assert response.status_code == 200
    assert response.json()["mock_data"] is False


def test_validate_endpoint_reports_missing_and_available_safely(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("NEWS_API_KEY", "present-news-key")
    client = TestClient(create_app())

    response = client.post("/intelligence-sources/validate")
    payload = response.json()
    serialized = json.dumps(payload, sort_keys=True, default=str)

    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "NEWS_API_KEY" not in payload["missing_env_vars"]
    assert "X_BEARER_TOKEN" in payload["missing_env_vars"]
    assert "present-news-key" not in serialized


def test_neural_bus_event_mapping_exists(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)

    providers = IntelligenceSourceReadinessService().validate_endpoint()["providers"]
    mappings = {item["neural_event_type"] for item in providers}

    assert {"NEWS_DETECTED", "WHALE_DETECTED", "SOCIAL_SPIKE", "AI_CONTEXT_UPDATED", "MEMORY_UPDATED"} <= mappings


def test_shared_awareness_domain_mapping_exists(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)

    providers = IntelligenceSourceReadinessService().validate_endpoint()["providers"]
    mappings = {item["awareness_domain"] for item in providers}

    assert {"NEWS", "WHALE", "SOCIAL", "CANDIDATE", "MEMORY"} <= mappings


def test_no_trading_mutation(postgres_test_schema, monkeypatch) -> None:
    _prepare()
    _clear_provider_env(monkeypatch)
    before = {
        "live_orders": _count("live_orders"),
        "paper_orders": _count("paper_orders"),
        "paper_fills": _count("paper_fills"),
        "paper_positions": _count("paper_positions"),
        "paper_intents": _count("paper_intents"),
        "paper_capital_ledger": _count("paper_capital_ledger"),
        "risk_decisions": _count("risk_decisions"),
        "exit_plans": _count("exit_plans"),
        "coordinator_decisions": _count("coordinator_decisions"),
        "brain_outputs": _count("brain_outputs"),
    }

    IntelligenceSourceReadinessService().validate_endpoint()

    assert {table: _count(table) for table in before} == before
