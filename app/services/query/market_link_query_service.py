from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.market_link_candidates_repository import MarketLinkCandidatesRepository
from app.repositories.market_link_runs_repository import MarketLinkRunsRepository


class MarketLinkQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = MarketLinkRunsRepository()
        self._candidates = MarketLinkCandidatesRepository()

    def get_market_link_run_summary(self, market_link_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, market_link_run_id)
            if run is None:
                return None
            candidates = self._candidates.list_for_run(conn, market_link_run_id)

        status_counts: dict[str, int] = {}
        usability_counts: dict[str, int] = {}
        for c in candidates:
            ls = str(c["link_status"])
            uc = str(c["usability_class"])
            status_counts[ls] = status_counts.get(ls, 0) + 1
            usability_counts[uc] = usability_counts.get(uc, 0) + 1

        return {
            "run": dict(run),
            "candidate_count": len(candidates),
            "link_status_counts": status_counts,
            "usability_class_counts": usability_counts,
        }

    def list_market_link_candidates_for_run(
        self, market_link_run_id: str
    ) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_for_run(conn, market_link_run_id)
        return [dict(r) for r in rows]

    def get_market_link_candidate_details(
        self, market_link_candidate_id: str
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            row = self._candidates.get_by_id(conn, market_link_candidate_id)
        return dict(row) if row is not None else None

    def list_market_links_for_interpretation(
        self, interpretation_id: str
    ) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_for_interpretation(conn, interpretation_id)
        return [dict(r) for r in rows]

    def compare_linked_market_ids_to_interpreter_candidates(
        self, interpretation_id: str
    ) -> dict[str, object] | None:
        """
        Compare the market_ids in market_link_candidates against the
        affected_market_candidates_json hints in the source interpretation.
        Returns a summary of which hints were linked and which were not.
        """
        with self._factory.connect() as conn:
            interp = conn.execute(
                "SELECT id, affected_market_candidates_json FROM event_interpretations WHERE id = %s LIMIT 1",
                (interpretation_id,),
            ).fetchone()
            if interp is None:
                return None
            linked_rows = self._candidates.list_for_interpretation(conn, interpretation_id)

        hints: list[dict] = list(interp["affected_market_candidates_json"] or [])
        linked_market_ids = {str(r["market_id"]) for r in linked_rows}

        matched: list[dict[str, object]] = []
        unmatched: list[dict[str, object]] = []
        for hint in hints:
            hint_id = hint.get("market_id_hint") or hint.get("question_hint") or ""
            if hint_id in linked_market_ids:
                matched.append(hint)
            else:
                unmatched.append(hint)

        return {
            "interpretation_id": interpretation_id,
            "total_hints": len(hints),
            "linked_count": len(linked_rows),
            "matched_hints": matched,
            "unmatched_hints": unmatched,
        }
