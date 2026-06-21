from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.whale_profile import WhaleProfileContract


class WhaleProfilesRepository:
    def insert(self, conn: Connection, profile: WhaleProfileContract) -> None:
        conn.execute(
            """
            INSERT INTO whale_profiles (
                id, wallet_address, whale_profile_run_id, total_events, entry_count,
                exit_count, reversal_candidate_count, unknown_count, average_size,
                average_notional, largest_size, largest_notional, active_markets_count,
                market_specialties_json, timing_consistency_score, noise_score,
                average_hold_time, follow_value_baseline, profile_status,
                explanation_json, profiler_version
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            """,
            (
                profile.id,
                profile.wallet_address,
                profile.whale_profile_run_id,
                profile.total_events,
                profile.entry_count,
                profile.exit_count,
                profile.reversal_candidate_count,
                profile.unknown_count,
                profile.average_size,
                profile.average_notional,
                profile.largest_size,
                profile.largest_notional,
                profile.active_markets_count,
                Jsonb(profile.market_specialties_json),
                profile.timing_consistency_score,
                profile.noise_score,
                profile.average_hold_time,
                profile.follow_value_baseline,
                profile.profile_status,
                Jsonb(profile.explanation_json),
                profile.profiler_version,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_profiles
            WHERE whale_profile_run_id = %s
            ORDER BY follow_value_baseline DESC, created_at DESC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, profile_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_profiles
            WHERE id = %s
            LIMIT 1
            """,
            (profile_id,),
        ).fetchone()

    def get_latest_by_wallet(self, conn: Connection, wallet_address: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_profiles
            WHERE wallet_address = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (wallet_address,),
        ).fetchone()

    def list_top_profiles(self, conn: Connection, limit: int, order_by: str) -> list[dict[str, object]]:
        order_column = "follow_value_baseline" if order_by == "follow_value_baseline" else "timing_consistency_score"
        query = f"""
            SELECT *
            FROM whale_profiles
            ORDER BY {order_column} DESC, created_at DESC
            LIMIT %s
        """
        return conn.execute(query, (limit,)).fetchall()
