from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.repositories.trade_classification_runs_repository import TradeClassificationRunsRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository
from app.repositories.whale_market_scores_repository import WhaleMarketScoresRepository


class TradeClassificationQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = TradeClassificationRunsRepository()
        self._classifications = TradeClassificationsRepository()
        self._markets = MarketSnapshotsRepository()
        self._decisions = DecisionLedgerRepository()
        self._cognition = CognitionSummariesRepository()
        self._whale_scores = WhaleMarketScoresRepository()

    def get_trade_classification_run_summary(self, trade_classification_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, trade_classification_run_id)
            if run is None:
                return None
            rows = self._classifications.list_for_run(conn, trade_classification_run_id)

        primary_counts: dict[str, int] = {}
        for row in rows:
            trade_type = str(row["primary_trade_type"])
            primary_counts[trade_type] = primary_counts.get(trade_type, 0) + 1

        return {
            "run": dict(run),
            "classification_count": len(rows),
            "primary_counts": primary_counts,
        }

    def list_trade_classifications_for_run(self, trade_classification_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._classifications.list_for_run(conn, trade_classification_run_id)
        return [dict(row) for row in rows]

    def get_trade_classification_details(
        self,
        *,
        trade_classification_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if trade_classification_id is not None:
                row = self._classifications.get_by_id(conn, trade_classification_id)
            elif market_id is not None:
                row = self._classifications.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("trade_classification_id or market_id is required")
        return dict(row) if row is not None else None

    def list_trade_classifications_by_type(self, primary_trade_type: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._classifications.list_by_primary(conn, primary_trade_type, limit)
        return [dict(row) for row in rows]

    def compare_trade_classification_to_upstream_context(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            classification = self._classifications.get_latest_by_market(conn, market_id)
            market = self._markets.get_latest_for_market(conn, market_id)
            cognition_rows = self._cognition.list_for_market(conn, market_id, 1)
            whale_score = self._whale_scores.get_latest_by_market(conn, market_id)
            decision = None
            if market is not None and market["cycle_id"] is not None:
                decision = self._decisions.get_for_cycle_market(
                    conn,
                    cycle_id=str(market["cycle_id"]),
                    market_id=market_id,
                )
        if classification is None and market is None and whale_score is None and not cognition_rows:
            return None
        return {
            "classification": dict(classification) if classification is not None else None,
            "market_snapshot": dict(market) if market is not None else None,
            "decision": dict(decision) if decision is not None else None,
            "cognition_summary": dict(cognition_rows[0]) if cognition_rows else None,
            "whale_market_score": dict(whale_score) if whale_score is not None else None,
        }
