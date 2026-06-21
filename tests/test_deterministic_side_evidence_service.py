from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.side_evidence import DeterministicSideEvidenceService
from app.services.system_power import SystemPowerService

from paper_eligibility_fixtures import table_exists


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "side_evidence_recovery_runs",
            "paper_eligibility_candidates",
            "signal_market_links",
            "neuron_signal_bindings",
            "neuron_signals",
            "markets_v2",
            "paper_intents",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "orders_v2",
            "fills_v2",
            "positions",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="side_evidence_prepare")


def _seed_link(
    suffix: str,
    *,
    market_id: str = "market-side",
    token_id: str | None,
    yes_token: str = "yes-token",
    no_token: str = "no-token",
    confidence: float = 0.95,
    status: str = "confirmed",
    review_required: bool = False,
    evidence_extra: dict | None = None,
) -> str:
    signal_id = f"signal-side-{suffix}"
    evidence = evidence_extra if evidence_extra is not None else {"details": {"sample_token_id": token_id}}
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, yes_token_id, no_token_id,
                outcome_tokens_json, active, closed, accepting_orders
            )
            VALUES (%s, %s, 'Side market?', %s, %s, %s, %s, true, false, true)
            ON CONFLICT (market_id) DO UPDATE
            SET yes_token_id = EXCLUDED.yes_token_id,
                no_token_id = EXCLUDED.no_token_id,
                outcome_tokens_json = EXCLUDED.outcome_tokens_json
            """,
            (market_id, f"condition-{suffix}", market_id, yes_token, no_token, Jsonb({"yes": yes_token, "no": no_token})),
        )
        conn.execute(
            """
            INSERT INTO neuron_signals (
                signal_id, neuron, event_type, source_name, market_id, confidence,
                strength, evidence_json, status, raw_payload_ref, created_at, updated_at
            )
            VALUES (%s, 'orderbook', 'source_status_observed', 'polymarket_clob_orderbook',
                    %s, 0.95, 0.8, %s, 'ACTIVE', %s, now(), now())
            """,
            (signal_id, market_id, Jsonb(evidence), f"raw-{suffix}"),
        )
        conn.execute(
            """
            INSERT INTO neuron_signal_bindings (
                signal_id, neuron_name, producer_name, source_name, market_id,
                generated_from, lineage_json, raw_payload_ref
            )
            VALUES (%s, 'orderbook', 'clob_source_status_adapter', 'polymarket_clob_orderbook',
                    %s, 'source_status', %s, %s)
            """,
            (signal_id, market_id, Jsonb({"generated_by": "runtime", "is_runtime_generated": True}), f"binding-{suffix}"),
        )
        conn.execute(
            """
            INSERT INTO signal_market_links (
                signal_id, market_id, link_type, link_status, confidence, reason,
                created_by, link_confidence, link_reason, link_evidence_json,
                link_method, linked_by, is_auto_linked, is_review_required,
                is_runtime_link, source_signal_id
            )
            VALUES (%s, %s, 'explicit_market_id', %s, %s, 'test',
                    'test', %s, 'test', %s, 'explicit_market_id', 'test',
                    true, %s, true, %s)
            """,
            (signal_id, market_id, status, confidence, confidence, Jsonb({}), review_required, signal_id),
        )
    return signal_id


def test_system_off_blocks_side_recovery(postgres_test_schema) -> None:
    _prepare()
    _seed_link("off", token_id="yes-token")
    SystemPowerService().turn_off(actor="test", reason="side_off")

    result = DeterministicSideEvidenceService().run_recovery(cycle_id="side-off", limit=10)

    assert result["status"] == "BLOCKED"
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM signal_market_links WHERE matched_side IS NOT NULL").fetchone()["count"] == 0


def test_token_id_equal_yes_token_persists_matched_side_yes(postgres_test_schema) -> None:
    _prepare()
    signal_id = _seed_link("yes", token_id="yes-token")

    result = DeterministicSideEvidenceService().run_recovery(cycle_id="side-yes", limit=10)

    assert result["status"] == "OK"
    assert result["sides_recovered"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        link = conn.execute("SELECT matched_side, side_source, side_source_id, link_evidence_json FROM signal_market_links WHERE signal_id = %s", (signal_id,)).fetchone()
        binding = conn.execute("SELECT matched_side FROM neuron_signal_bindings WHERE signal_id = %s", (signal_id,)).fetchone()
    assert link["matched_side"] == "YES"
    assert link["side_source"] == "token_id"
    assert link["side_source_id"] == "yes-token"
    assert link["link_evidence_json"]["matched_side"] == "YES"
    assert binding["matched_side"] == "YES"


def test_token_id_equal_no_token_persists_matched_side_no(postgres_test_schema) -> None:
    _prepare()
    signal_id = _seed_link("no", token_id="no-token")

    DeterministicSideEvidenceService().run_recovery(cycle_id="side-no", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT matched_side FROM signal_market_links WHERE signal_id = %s", (signal_id,)).fetchone()["matched_side"] == "NO"


def test_ambiguous_and_missing_token_mapping_do_not_recover_side(postgres_test_schema) -> None:
    _prepare()
    ambiguous_signal = _seed_link("ambiguous", market_id="market-ambiguous", token_id=None, evidence_extra={"details": {"token_ids": ["yes-token", "no-token"]}})
    missing_signal = _seed_link("missing-map", market_id="market-missing-map", token_id="yes-token", yes_token=None, no_token="no-token")

    result = DeterministicSideEvidenceService().run_recovery(cycle_id="side-rejects", limit=10)

    assert result["sides_recovered"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, side_rejected_reason FROM signal_market_links WHERE signal_id IN (%s, %s)",
            (ambiguous_signal, missing_signal),
        ).fetchall()
    reasons = {row["signal_id"]: row["side_rejected_reason"] for row in rows}
    assert reasons[ambiguous_signal] == "AMBIGUOUS_TOKEN_SIDE"
    assert reasons[missing_signal] == "MISSING_TOKEN_MAPPING"


def test_weak_stale_or_text_only_evidence_does_not_recover_side(postgres_test_schema) -> None:
    _prepare()
    weak_signal = _seed_link("weak", token_id="yes-token", confidence=0.4)
    text_signal = _seed_link("text", token_id=None, evidence_extra={"details": {"title_sentiment": "positive means yes"}})

    DeterministicSideEvidenceService().run_recovery(cycle_id="side-weak-text", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, matched_side, side_rejected_reason FROM signal_market_links WHERE signal_id IN (%s, %s)",
            (weak_signal, text_signal),
        ).fetchall()
    by_signal = {row["signal_id"]: row for row in rows}
    assert by_signal[weak_signal]["matched_side"] is None
    assert by_signal[text_signal]["matched_side"] is None
    assert by_signal[text_signal]["side_rejected_reason"] == "MISSING_TOKEN_EVIDENCE"


def test_candidate_side_propagates_only_with_trusted_lineage(postgres_test_schema) -> None:
    _prepare()
    signal_id = _seed_link("candidate", token_id="yes-token")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                coordinator_decision_id, brain_output_ids, signal_ids, market_id,
                side, status, eligibility_score, eligibility_blockers,
                missing_requirements, evidence, lineage_trusted, risk_approved,
                exit_ready, not_dry_run, paper_intent_allowed,
                execution_allowed, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                'candidate-side', 'thesis-side', 'risk-side', 'exit-side',
                'coord-side', '[]'::jsonb, %s, 'market-side', NULL,
                'BLOCKED', 0.0, '["MISSING_SIDE"]'::jsonb,
                '["MISSING_SIDE"]'::jsonb, '{}'::jsonb, true, false,
                false, true, false, false, 'runtime', 'test', true, false
            )
            """,
            (Jsonb([signal_id]),),
        )

    DeterministicSideEvidenceService().run_recovery(cycle_id="side-candidate", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        candidate = conn.execute("SELECT side, evidence FROM paper_eligibility_candidates WHERE eligibility_id='candidate-side'").fetchone()
    assert candidate["side"] == "YES"
    assert candidate["evidence"]["side_recovery"]["source_component"] == "side_evidence_recovery"
