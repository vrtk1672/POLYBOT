from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.advisory_resolution_records_repository import AdvisoryResolutionRecordsRepository
from app.repositories.command_intent_records_repository import CommandIntentRecordsRepository
from app.repositories.orchestration_gate_records_repository import OrchestrationGateRecordsRepository
from app.repositories.orchestration_gate_runs_repository import OrchestrationGateRunsRepository
from app.repositories.orchestration_packets_repository import OrchestrationPacketsRepository


class ControlledOrchestrationQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = OrchestrationGateRunsRepository()
        self._records = OrchestrationGateRecordsRepository()
        self._packets = OrchestrationPacketsRepository()
        self._command_intents = CommandIntentRecordsRepository()
        self._resolutions = AdvisoryResolutionRecordsRepository()

    def get_orchestration_gate_run_summary(self, orchestration_gate_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, orchestration_gate_run_id)
            if run is None:
                return None
            gate_rows = self._records.list_for_run(conn, orchestration_gate_run_id)
            packets = self._packets.list_for_run(conn, orchestration_gate_run_id)

        decision_counts: dict[str, int] = {}
        for row in gate_rows:
            key = str(row["orchestration_decision_class"])
            decision_counts[key] = decision_counts.get(key, 0) + 1

        return {
            "run": dict(run),
            "gate_record_count": len(gate_rows),
            "packet_count": len(packets),
            "decision_counts": decision_counts,
        }

    def list_orchestration_gate_records_for_run(self, orchestration_gate_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_for_run(conn, orchestration_gate_run_id)
        return [dict(row) for row in rows]

    def get_orchestration_gate_record_details(
        self,
        *,
        orchestration_gate_record_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if orchestration_gate_record_id is not None:
                row = self._records.get_by_id(conn, orchestration_gate_record_id)
            elif market_id is not None:
                row = self._records.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("orchestration_gate_record_id or market_id is required")
        return dict(row) if row is not None else None

    def list_dry_run_ready_packets(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._packets.list_dry_run_ready(conn, limit)
        return [dict(row) for row in rows]

    def compare_orchestration_packet_to_upstream_context(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            gate_rows = self._records.list_for_market(conn, market_id)
            latest_gate = gate_rows[0] if gate_rows else None
            latest_run_id = str(latest_gate["orchestration_gate_run_id"]) if latest_gate is not None else None
            packets = self._packets.list_for_run(conn, latest_run_id) if latest_run_id is not None else []
            command_intents = self._command_intents.list_for_market(conn, market_id)
            latest_resolution = self._resolutions.get_latest_by_market(conn, market_id)

        if not gate_rows and not packets and not command_intents and latest_resolution is None:
            return None

        scoped_gate_rows = [
            dict(row) for row in gate_rows
            if latest_run_id is None or str(row["orchestration_gate_run_id"]) == latest_run_id
        ]
        return {
            "orchestration_gate_records": scoped_gate_rows,
            "orchestration_packets": [dict(row) for row in packets],
            "command_intent_records": [dict(row) for row in command_intents],
            "advisory_resolution_record": dict(latest_resolution) if latest_resolution is not None else None,
        }
