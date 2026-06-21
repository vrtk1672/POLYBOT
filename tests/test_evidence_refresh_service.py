from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.evidence_refresh import EvidenceRefreshService
from app.services.neuron_signals import NeuronSignalService


class _Power:
    def __init__(self, on: bool) -> None:
        self.on = on

    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON" if self.on else "OFF", "runtime_work_allowed": self.on}


class _Governor:
    def can_execute(self, action) -> bool:
        return True


class _Orderbooks:
    def __init__(self) -> None:
        self.called = False
        self.market_ids: list[str] | None = None

    def collect_snapshots(self, **kwargs) -> dict[str, object]:
        self.called = True
        self.market_ids = kwargs.get("market_ids")
        return {"run_id": "ob-run", "markets_checked": len(self.market_ids or []), "snapshots_created": 2, "ok_snapshots": 2, "error_count": 0}


class _Bindings:
    def __init__(self) -> None:
        self.called = False

    def recover_market_bindings(self, **kwargs) -> dict[str, object]:
        self.called = True
        return {"run_id": "binding-run", "signals_checked": 3, "safe_links_created": 1, "already_linked": 0, "remained_unlinked": 2}


def _seed_market_and_signal() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, question, slug, yes_token_id, no_token_id, active, closed, accepting_orders)
            VALUES ('m-evidence', 'Evidence market?', 'm-evidence', 'yes-token', 'no-token', true, false, true)
            ON CONFLICT (market_id) DO UPDATE SET active=true, closed=false, accepting_orders=true
            """
        )
        conn.execute(
            """
            INSERT INTO coordinator_decisions (
                coordinator_decision_id, market_id, final_state, primary_reason, confidence,
                execution_allowed, status, metadata_json, created_at, updated_at
            )
            VALUES (
                'coord-evidence', 'm-evidence', 'NO_TRADE', 'test', 0.5,
                false, 'ACTIVE', '{"generated_by":"runtime","producer_name":"runtime_coordinator_adapter","is_runtime_generated":true,"is_dry_run_generated":false}'::jsonb,
                now(), now()
            )
            ON CONFLICT (coordinator_decision_id) DO NOTHING
            """
        )


def test_system_off_prevents_evidence_refresh(postgres_test_schema) -> None:
    run_migrations()
    orderbooks = _Orderbooks()
    bindings = _Bindings()
    service = EvidenceRefreshService(system_power=_Power(False), governor=_Governor(), orderbook_service=orderbooks, binding_service=bindings)

    result = service.run_refresh(cycle_id="off-cycle")

    assert result["status"] == "BLOCKED"
    assert result["blocked_reason"] == "SYSTEM_POWER_OFF"
    assert orderbooks.called is False
    assert bindings.called is False


def test_system_on_refreshes_orderbooks_bindings_and_records_summary(postgres_test_schema) -> None:
    run_migrations()
    _seed_market_and_signal()
    orderbooks = _Orderbooks()
    bindings = _Bindings()
    service = EvidenceRefreshService(system_power=_Power(True), governor=_Governor(), orderbook_service=orderbooks, binding_service=bindings)

    result = service.run_refresh(cycle_id="on-cycle", limit=10)

    assert result["status"] == "OK"
    assert orderbooks.called is True
    assert orderbooks.market_ids == ["m-evidence"]
    assert bindings.called is True
    assert result["orderbook_snapshots_created"] == 2
    assert result["bindings_created"] == 1
    assert result["bindings_rejected"] == 2
    assert result["orders_delta"] == 0
    assert result["fills_delta"] == 0
    assert result["positions_delta"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM evidence_refresh_runs WHERE cycle_id='on-cycle'").fetchone()
    assert row is not None
    assert row["status"] == "OK"


def test_side_recovery_requires_trusted_matched_side(postgres_test_schema) -> None:
    run_migrations()
    NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="signal-side",
            neuron="orderbook",
            event_type="source_status_observed",
            source_name="polymarket_clob_orderbook",
            market_id="m-side",
            confidence=0.9,
            strength=0.9,
            evidence={"generated_by": "runtime", "is_runtime_generated": True},
            raw_payload_ref="test:signal-side",
            status="ACTIVE",
        )
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO thesis_profiles (
                thesis_id, market_id, side, status, thesis_type, why_now, expected_move,
                confidence, evidence, missing_evidence, invalidation_rules, risk_notes,
                source_signal_ids, generated_by, producer_name, is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                'thesis-side', 'm-side', NULL, 'INCOMPLETE', 'HOLD_FOR_MORE_EVIDENCE', 'test', 'UNKNOWN',
                0.5, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                '["signal-side"]'::jsonb, 'runtime', 'thesis_profile_builder', true, false
            )
            """
        )
        conn.execute(
            """
            INSERT INTO signal_market_links (
                signal_id, market_id, link_type, link_status, confidence, reason,
                link_confidence, link_reason, link_evidence_json, link_method,
                created_by, linked_by, is_auto_linked, is_review_required, is_runtime_link, source_signal_id
            )
            VALUES (
                'signal-side', 'm-side', 'unique_token_id', 'confirmed', 0.9, 'token',
                0.9, 'token', %s, 'unique_token_id',
                'test', 'test', true, false, true, 'signal-side'
            )
            """,
            (Jsonb({"matched_side": "YES"}),),
        )
    service = EvidenceRefreshService(system_power=_Power(True), governor=_Governor(), orderbook_service=_Orderbooks(), binding_service=_Bindings())

    result = service.run_refresh(cycle_id="side-cycle", limit=10)

    assert result["sides_recovered"] >= 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT side FROM thesis_profiles WHERE thesis_id='thesis-side'").fetchone()
    assert row["side"] == "YES"


def test_side_recovery_does_not_default_without_matched_side(postgres_test_schema) -> None:
    run_migrations()
    NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="signal-no-side",
            neuron="orderbook",
            event_type="source_status_observed",
            source_name="polymarket_clob_orderbook",
            market_id="m-no-side",
            confidence=0.9,
            strength=0.9,
            evidence={"generated_by": "runtime", "is_runtime_generated": True},
            raw_payload_ref="test:signal-no-side",
            status="ACTIVE",
        )
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO thesis_profiles (
                thesis_id, market_id, side, status, thesis_type, why_now, expected_move,
                confidence, evidence, missing_evidence, invalidation_rules, risk_notes,
                source_signal_ids, generated_by, producer_name, is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                'thesis-no-side', 'm-no-side', NULL, 'INCOMPLETE', 'HOLD_FOR_MORE_EVIDENCE', 'test', 'UNKNOWN',
                0.5, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                '["signal-no-side"]'::jsonb, 'runtime', 'thesis_profile_builder', true, false
            )
            """
        )
    service = EvidenceRefreshService(system_power=_Power(True), governor=_Governor(), orderbook_service=_Orderbooks(), binding_service=_Bindings())

    service.run_refresh(cycle_id="no-side-cycle", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT side FROM thesis_profiles WHERE thesis_id='thesis-no-side'").fetchone()
    assert row["side"] is None
