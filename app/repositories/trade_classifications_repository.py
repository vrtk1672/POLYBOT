from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.trade_classification import TradeClassificationContract


class TradeClassificationsRepository:
    def insert(self, conn: Connection, classification: TradeClassificationContract) -> None:
        conn.execute(
            """
            INSERT INTO trade_classifications (
                id, trade_classification_run_id, market_id, cycle_id, decision_id,
                cognition_summary_id, whale_market_score_id, primary_trade_type,
                secondary_trade_types_json, classification_confidence, risk_posture_class,
                suggested_bucket_class, classification_reason_codes_json,
                classification_reason_text, explanation_json, classifier_version
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s
            )
            """,
            (
                classification.id,
                classification.trade_classification_run_id,
                classification.market_id,
                classification.cycle_id,
                classification.decision_id,
                classification.cognition_summary_id,
                classification.whale_market_score_id,
                classification.primary_trade_type,
                Jsonb(classification.secondary_trade_types_json),
                classification.classification_confidence,
                classification.risk_posture_class,
                classification.suggested_bucket_class,
                Jsonb(classification.classification_reason_codes_json),
                classification.classification_reason_text,
                Jsonb(classification.explanation_json),
                classification.classifier_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM trade_classifications
            WHERE trade_classification_run_id = %s
            ORDER BY classification_confidence DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, trade_classification_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM trade_classifications
            WHERE id = %s
            LIMIT 1
            """,
            (trade_classification_id,),
        ).fetchone()

    def get_latest_by_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM trade_classifications
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_by_primary(self, conn: Connection, primary_trade_type: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM trade_classifications
            WHERE primary_trade_type = %s
            ORDER BY classification_confidence DESC, created_at DESC
            LIMIT %s
            """,
            (primary_trade_type, limit),
        ).fetchall()
