from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.whale_neuron.contracts import WhaleProfile


class WhaleProfileRepository:
    def ensure_profile_run(self, conn: Connection) -> str:
        run_id = str(uuid4())
        now = datetime.now(UTC)
        conn.execute(
            "INSERT INTO whale_profile_runs (id, source_type, status, profiler_version, started_at, ended_at, input_count, success_count, failure_count) VALUES (%s, 'v2.7', 'COMPLETED', 'v2.7', %s, %s, 1, 1, 0)",
            (run_id, now, now),
        )
        return run_id

    def insert_profile(self, conn: Connection, profile: WhaleProfile) -> dict[str, Any]:
        profile_id = str(uuid4())
        return conn.execute(
            """
            INSERT INTO whale_profiles (
                id, wallet_address, whale_profile_run_id, total_events, entry_count, exit_count,
                reversal_candidate_count, unknown_count, average_size, average_notional, largest_size,
                largest_notional, active_markets_count, market_specialties_json, timing_consistency_score,
                noise_score, average_hold_time, follow_value_baseline, profile_status, explanation_json,
                profiler_version, whale_profile_id, whale_id, hit_rate, timing_quality,
                average_entry_quality, average_exit_quality, average_hold_time_seconds, average_trade_size_usd,
                win_consistency, market_specialties_v27_json, follow_value, momentum_chase_score,
                reversal_risk_score, copy_worthy_score, confidence, sample_size
            )
            VALUES (%s, %s, %s, %s, 0, 0, 0, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'v2.7', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                profile_id,
                profile.whale_id,
                self.ensure_profile_run(conn),
                profile.sample_size,
                profile.average_trade_size_usd or 0,
                profile.average_trade_size_usd,
                profile.average_trade_size_usd or 0,
                profile.average_trade_size_usd,
                len(profile.market_specialties),
                Jsonb(profile.market_specialties),
                profile.timing_quality,
                profile.noise_score,
                profile.average_hold_time_seconds,
                profile.follow_value,
                "PROFILE_READY" if profile.sample_size >= 3 else "SPARSE_HISTORY",
                Jsonb({}),
                profile_id,
                profile.whale_id,
                profile.hit_rate,
                profile.timing_quality,
                profile.average_entry_quality,
                profile.average_exit_quality,
                profile.average_hold_time_seconds,
                profile.average_trade_size_usd,
                profile.win_consistency,
                Jsonb(profile.market_specialties),
                profile.follow_value,
                profile.momentum_chase_score,
                profile.reversal_risk_score,
                profile.copy_worthy_score,
                profile.confidence,
                profile.sample_size,
            ),
        ).fetchone()

    def latest_profile(self, conn: Connection, whale_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM whale_profiles WHERE whale_id = %s OR wallet_address = %s ORDER BY created_at DESC LIMIT 1", (whale_id, whale_id)).fetchone()
