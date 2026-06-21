from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.market_link_candidate import MarketLinkCandidateContract


class MarketLinkCandidatesRepository:
    def insert(self, conn: Connection, candidate: MarketLinkCandidateContract) -> None:
        conn.execute(
            """
            INSERT INTO market_link_candidates (
                id, market_link_run_id, interpretation_id, market_id,
                candidate_source, link_status, relevance_score,
                directness_class, directness_score, contradiction_risk,
                affected_outcome, usability_class, explanation_json,
                linker_version, prompt_version, model_name
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                candidate.id,
                candidate.market_link_run_id,
                candidate.interpretation_id,
                candidate.market_id,
                candidate.candidate_source,
                candidate.link_status,
                candidate.relevance_score,
                candidate.directness_class,
                candidate.directness_score,
                candidate.contradiction_risk,
                candidate.affected_outcome,
                candidate.usability_class,
                Jsonb(candidate.explanation_json),
                candidate.linker_version,
                candidate.prompt_version,
                candidate.model_name,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM market_link_candidates
            WHERE market_link_run_id = %s
            ORDER BY relevance_score DESC, created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, candidate_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM market_link_candidates
            WHERE id = %s
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()

    def list_for_interpretation(
        self, conn: Connection, interpretation_id: str
    ) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM market_link_candidates
            WHERE interpretation_id = %s
            ORDER BY relevance_score DESC, created_at ASC
            """,
            (interpretation_id,),
        ).fetchall()
