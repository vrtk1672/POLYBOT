from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.bucket_allocations_repository import BucketAllocationsRepository
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.repositories.ranking_v2_candidates_repository import RankingV2CandidatesRepository
from app.repositories.ranking_v2_runs_repository import RankingV2RunsRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository
from app.repositories.whale_market_scores_repository import WhaleMarketScoresRepository


class RankingV2QueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = RankingV2RunsRepository()
        self._candidates = RankingV2CandidatesRepository()
        self._markets = MarketSnapshotsRepository()
        self._decisions = DecisionLedgerRepository()
        self._cognition = CognitionSummariesRepository()
        self._whale_scores = WhaleMarketScoresRepository()
        self._trade_classifications = TradeClassificationsRepository()
        self._bucket_allocations = BucketAllocationsRepository()

    def get_ranking_v2_run_summary(self, ranking_v2_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, ranking_v2_run_id)
            if run is None:
                return None
            rows = self._candidates.list_for_run(conn, ranking_v2_run_id)

        tier_counts: dict[str, int] = {}
        for row in rows:
            tier = str(row["rank_tier_class"])
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        return {
            "run": dict(run),
            "candidate_count": len(rows),
            "tier_counts": tier_counts,
        }

    def list_ranking_v2_candidates_for_run(self, ranking_v2_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_for_run(conn, ranking_v2_run_id)
        return [dict(row) for row in rows]

    def get_ranking_v2_candidate_details(
        self,
        *,
        ranking_v2_candidate_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if ranking_v2_candidate_id is not None:
                row = self._candidates.get_by_id(conn, ranking_v2_candidate_id)
            elif market_id is not None:
                row = self._candidates.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("ranking_v2_candidate_id or market_id is required")
        return dict(row) if row is not None else None

    def list_top_ranked_candidates(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_top_candidates(conn, limit)
        return [dict(row) for row in rows]

    def compare_ranking_v2_candidate_to_upstream_context(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            candidate = self._candidates.get_latest_by_market(conn, market_id)
            market = self._markets.get_latest_for_market(conn, market_id)
            cognition_rows = self._cognition.list_for_market(conn, market_id, 1)
            whale_score = self._whale_scores.get_latest_by_market(conn, market_id)
            trade_classification = self._trade_classifications.get_latest_by_market(conn, market_id)
            bucket_allocation = self._bucket_allocations.get_latest_by_market(conn, market_id)
            decision = None
            if market is not None and market["cycle_id"] is not None:
                decision = self._decisions.get_for_cycle_market(conn, cycle_id=str(market["cycle_id"]), market_id=market_id)
        if (
            candidate is None
            and market is None
            and not cognition_rows
            and whale_score is None
            and trade_classification is None
            and bucket_allocation is None
        ):
            return None
        return {
            "ranking_candidate": dict(candidate) if candidate is not None else None,
            "market_snapshot": dict(market) if market is not None else None,
            "decision": dict(decision) if decision is not None else None,
            "cognition_summary": dict(cognition_rows[0]) if cognition_rows else None,
            "whale_market_score": dict(whale_score) if whale_score is not None else None,
            "trade_classification": dict(trade_classification) if trade_classification is not None else None,
            "bucket_allocation": dict(bucket_allocation) if bucket_allocation is not None else None,
        }
