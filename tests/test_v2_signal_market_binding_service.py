from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_market_binding import SignalMarketBindingRecoveryService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "signal_market_binding_candidates",
            "signal_market_binding_recovery_runs",
            "signal_suggested_market_links",
            "signal_link_coverage_analysis",
            "signal_market_links",
            "signal_position_links",
            "signal_processing_state_history",
            "signal_processing_states",
            "signal_quality_evaluations",
            "neuron_signal_bindings",
            "neuron_signals",
            "markets_v2",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")


def _market(
    market_id: str,
    *,
    yes_token_id: str | None = None,
    no_token_id: str | None = None,
    slug: str | None = None,
) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, question, slug, yes_token_id, no_token_id, active, closed)
            VALUES (%s, 'Binding test market?', %s, %s, NULL, true, false)
            """,
            (market_id, slug or market_id, yes_token_id),
        )
        if no_token_id:
            conn.execute("UPDATE markets_v2 SET no_token_id = %s WHERE market_id = %s", (no_token_id, market_id))


def _signal(
    signal_id: str,
    *,
    market_id: str | None = None,
    token_id: str | None = None,
    slug: str | None = None,
    status: str = "ACTIVE",
    generated_by: str = "runtime",
) -> None:
    evidence = {
        "generated_by": generated_by,
        "is_runtime_generated": generated_by == "runtime",
        "is_dry_run_generated": generated_by == "dry_run",
    }
    if token_id:
        evidence["details"] = {"sample_token_id": token_id}
    if slug:
        evidence["market_ref"] = slug
    NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id=signal_id,
            neuron="orderbook",
            event_type="source_status_observed",
            source_name="polymarket_clob_orderbook",
            market_id=market_id,
            confidence=0.8,
            strength=0.7,
            evidence=evidence,
            raw_payload_ref=f"source:{signal_id}",
            status=status,
        )
    )


def test_explicit_existing_market_id_creates_safe_link(postgres_test_schema) -> None:
    _prepare()
    _market("m-explicit")
    _signal("s-explicit", market_id="m-explicit")

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["safe_links_created"] == 1
    assert result["signal_market_links_after"] == result["signal_market_links_before"] + 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM signal_market_links WHERE signal_id='s-explicit'").fetchone()
    assert row["market_id"] == "m-explicit"
    assert row["link_method"] == "explicit_market_id"


def test_missing_market_id_remains_unlinked(postgres_test_schema) -> None:
    _prepare()
    _signal("s-missing", market_id=None)

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["safe_links_created"] == 0
    assert result["weak_evidence_skipped"] == 1


def test_unique_token_id_maps_to_market_and_auto_links(postgres_test_schema) -> None:
    _prepare()
    _market("m-token", yes_token_id="token-1")
    _signal("s-token", token_id="token-1")

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["safe_links_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM signal_market_links WHERE signal_id='s-token'").fetchone()
    assert row["market_id"] == "m-token"
    assert row["link_method"] == "unique_token_id"


def test_ambiguous_token_match_does_not_auto_link(postgres_test_schema) -> None:
    _prepare()
    _market("m-ambiguous-1", yes_token_id="ambiguous-token")
    _market("m-ambiguous-2", no_token_id="ambiguous-token")
    _signal("s-ambiguous", token_id="ambiguous-token")

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["safe_links_created"] == 0
    assert result["ambiguous_candidates"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links").fetchone()["count"]
        candidate = conn.execute("SELECT * FROM signal_market_binding_candidates WHERE signal_id='s-ambiguous'").fetchone()
    assert links == 0
    assert candidate["action"] == "BLOCKED_AMBIGUOUS"


def test_exact_slug_match_can_create_safe_link(postgres_test_schema) -> None:
    _prepare()
    _market("m-slug", slug="exact-slug")
    _signal("s-slug", slug="exact-slug")

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["safe_links_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM signal_market_links WHERE signal_id='s-slug'").fetchone()
    assert row["market_id"] == "m-slug"
    assert row["link_method"] == "exact_slug"


def test_apply_safe_links_false_creates_suggestion_not_link(postgres_test_schema) -> None:
    _prepare()
    _market("m-review")
    _signal("s-review", market_id="m-review")

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=False, create_suggestions=True)

    assert result["safe_links_created"] == 0
    assert result["suggestions_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links").fetchone()["count"]
        suggestions = conn.execute("SELECT COUNT(*) AS count FROM signal_suggested_market_links").fetchone()["count"]
    assert links == 0
    assert suggestions == 1


def test_stale_signal_is_skipped(postgres_test_schema) -> None:
    _prepare()
    _market("m-stale")
    _signal("s-stale", market_id="m-stale", status="STALE")

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["safe_links_created"] == 0
    assert result["stale_skipped"] == 1


def test_dry_run_signal_is_skipped_by_default(postgres_test_schema) -> None:
    _prepare()
    _market("m-dry-run")
    _signal("s-dry-run", market_id="m-dry-run", generated_by="dry_run")

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["safe_links_created"] == 0
    assert result["dry_run_skipped"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links").fetchone()["count"]
    assert links == 0
