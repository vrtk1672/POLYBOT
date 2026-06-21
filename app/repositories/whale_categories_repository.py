from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.whale_category import WhaleCategoryContract


class WhaleCategoriesRepository:
    def insert(self, conn: Connection, category: WhaleCategoryContract) -> None:
        conn.execute(
            """
            INSERT INTO whale_categories (
                id, wallet_address, whale_profile_id, whale_category_run_id, primary_category,
                secondary_categories_json, category_confidence, specialization_context_json,
                category_reason_codes_json, category_reason_text, explanation_json, categorizer_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                category.id,
                category.wallet_address,
                category.whale_profile_id,
                category.whale_category_run_id,
                category.primary_category,
                Jsonb(category.secondary_categories_json),
                category.category_confidence,
                Jsonb(category.specialization_context_json),
                Jsonb(category.category_reason_codes_json),
                category.category_reason_text,
                Jsonb(category.explanation_json),
                category.categorizer_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_categories
            WHERE whale_category_run_id = %s
            ORDER BY category_confidence DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, category_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_categories
            WHERE id = %s
            LIMIT 1
            """,
            (category_id,),
        ).fetchone()

    def get_latest_by_wallet(self, conn: Connection, wallet_address: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_categories
            WHERE wallet_address = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (wallet_address,),
        ).fetchone()

    def list_by_primary(self, conn: Connection, primary_category: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_categories
            WHERE primary_category = %s
            ORDER BY category_confidence DESC, created_at DESC
            LIMIT %s
            """,
            (primary_category, limit),
        ).fetchall()
