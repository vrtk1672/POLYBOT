from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.opportunity.contracts import OpportunityScore


class OpportunityScoreRepository:
    def insert(self, conn: Connection, run_id: str, market_family: str | None, score: OpportunityScore) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO opportunity_scores_v2 (
                run_id, market_id, market_family, side, opportunity_score, score_band, edge,
                confidence, trigger_strength, repricing_potential, time_efficiency,
                liquidity_quality, exit_probability, capital_recycling_speed, convexity,
                balance_fit, fee_reward_advantage, risk_penalty, slippage_penalty,
                lockup_penalty, correlation_risk, trap_risk, wording_risk,
                adverse_selection_risk, already_priced_in_score, technical_blocked,
                capital_allowed, insufficient_data, insufficient_data_reasons_json,
                candidate_engines_json, no_trade_reasons_json, explanation, reproducibility_hash
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                run_id, score.market_id, market_family, score.side, score.opportunity_score,
                score.score_band, score.edge, score.confidence, score.trigger_strength,
                score.repricing_potential, score.time_efficiency, score.liquidity_quality,
                score.exit_probability, score.capital_recycling_speed, score.convexity,
                score.balance_fit, score.fee_reward_advantage, score.risk_penalty,
                score.slippage_penalty, score.lockup_penalty, score.correlation_risk,
                score.trap_risk, score.wording_risk, score.adverse_selection_risk,
                score.already_priced_in_score, score.technical_blocked, score.capital_allowed,
                score.insufficient_data, Jsonb(score.insufficient_data_reasons),
                Jsonb(score.candidate_engines), Jsonb(score.no_trade_reasons),
                score.explanation, score.reproducibility_hash,
            ),
        ).fetchone()

    def latest_for_market(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM opportunity_scores_v2 WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM opportunity_scores_v2 ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def top(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM opportunity_scores_v2
            WHERE score_band <> 'BLOCKED' AND insufficient_data IS FALSE
            ORDER BY opportunity_score DESC, confidence DESC, created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def blocked(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            "SELECT * FROM opportunity_scores_v2 WHERE score_band='BLOCKED' OR technical_blocked IS TRUE OR capital_allowed IS FALSE ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()

    def by_run(self, conn: Connection, run_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM opportunity_scores_v2 WHERE run_id=%s ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))

