from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.link_coverage import LinkCoverageService
from app.services.neuron_signals import NeuronSignalService


def _prepare() -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM event_entities")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM markets_v2")


def _signal(*, signal_id: str, market_id: str | None = None, source_name: str | None = "rules_resolution_truth") -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id=signal_id,
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name=source_name,
            status="ACTIVE",
            market_id=market_id,
            confidence=0.8,
            strength=0.7,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:test",
        )
    )


def _market(market_id: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, question, slug)
            VALUES (%s, 'Will test market resolve yes?', %s)
            ON CONFLICT (market_id) DO NOTHING
            """,
            (market_id, f"slug-{market_id}"),
        )


def test_suggested_links_are_stored_separately_from_actual_links(postgres_test_schema) -> None:
    _prepare()
    signal = _signal(signal_id="coverage-explicit", market_id="market-explicit")
    _market("market-explicit")

    result = LinkCoverageService().analyze_signal(str(signal["signal_id"]), create_suggestions=True, apply_safe_links=False)

    assert result is not None
    assert result["suggested_link_action"] == "SAFE_TO_LINK_EXISTING_MARKET_ID"
    with DatabaseConnectionFactory().connect() as conn:
        suggestions = conn.execute("SELECT COUNT(*) AS count FROM signal_suggested_market_links").fetchone()["count"]
        actual_links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links").fetchone()["count"]
    assert suggestions == 1
    assert actual_links == 0


def test_apply_safe_links_false_never_mutates_signal_market_links(postgres_test_schema) -> None:
    _prepare()
    signal = _signal(signal_id="coverage-no-apply", market_id="market-no-apply")
    _market("market-no-apply")

    LinkCoverageService().analyze_recent_signals(limit=10, create_suggestions=True, apply_safe_links=False)

    with DatabaseConnectionFactory().connect() as conn:
        actual_links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links WHERE signal_id = %s", (signal["signal_id"],)).fetchone()["count"]
    assert actual_links == 0


def test_apply_safe_links_true_only_applies_explicit_existing_market_id(postgres_test_schema) -> None:
    _prepare()
    signal = _signal(signal_id="coverage-apply", market_id="market-apply")
    _market("market-apply")

    result = LinkCoverageService().analyze_signal(str(signal["signal_id"]), create_suggestions=True, apply_safe_links=True)

    assert result is not None
    assert result["applied_link"] is True
    with DatabaseConnectionFactory().connect() as conn:
        actual_links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links WHERE signal_id = %s", (signal["signal_id"],)).fetchone()["count"]
    assert actual_links == 1


def test_missing_source_and_entity_are_detected(postgres_test_schema) -> None:
    _prepare()
    signal = _signal(signal_id="coverage-missing-source", market_id=None, source_name=None)

    result = LinkCoverageService().analyze_signal(str(signal["signal_id"]))

    assert result is not None
    assert "MISSING_SOURCE" in result["missing_fields"]
    assert "MISSING_ENTITY" in result["unlinked_reasons"]
