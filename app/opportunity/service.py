from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.opportunity.contracts import OpportunityRunResult
from app.opportunity.opportunity_errors import OpportunityScoringBlocked
from app.opportunity.opportunity_scorer import OpportunityScorer
from app.opportunity.signal_input_builder import OpportunitySignalInputBuilder
from app.repositories.opportunity_risk_flag_repository import OpportunityRiskFlagRepository
from app.repositories.opportunity_run_repository import OpportunityRunRepository
from app.repositories.opportunity_score_repository import OpportunityScoreRepository
from app.repositories.opportunity_signal_input_repository import OpportunitySignalInputRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class OpportunityService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, state_governor: StateGovernor | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.input_builder = OpportunitySignalInputBuilder()
        self.scorer = OpportunityScorer()
        self.run_repo = OpportunityRunRepository()
        self.score_repo = OpportunityScoreRepository()
        self.input_repo = OpportunitySignalInputRepository()
        self.flag_repo = OpportunityRiskFlagRepository()

    def score_market(self, market_id: str, *, side: str | None = None, dry_run: bool = False, manual_input: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_allowed()
        if not self._factory.enabled:
            return {"dry_run": dry_run, "written": False, "error": "database_disabled"}
        run_id = f"opportunity_{uuid4().hex}"
        with self._factory.connect() as conn:
            payload = self.input_builder.build(conn, market_id, side=side, manual=manual_input)
            score, signal_inputs = self.scorer.score(payload)
            result = OpportunityRunResult(
                run_id=run_id,
                market_id=market_id,
                side=score.side,
                score=score,
                signal_inputs=signal_inputs,
                risk_flags=score.risk_flags,
                persisted=False,
            )
            if dry_run:
                return {"dry_run": True, "written": False, "result": result.model_dump(mode="json")}
            with conn.transaction():
                self.run_repo.insert_started(
                    conn,
                    run_id=run_id,
                    market_id=market_id,
                    market_family=payload.market_family,
                    side=score.side,
                    runtime_mode=self._runtime_mode(),
                    input_sources=_input_sources(payload),
                    input_completeness_score=payload.data_completeness_score,
                    context_run_id=payload.context_output.get("run_id"),
                    capital_run_id=payload.capital_output.get("run_id"),
                )
                self.score_repo.insert(conn, run_id, payload.market_family, score)
                self.input_repo.insert_many(conn, run_id, market_id, signal_inputs)
                self.flag_repo.insert_many(conn, run_id, market_id, score.risk_flags)
                self.run_repo.finish(conn, run_id)
            conn.commit()
        self._publish(run_id, score)
        result.persisted = True
        return {"dry_run": False, "written": True, "result": result.model_dump(mode="json")}

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty("DISABLED")
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('opportunity_scores_v2') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return _empty("EMPTY")
                run_health = self.run_repo.health(conn)
                stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS scores_today,
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND score_band = 'BLOCKED') AS blocked_today,
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND score_band = 'WATCHLIST') AS watchlist_today,
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND score_band = 'HIGH_CONVICTION') AS high_score_today,
                      COUNT(*) FILTER (WHERE insufficient_data IS TRUE) AS insufficient_data_count,
                      MAX(created_at) AS latest_score_ts
                    FROM opportunity_scores_v2
                    """
                ).fetchone()
            return {
                "status": "HEALTHY" if (stats or {}).get("latest_score_ts") else "EMPTY",
                "runs_today": int((run_health or {}).get("runs_today") or 0),
                "scores_today": int((stats or {}).get("scores_today") or 0),
                "blocked_today": int((stats or {}).get("blocked_today") or 0),
                "watchlist_today": int((stats or {}).get("watchlist_today") or 0),
                "high_score_today": int((stats or {}).get("high_score_today") or 0),
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
                "latest_score_ts": _iso((stats or {}).get("latest_score_ts")),
                "errors_today": int((run_health or {}).get("errors_today") or 0),
            }
        except Exception as exc:
            data = _empty("ERROR")
            data["errors_today"] = 1
            data["error"] = str(exc)
            return data

    def latest_for_market(self, market_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return _serialize(self.score_repo.latest_for_market(conn, market_id)) or {"market_id": market_id, "score": None}

    def recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.score_repo.recent(conn, limit=limit)]

    def top(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.score_repo.top(conn, limit=limit)]

    def blocked_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.score_repo.blocked(conn, limit=limit)]

    def risk_flags_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.flag_repo.recent(conn, limit=limit)]

    def run_detail(self, run_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            score = _serialize(self.score_repo.by_run(conn, run_id))
            return {
                "run_id": run_id,
                "score": score,
                "signal_inputs": [_serialize(row) for row in self.input_repo.by_run(conn, run_id)],
                "risk_flags": [_serialize(row) for row in self.flag_repo.by_run(conn, run_id)],
            }

    def _assert_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.SCORE_MARKET)
        except Exception as exc:
            raise OpportunityScoringBlocked("opportunity scoring blocked by runtime mode") from exc

    def _runtime_mode(self) -> str | None:
        try:
            return self._governor.get_current_state().current_mode.value
        except Exception:
            return None

    def _publish(self, run_id: str, score) -> None:
        payload = {
            "run_id": run_id,
            "market_id": score.market_id,
            "score_band": score.score_band,
            "opportunity_score": score.opportunity_score,
            "insufficient_data": score.insufficient_data,
            "candidate_engines": score.candidate_engines,
        }
        self._event_bus.publish(EventType.OPPORTUNITY_RUN_STARTED.value, {"run_id": run_id, "market_id": score.market_id}, "opportunity", aggregate_type="market", aggregate_id=score.market_id)
        self._event_bus.publish(EventType.OPPORTUNITY_SCORE_CREATED.value, payload, "opportunity", aggregate_type="market", aggregate_id=score.market_id)
        if score.score_band == "BLOCKED":
            self._event_bus.publish(EventType.OPPORTUNITY_BLOCKED.value, payload, "opportunity", aggregate_type="market", aggregate_id=score.market_id)
        if score.score_band == "WATCHLIST":
            self._event_bus.publish(EventType.OPPORTUNITY_WATCHLIST_CREATED.value, payload, "opportunity", aggregate_type="market", aggregate_id=score.market_id)
        if score.score_band in {"STRONG", "HIGH_CONVICTION"}:
            self._event_bus.publish(EventType.OPPORTUNITY_HIGH_SCORE_CREATED.value, payload, "opportunity", aggregate_type="market", aggregate_id=score.market_id)
        if score.insufficient_data:
            self._event_bus.publish(EventType.OPPORTUNITY_INSUFFICIENT_DATA.value, payload, "opportunity", aggregate_type="market", aggregate_id=score.market_id)


def _input_sources(payload) -> list[str]:
    sources = []
    for name, value in [
        ("context_brain", payload.context_output),
        ("capital_brain", payload.capital_output),
        ("market_technical", payload.technical_truth),
        ("market_memory", payload.market_memory),
        ("news", payload.news_signals),
        ("rules", payload.rules_signals),
        ("social", payload.social_signals),
        ("whale", payload.whale_signals),
        ("fees", payload.fee_reward_signal),
    ]:
        if value:
            sources.append(name)
    return sources


def _empty(status: str) -> dict[str, Any]:
    return {"status": status, "runs_today": 0, "scores_today": 0, "blocked_today": 0, "watchlist_today": 0, "high_score_today": 0, "insufficient_data_count": 0, "latest_score_ts": None, "errors_today": 0}


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _iso(value) for key, value in dict(row).items()}

