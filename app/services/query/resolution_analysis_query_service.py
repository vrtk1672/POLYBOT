from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.market_link_candidates_repository import MarketLinkCandidatesRepository
from app.repositories.resolution_analyses_repository import ResolutionAnalysesRepository
from app.repositories.resolution_analysis_runs_repository import ResolutionAnalysisRunsRepository


class ResolutionAnalysisQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = ResolutionAnalysisRunsRepository()
        self._analyses = ResolutionAnalysesRepository()
        self._candidates = MarketLinkCandidatesRepository()

    def get_resolution_analysis_run_summary(
        self,
        resolution_analysis_run_id: str,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, resolution_analysis_run_id)
            if run is None:
                return None
            analyses = self._analyses.list_for_run(conn, resolution_analysis_run_id)

        status_counts: dict[str, int] = {}
        fit_counts: dict[str, int] = {}
        usable_counts: dict[str, int] = {}
        for analysis in analyses:
            status = str(analysis["status"])
            status_counts[status] = status_counts.get(status, 0) + 1
            fit = analysis["direct_fit_class"]
            if fit is not None:
                fit_key = str(fit)
                fit_counts[fit_key] = fit_counts.get(fit_key, 0) + 1
            usable = analysis["usable_now_class"]
            if usable is not None:
                usable_key = str(usable)
                usable_counts[usable_key] = usable_counts.get(usable_key, 0) + 1

        return {
            "run": dict(run),
            "analysis_count": len(analyses),
            "status_counts": status_counts,
            "direct_fit_counts": fit_counts,
            "usable_now_counts": usable_counts,
        }

    def list_resolution_analyses_for_run(self, resolution_analysis_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._analyses.list_for_run(conn, resolution_analysis_run_id)
        return [dict(row) for row in rows]

    def get_resolution_analysis_details(self, resolution_analysis_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._analyses.get_by_id(conn, resolution_analysis_id)
        return dict(row) if row is not None else None

    def list_resolution_analyses_for_market(self, market_id: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._analyses.list_for_market(conn, market_id, limit)
        return [dict(row) for row in rows]

    def compare_resolution_analysis_to_link_candidate(
        self,
        resolution_analysis_id: str,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            analysis = self._analyses.get_by_id(conn, resolution_analysis_id)
            if analysis is None:
                return None
            candidate = self._candidates.get_by_id(conn, str(analysis["market_link_candidate_id"]))
        return {
            "analysis": dict(analysis),
            "candidate": dict(candidate) if candidate is not None else None,
        }
