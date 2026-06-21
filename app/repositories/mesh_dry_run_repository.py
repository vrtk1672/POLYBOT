from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class MeshDryRunRepository:
    def list_candidate_signals(
        self,
        conn: Connection,
        *,
        limit: int = 20,
        market_id: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = ["market_id IS NOT NULL"]
        params: list[Any] = []
        if market_id:
            filters.append("market_id = %s")
            params.append(market_id)
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM neuron_signals
                WHERE {' AND '.join(filters)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        ]

    def list_signal_entities(self, conn: Connection, signal_ids: list[str]) -> list[dict[str, Any]]:
        if not signal_ids:
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM neuron_signal_entities
                WHERE signal_id = ANY(%s)
                ORDER BY created_at DESC, id DESC
                """,
                (signal_ids,),
            ).fetchall()
        ]

    def ensure_signal_market_link(self, conn: Connection, *, signal_id: str, market_id: str, reason: str) -> tuple[dict[str, Any], bool]:
        existing = conn.execute(
            """
            SELECT *
            FROM signal_market_links
            WHERE signal_id = %s
              AND market_id = %s
              AND created_by = 'mesh_dry_run'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (signal_id, market_id),
        ).fetchone()
        if existing:
            return dict(existing), False
        row = conn.execute(
            """
            INSERT INTO signal_market_links (
                signal_id, market_id, link_type, link_status, confidence, reason, created_by
            )
            VALUES (%s, %s, 'exact_match', 'suggested', 1.0, %s, 'mesh_dry_run')
            RETURNING *
            """,
            (signal_id, market_id, reason),
        ).fetchone()
        return dict(row), True

    def ensure_event_entity(
        self,
        conn: Connection,
        *,
        signal_id: str,
        entity_type: str,
        entity_name: str,
        entity_id: str,
        confidence: float | None,
    ) -> tuple[dict[str, Any], bool]:
        existing = conn.execute(
            """
            SELECT *
            FROM event_entities
            WHERE source_signal_id = %s
              AND lower(entity_name) = lower(%s)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (signal_id, entity_name),
        ).fetchone()
        if existing:
            return dict(existing), False
        row = conn.execute(
            """
            INSERT INTO event_entities (
                entity_id, entity_type, entity_name, normalized_name, source_signal_id,
                source_name, confidence, metadata_json
            )
            VALUES (%s, %s, %s, lower(%s), %s, 'neuron_signal_entities', %s, %s)
            RETURNING *
            """,
            (
                entity_id,
                entity_type or "unknown",
                entity_name,
                entity_name,
                signal_id,
                confidence,
                Jsonb({"created_by": "mesh_dry_run"}),
            ),
        ).fetchone()
        return dict(row), True

    def ensure_impact_link(
        self,
        conn: Connection,
        *,
        signal_id: str,
        market_id: str,
        impact_direction: str,
        cortex_action_hint: str,
        reasoning_summary: str,
        confidence: float | None,
        urgency: float | None,
    ) -> tuple[dict[str, Any], bool]:
        existing = conn.execute(
            """
            SELECT *
            FROM impact_links
            WHERE signal_id = %s
              AND market_id = %s
              AND created_by = 'mesh_dry_run'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (signal_id, market_id),
        ).fetchone()
        if existing:
            return dict(existing), False
        row = conn.execute(
            """
            INSERT INTO impact_links (
                impact_link_id, signal_id, market_id, impact_scope, impact_direction,
                impact_status, impact_strength, confidence, urgency, cortex_action_hint,
                reasoning_summary, created_by
            )
            VALUES (
                %s, %s, %s, 'market',
                %s, 'suggested', 0.4, %s, %s, %s, %s, 'mesh_dry_run'
            )
            RETURNING *
            """,
            (f"impact_{uuid4().hex}", signal_id, market_id, impact_direction, confidence, urgency, cortex_action_hint, reasoning_summary),
        ).fetchone()
        return dict(row), True

    def find_dry_run_brain_output(
        self,
        conn: Connection,
        *,
        market_id: str,
        brain: str,
        source_signal_ids: list[str],
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM brain_outputs
            WHERE market_id = %s
              AND brain = %s
              AND generated_by = 'mesh_dry_run'
              AND metadata_json ->> 'source_signal_key' = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (market_id, brain, _signal_key(source_signal_ids)),
        ).fetchone()
        return dict(row) if row else None

    def insert_dry_run(
        self,
        conn: Connection,
        *,
        dry_run_id: str,
        status: str,
        started_at: Any,
        completed_at: Any,
        mode: str | None,
        summary: dict[str, Any],
        safety_before: dict[str, int],
        safety_after: dict[str, int],
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO mesh_dry_runs (
                dry_run_id, status, started_at, completed_at, mode, markets_processed,
                signals_processed, signal_market_links_created, impact_links_created,
                brain_outputs_created, coordinator_decisions_created, no_trade_explanations_created,
                execution_allowed, paper_orders_before, paper_orders_after, shadow_orders_before,
                shadow_orders_after, live_orders_before, live_orders_after, summary_json
            )
            VALUES (
                %(dry_run_id)s, %(status)s, %(started_at)s, %(completed_at)s, %(mode)s,
                %(markets_processed)s, %(signals_processed)s, %(signal_market_links_created)s,
                %(impact_links_created)s, %(brain_outputs_created)s, %(coordinator_decisions_created)s,
                %(no_trade_explanations_created)s, false, %(paper_orders_before)s,
                %(paper_orders_after)s, %(shadow_orders_before)s, %(shadow_orders_after)s,
                %(live_orders_before)s, %(live_orders_after)s, %(summary_json)s
            )
            RETURNING *
            """,
            {
                "dry_run_id": dry_run_id,
                "status": status,
                "started_at": started_at,
                "completed_at": completed_at,
                "mode": mode,
                "markets_processed": summary["markets_processed"],
                "signals_processed": summary["signals_processed"],
                "signal_market_links_created": summary["signal_market_links_created"],
                "impact_links_created": summary["impact_links_created"],
                "brain_outputs_created": summary["brain_outputs_created"],
                "coordinator_decisions_created": summary["coordinator_decisions_created"],
                "no_trade_explanations_created": summary["no_trade_explanations_created"],
                "paper_orders_before": safety_before.get("paper_orders", 0),
                "paper_orders_after": safety_after.get("paper_orders", 0),
                "shadow_orders_before": safety_before.get("shadow_orders", 0),
                "shadow_orders_after": safety_after.get("shadow_orders", 0),
                "live_orders_before": safety_before.get("live_orders", 0),
                "live_orders_after": safety_after.get("live_orders", 0),
                "summary_json": Jsonb(json.loads(json.dumps(summary, default=str))),
            },
        ).fetchone()
        return dict(row)

    def insert_dry_run_item(self, conn: Connection, *, dry_run_id: str, item: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO mesh_dry_run_items (
                dry_run_id, market_id, position_id, final_state, primary_reason, signal_count,
                impact_link_count, brain_output_count, coordinator_decision_id,
                no_trade_explanation, details_json
            )
            VALUES (
                %(dry_run_id)s, %(market_id)s, %(position_id)s, %(final_state)s,
                %(primary_reason)s, %(signal_count)s, %(impact_link_count)s,
                %(brain_output_count)s, %(coordinator_decision_id)s,
                %(no_trade_explanation)s, %(details_json)s
            )
            RETURNING *
            """,
            {
                "dry_run_id": dry_run_id,
                "market_id": item.get("market_id"),
                "position_id": item.get("position_id"),
                "final_state": item.get("coordinator_final_state") or item.get("final_state") or "INSUFFICIENT_DATA",
                "primary_reason": item.get("reason") or item.get("primary_reason") or "Dry run produced no executable action.",
                "signal_count": item.get("signal_count", 0),
                "impact_link_count": item.get("impact_link_count", 0),
                "brain_output_count": item.get("brain_output_count", 0),
                "coordinator_decision_id": item.get("coordinator_decision_id"),
                "no_trade_explanation": item.get("no_trade_explanation"),
                "details_json": Jsonb(json.loads(json.dumps(item, default=str))),
            },
        ).fetchone()
        return dict(row)

    def list_recent_dry_runs(self, conn: Connection, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_dry_runs
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def get_dry_run(self, conn: Connection, dry_run_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_dry_runs WHERE dry_run_id = %s", (dry_run_id,)).fetchone()
        return dict(row) if row else None

    def list_dry_run_items(self, conn: Connection, dry_run_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_dry_run_items
                WHERE dry_run_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (dry_run_id,),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int = 10) -> dict[str, Any]:
        latest = self.list_recent_dry_runs(conn, limit=1)
        recent = self.list_recent_dry_runs(conn, limit=limit)
        counts = conn.execute(
            """
            SELECT
                COALESCE(SUM(signals_processed), 0) AS signals,
                COALESCE(SUM(impact_links_created), 0) AS impact_links,
                COALESCE(SUM(brain_outputs_created), 0) AS brain_outputs,
                COALESCE(SUM(coordinator_decisions_created), 0) AS coordinator_decisions,
                COALESCE(SUM(no_trade_explanations_created), 0) AS no_trade_explanations
            FROM mesh_dry_runs
            WHERE created_at >= now() - interval '24 hours'
            """
        ).fetchone()
        return {
            "latest_dry_run": latest[0] if latest else None,
            "recent_dry_runs": recent,
            "flow_counts": {
                "signals": int(counts["signals"] or 0),
                "impact_links": int(counts["impact_links"] or 0),
                "brain_outputs": int(counts["brain_outputs"] or 0),
                "coordinator_decisions": int(counts["coordinator_decisions"] or 0),
                "no_trade_explanations": int(counts["no_trade_explanations"] or 0),
            },
        }


def _signal_key(source_signal_ids: list[str]) -> str:
    return ",".join(sorted(str(item) for item in source_signal_ids if item))
