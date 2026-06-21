from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.brains.brain_errors import BrainAnalysisBlocked
from app.brains.capital_brain import CapitalBrain
from app.brains.capital_input_builder import CapitalInputBuilder
from app.brains.context_brain import ContextBrain
from app.brains.context_input_builder import ContextInputBuilder
from app.brains.contracts import BrainCombinedSnapshot, CapitalBrainOutput, ContextBrainOutput
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.capital_brain_output_repository import CapitalBrainOutputRepository
from app.repositories.capital_brain_run_repository import CapitalBrainRunRepository
from app.repositories.context_brain_output_repository import ContextBrainOutputRepository
from app.repositories.context_brain_run_repository import ContextBrainRunRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class BrainService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, state_governor: StateGovernor | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.context_input_builder = ContextInputBuilder()
        self.capital_input_builder = CapitalInputBuilder()
        self.context_brain = ContextBrain()
        self.capital_brain = CapitalBrain()
        self.context_run_repo = ContextBrainRunRepository()
        self.context_output_repo = ContextBrainOutputRepository()
        self.capital_run_repo = CapitalBrainRunRepository()
        self.capital_output_repo = CapitalBrainOutputRepository()

    def analyze_context(self, market_id: str, *, dry_run: bool = False, manual_input: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_allowed()
        if not self._factory.enabled:
            output = ContextBrainOutput(market_id=market_id, insufficient_data=True, insufficient_data_reasons=["database_disabled"])
            return {"dry_run": dry_run, "written": False, "output": output.model_dump(mode="json")}
        run_id = f"context_{uuid4().hex}"
        with self._factory.connect() as conn:
            payload = self.context_input_builder.build(conn, market_id, manual_input)
            output = self.context_brain.analyze(payload)
            if dry_run:
                return {"dry_run": True, "written": False, "run_id": run_id, "output": output.model_dump(mode="json")}
            with conn.transaction():
                self.context_run_repo.insert_started(
                    conn,
                    run_id=run_id,
                    market_id=market_id,
                    market_family=payload.market_family,
                    runtime_mode=self._runtime_mode(),
                    input_sources=_context_sources(payload),
                    input_completeness_score=payload.data_completeness_score,
                    memory_confidence=float(payload.memory_snapshot.get("confidence") or 0),
                    ai_used=payload.ai_analysis is not None,
                    ai_request_id=(payload.ai_analysis or {}).get("ai_request_id") if payload.ai_analysis else None,
                )
                self.context_output_repo.insert(conn, run_id, payload.market_family, output, payload.memory_snapshot)
                self.context_run_repo.finish(conn, run_id)
            conn.commit()
        self._publish_context(run_id, output)
        return {"dry_run": False, "written": True, "run_id": run_id, "output": output.model_dump(mode="json")}

    def analyze_capital(self, *, market_id: str | None = None, candidate_engine: str | None = None, dry_run: bool = False, manual_input: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_allowed()
        if not self._factory.enabled:
            output = CapitalBrainOutput(market_id=market_id, insufficient_data=True, insufficient_data_reasons=["database_disabled"])
            return {"dry_run": dry_run, "written": False, "output": output.model_dump(mode="json")}
        run_id = f"capital_{uuid4().hex}"
        with self._factory.connect() as conn:
            payload = self.capital_input_builder.build(conn, market_id=market_id, candidate_engine=candidate_engine, manual=manual_input, connection_factory=self._factory)
            output = self.capital_brain.analyze(payload)
            if dry_run:
                return {"dry_run": True, "written": False, "run_id": run_id, "output": output.model_dump(mode="json")}
            with conn.transaction():
                self.capital_run_repo.insert_started(
                    conn,
                    run_id=run_id,
                    market_id=market_id,
                    market_family=payload.market_family,
                    candidate_engine=payload.candidate_engine,
                    runtime_mode=self._runtime_mode(),
                    input_sources=_capital_sources(payload),
                    input_completeness_score=payload.data_completeness_score,
                )
                self.capital_output_repo.insert(conn, run_id, payload.market_family, payload.candidate_engine, output)
                self.capital_run_repo.finish(conn, run_id)
            conn.commit()
        self._publish_capital(run_id, output)
        return {"dry_run": False, "written": True, "run_id": run_id, "output": output.model_dump(mode="json")}

    def analyze_both(self, market_id: str, *, candidate_engine: str | None = None, dry_run: bool = False, manual_context: dict[str, Any] | None = None, manual_capital: dict[str, Any] | None = None) -> dict[str, Any]:
        context = self.analyze_context(market_id, dry_run=dry_run, manual_input=manual_context)
        capital = self.analyze_capital(market_id=market_id, candidate_engine=candidate_engine, dry_run=dry_run, manual_input=manual_capital)
        snapshot = BrainCombinedSnapshot(
            market_id=market_id,
            context_output=ContextBrainOutput(**context["output"]),
            capital_output=CapitalBrainOutput(**capital["output"]),
            reasons=[],
        )
        if not dry_run:
            self._event_bus.publish(EventType.BRAIN_SNAPSHOT_CREATED.value, {"market_id": market_id, "interesting": snapshot.interesting, "worth_money": snapshot.worth_money}, "brains", aggregate_type="market", aggregate_id=market_id)
        return {"dry_run": dry_run, "written": not dry_run, "snapshot": snapshot.model_dump(mode="json")}

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DISABLED", "context_runs_today": 0, "capital_runs_today": 0, "insufficient_data_count": 0, "blocked_capital_count": 0, "latest_context_run_ts": None, "latest_capital_run_ts": None, "errors_today": 0}
        try:
            with self._factory.connect() as conn:
                context = self.context_run_repo.health(conn)
                capital = self.capital_run_repo.health(conn)
                counts = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM context_brain_outputs WHERE insufficient_data IS TRUE) +
                        (SELECT COUNT(*) FROM capital_brain_outputs WHERE insufficient_data IS TRUE) AS insufficient_data_count,
                        (SELECT COUNT(*) FROM capital_brain_outputs WHERE capital_allowed IS FALSE) AS blocked_capital_count
                    """
                ).fetchone()
            return {
                "status": "HEALTHY" if (context or {}).get("latest_run_ts") or (capital or {}).get("latest_run_ts") else "EMPTY",
                "context_runs_today": int((context or {}).get("runs_today") or 0),
                "capital_runs_today": int((capital or {}).get("runs_today") or 0),
                "insufficient_data_count": int((counts or {}).get("insufficient_data_count") or 0),
                "blocked_capital_count": int((counts or {}).get("blocked_capital_count") or 0),
                "latest_context_run_ts": _iso((context or {}).get("latest_run_ts")),
                "latest_capital_run_ts": _iso((capital or {}).get("latest_run_ts")),
                "errors_today": 0,
            }
        except Exception as exc:
            return {"status": "ERROR", "context_runs_today": 0, "capital_runs_today": 0, "insufficient_data_count": 0, "blocked_capital_count": 0, "latest_context_run_ts": None, "latest_capital_run_ts": None, "errors_today": 1, "error": str(exc)}

    def latest_context(self, market_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return _serialize(self.context_output_repo.latest_for_market(conn, market_id)) or {"market_id": market_id, "output": None}

    def latest_capital(self, market_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return _serialize(self.capital_output_repo.latest_for_market(conn, market_id)) or {"market_id": market_id, "output": None}

    def combined(self, market_id: str) -> dict[str, Any]:
        return {"market_id": market_id, "context": self.latest_context(market_id), "capital": self.latest_capital(market_id)}

    def recent_context(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.context_output_repo.recent(conn, limit=limit)]

    def recent_capital(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.capital_output_repo.recent(conn, limit=limit)]

    def recent_blocked(self, *, limit: int = 100) -> dict[str, Any]:
        with self._factory.connect() as conn:
            capital = [_serialize(row) for row in self.capital_output_repo.blocked(conn, limit=limit)]
            context = [_serialize(row) for row in conn.execute("SELECT * FROM context_brain_outputs WHERE insufficient_data IS TRUE ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()]
        return {"capital_blocks": capital, "context_insufficient_data": context}

    def _assert_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.RUN_INTELLIGENCE)
        except Exception as exc:
            raise BrainAnalysisBlocked("brain analysis blocked by runtime mode") from exc

    def _runtime_mode(self) -> str | None:
        try:
            return self._governor.get_current_state().current_mode.value
        except Exception:
            return None

    def _publish_context(self, run_id: str, output: ContextBrainOutput) -> None:
        payload = {"run_id": run_id, "market_id": output.market_id, "context_shift": output.context_shift, "confidence": output.confidence, "insufficient_data": output.insufficient_data}
        self._event_bus.publish(EventType.CONTEXT_BRAIN_RUN_STARTED.value, {"run_id": run_id, "market_id": output.market_id}, "brains", aggregate_type="market", aggregate_id=output.market_id)
        self._event_bus.publish(EventType.CONTEXT_BRAIN_OUTPUT_CREATED.value, payload, "brains", aggregate_type="market", aggregate_id=output.market_id)
        if output.insufficient_data:
            self._event_bus.publish(EventType.CONTEXT_BRAIN_INSUFFICIENT_DATA.value, payload, "brains", aggregate_type="market", aggregate_id=output.market_id)

    def _publish_capital(self, run_id: str, output: CapitalBrainOutput) -> None:
        payload = {"run_id": run_id, "market_id": output.market_id, "capital_allowed": output.capital_allowed, "confidence": output.allocation_confidence, "block_reason": output.block_reason, "insufficient_data": output.insufficient_data}
        self._event_bus.publish(EventType.CAPITAL_BRAIN_RUN_STARTED.value, {"run_id": run_id, "market_id": output.market_id}, "brains", aggregate_type="market", aggregate_id=output.market_id)
        self._event_bus.publish(EventType.CAPITAL_BRAIN_OUTPUT_CREATED.value, payload, "brains", aggregate_type="market", aggregate_id=output.market_id)
        if not output.capital_allowed:
            self._event_bus.publish(EventType.CAPITAL_BRAIN_BLOCKED.value, payload, "brains", aggregate_type="market", aggregate_id=output.market_id)
        if output.insufficient_data:
            self._event_bus.publish(EventType.CAPITAL_BRAIN_INSUFFICIENT_DATA.value, payload, "brains", aggregate_type="market", aggregate_id=output.market_id)


def _context_sources(payload) -> list[str]:
    return [name for name, rows in [("news", payload.news_signals), ("rules", payload.rules_signals), ("social", payload.social_signals), ("whale", payload.whale_signals), ("technical", payload.technical_signals)] if rows]


def _capital_sources(payload) -> list[str]:
    sources = ["capital_snapshot"] if payload.balance is not None else []
    if payload.memory_snapshot:
        sources.append("market_memory")
    return sources


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _iso(value) for key, value in dict(row).items()}
