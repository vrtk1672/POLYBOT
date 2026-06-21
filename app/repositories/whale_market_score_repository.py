from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.whale_neuron.contracts import WhaleMarketScore


class WhaleMarketScoreRepository:
    def ensure_scoring_run(self, conn: Connection) -> str:
        run_id = str(uuid4())
        now = datetime.now(UTC)
        conn.execute("INSERT INTO whale_scoring_runs (id, source_type, status, scorer_version, started_at, ended_at, input_count, success_count, failure_count) VALUES (%s, 'v2.7', 'COMPLETED', 'v2.7', %s, %s, 1, 1, 0)", (run_id, now, now))
        return run_id

    def insert_score(self, conn: Connection, score: WhaleMarketScore) -> dict[str, Any]:
        score_id = score.whale_market_score_id
        return conn.execute(
            """
            INSERT INTO whale_market_scores (
                id, whale_scoring_run_id, market_id, scoring_window_start, scoring_window_end,
                whale_presence_score, whale_conviction_score, smart_whale_alignment_score,
                whale_reversal_risk, supporting_wallet_count, top_supporting_wallets_json,
                category_mix_json, scoring_reason_codes_json, scoring_reason_text, explanation_json,
                scorer_version, whale_market_score_id, whale_id, whale_event_id, side,
                smart_whale_alignment, follow_value, noise_penalty, confidence, signal_json, metadata_json
            )
            VALUES (%s, %s, %s, now(), now(), %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, 'v2.7', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                score_id,
                self.ensure_scoring_run(conn),
                score.market_id,
                score.whale_presence_score,
                score.whale_conviction_score,
                score.smart_whale_alignment,
                score.whale_reversal_risk,
                Jsonb([score.whale_id]),
                Jsonb({}),
                Jsonb([]),
                "v2.7 whale market score",
                Jsonb(score.signal),
                score_id,
                score.whale_id,
                score.whale_event_id,
                score.side.value,
                score.smart_whale_alignment,
                score.follow_value,
                score.noise_penalty,
                score.confidence,
                Jsonb(score.signal),
                Jsonb({}),
            ),
        ).fetchone()

    def list_by_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM whale_market_scores WHERE market_id = %s ORDER BY computed_at DESC, created_at DESC LIMIT %s", (market_id, limit)).fetchall()

    def list_top(self, conn: Connection, *, limit: int = 50, min_follow_value: float | None = None, max_noise_score: float | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if min_follow_value is not None:
            clauses.append("follow_value >= %s")
            params.append(min_follow_value)
        if max_noise_score is not None:
            clauses.append("noise_penalty <= %s")
            params.append(max_noise_score)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(f"SELECT * FROM whale_market_scores {where} ORDER BY follow_value DESC, whale_presence_score DESC, computed_at DESC LIMIT %s", params).fetchall()
