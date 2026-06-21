from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService
from app.services.neuron_intelligence import NeuronIntelligenceService
from app.services.system_power import SystemPowerService
from app.services.trusted_orderbook import TrustedOrderbookEvidenceService

from test_trusted_orderbook_evidence_service import _prepare, _seed_candidate


def _prepare_pack() -> dict[str, object]:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "neuron_intelligence_evidence",
            "neuron_intelligence_runs",
            "brain_dialogue_events",
            "rules_analysis",
            "market_rules",
            "fee_snapshots",
            "news_impact_scores",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
    ids = _seed_candidate("pack1")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE markets_v2
            SET close_time = %s
            WHERE market_id = %s
            """,
            (datetime.now(UTC) + timedelta(hours=3), ids["market_id"]),
        )
    TrustedOrderbookEvidenceService().resolve(cycle_id="pack-trusted", limit=10)
    return ids


def _seed_pack_sources(market_id: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO market_rules (
                market_id, rules_text, resolution_source, settlement_method,
                deadline_at, ambiguity_flags_json, updated_at
            )
            VALUES (
                %s, 'This market resolves according to the official source.',
                'official_source', 'oracle', %s, '[]'::jsonb, now()
            )
            ON CONFLICT (market_id) DO UPDATE
            SET rules_text = EXCLUDED.rules_text,
                resolution_source = EXCLUDED.resolution_source,
                updated_at = now()
            """,
            (market_id, datetime.now(UTC) + timedelta(hours=3)),
        )
        conn.execute(
            """
            INSERT INTO rules_analysis (
                rules_analysis_id, market_id, rules_text_present,
                resolution_source_present, deadline_present, settlement_method,
                ambiguous_terms_json, edge_cases_json, dangerous_edge_cases_json,
                wording_risk, dispute_risk, resolution_clarity,
                source_verification_status, jurisdiction_status,
                compliance_status, recommendation, metadata_json
            )
            VALUES (
                'rules-pack1', %s, true, true, true, 'oracle',
                '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                0.12, 0.05, 0.91,
                'VERIFIED', 'CLEAR', 'CLEAR', 'TRADE_ALLOWED', '{}'::jsonb
            )
            """,
            (market_id,),
        )
        conn.execute(
            """
            INSERT INTO fee_snapshots (
                fee_snapshot_id, market_id, maker_fee, taker_fee,
                spread_cost, estimated_slippage_cost, reward_pool, snapshot_at
            )
            VALUES ('fee-pack1', %s, 0.001, 0.001, 0.002, 0.001, 0, now())
            """,
            (market_id,),
        )
        conn.execute(
            """
            INSERT INTO news_impact_scores (
                impact_id, news_event_id, market_id, direction, strength,
                confidence, urgency, already_priced_in, ttl_seconds,
                source_reliability, reason, signal_json
            )
            VALUES (
                'impact-pack1', 'news-pack1', %s, 'YES', 0.80,
                0.75, 0.5, 0.1, 3600, 0.90, 'source-backed test impact',
                '{}'::jsonb
            )
            """,
            (market_id,),
        )


def _evidence_rows() -> list[dict[str, object]]:
    with DatabaseConnectionFactory().connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM neuron_intelligence_evidence ORDER BY neuron_name"
            ).fetchall()
        ]


def test_system_off_blocks_neuron_intelligence(postgres_test_schema) -> None:
    _prepare_pack()
    SystemPowerService().turn_off(actor="test", reason="neuron_pack_off")

    result = NeuronIntelligenceService().run_pack(cycle_id="pack-off", limit=10)

    assert result["status"] == "SYSTEM_POWER_OFF"
    assert _evidence_rows() == []


def test_pack_creates_all_five_source_backed_neuron_outputs(postgres_test_schema) -> None:
    ids = _prepare_pack()
    _seed_pack_sources(str(ids["market_id"]))

    result = NeuronIntelligenceService().run_pack(cycle_id="pack-on", limit=10)

    assert result["status"] == "OK"
    assert result["rules_evidence_count"] == 1
    assert result["liquidity_evidence_count"] == 1
    assert result["fees_evidence_count"] == 1
    assert result["time_evidence_count"] == 1
    assert result["news_evidence_count"] == 1
    rows = _evidence_rows()
    assert {row["neuron_name"] for row in rows} == {
        "Rules / Wording Neuron",
        "Liquidity Neuron",
        "Fees / Rewards Neuron",
        "Time Neuron",
        "News Neuron",
    }
    assert all(row["source_table"] for row in rows)
    assert all(row["human_message"] for row in rows)


def test_rules_neuron_blocks_missing_rules_analysis_without_faking_score(postgres_test_schema) -> None:
    _prepare_pack()

    NeuronIntelligenceService().run_pack(cycle_id="pack-rules-missing", limit=10)

    row = next(item for item in _evidence_rows() if item["neuron_name"] == "Rules / Wording Neuron")
    assert row["status"] == "BLOCKED"
    assert row["decision"] == "LOW_CONFIDENCE"
    assert "MISSING_RULES_ANALYSIS" in row["blockers_json"]


def test_liquidity_neuron_flags_low_depth_from_trusted_orderbook_source(postgres_test_schema) -> None:
    ids = _prepare_pack()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            "UPDATE orderbook_snapshots SET liquidity_score = 0.10 WHERE market_id = %s",
            (ids["market_id"],),
        )

    NeuronIntelligenceService().run_pack(cycle_id="pack-low-depth", limit=10)

    row = next(item for item in _evidence_rows() if item["neuron_name"] == "Liquidity Neuron")
    assert row["decision"] == "LOW_DEPTH"
    assert row["source_table"] == "orderbook_snapshots"


def test_news_neuron_stays_unverified_without_source_backed_news(postgres_test_schema) -> None:
    _prepare_pack()

    NeuronIntelligenceService().run_pack(cycle_id="pack-news-missing", limit=10)

    row = next(item for item in _evidence_rows() if item["neuron_name"] == "News Neuron")
    assert row["status"] == "BLOCKED"
    assert row["decision"] == "UNVERIFIED"
    assert "NO_NEWS_EVIDENCE" in row["blockers_json"]


def test_brain_dialogue_materializes_pack1_neuron_messages_without_duplicates(postgres_test_schema) -> None:
    ids = _prepare_pack()
    _seed_pack_sources(str(ids["market_id"]))
    NeuronIntelligenceService().run_pack(cycle_id="pack-dialogue", limit=10)

    first = BrainDialogueService().materialize_recent(limit_per_source=20)
    second = BrainDialogueService().materialize_recent(limit_per_source=20)

    assert first["status"] == "OK"
    assert second["status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM brain_dialogue_events
            WHERE source_table = 'neuron_intelligence_evidence'
            """
        ).fetchone()["count"]
        components = {
            row["component"]
            for row in conn.execute(
                """
                SELECT component
                FROM brain_dialogue_events
                WHERE source_table = 'neuron_intelligence_evidence'
                """
            ).fetchall()
        }
    assert count == 5
    assert "Rules / Wording Neuron" in components
    assert "News Neuron" in components


def test_neuron_pack_does_not_create_trading_artifacts(postgres_test_schema) -> None:
    ids = _prepare_pack()
    _seed_pack_sources(str(ids["market_id"]))
    with DatabaseConnectionFactory().connect() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_orders", "paper_fills", "paper_positions")
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
        }

    NeuronIntelligenceService().run_pack(cycle_id="pack-safety", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in before
        }
    assert after == before
