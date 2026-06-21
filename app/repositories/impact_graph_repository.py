from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.impact_graph import (
    EntityMarketLink,
    EventEntity,
    ImpactLink,
    PositionThesisProfile,
    SignalMarketLink,
    SignalPositionLink,
)


class ImpactGraphRepository:
    def create_event_entity(self, conn: Connection, entity: EventEntity) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO event_entities (
                entity_id, entity_type, entity_name, normalized_name, source_signal_id,
                source_event_id, source_name, confidence, metadata_json, created_at, updated_at
            )
            VALUES (
                %(entity_id)s, %(entity_type)s, %(entity_name)s, %(normalized_name)s,
                %(source_signal_id)s, %(source_event_id)s, %(source_name)s, %(confidence)s,
                %(metadata_json)s, COALESCE(%(created_at)s, now()), COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            _entity_params(entity),
        ).fetchone()
        return dict(row)

    def get_entity(self, conn: Connection, entity_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM event_entities WHERE entity_id = %s", (entity_id,)).fetchone()
        return dict(row) if row else None

    def list_entities(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM event_entities
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def link_entity_to_market(self, conn: Connection, link: EntityMarketLink) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO entity_market_links (
                entity_id, market_id, link_type, link_status, confidence, evidence_signal_id,
                evidence_event_id, evidence_text, created_by, created_at, updated_at
            )
            VALUES (
                %(entity_id)s, %(market_id)s, %(link_type)s, %(link_status)s, %(confidence)s,
                %(evidence_signal_id)s, %(evidence_event_id)s, %(evidence_text)s, %(created_by)s,
                COALESCE(%(created_at)s, now()), COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            link.model_dump(),
        ).fetchone()
        return dict(row)

    def link_signal_to_market(self, conn: Connection, link: SignalMarketLink) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_market_links (
                signal_id, market_id, link_type, link_status, confidence, reason,
                created_by, created_at, updated_at
            )
            VALUES (
                %(signal_id)s, %(market_id)s, %(link_type)s, %(link_status)s, %(confidence)s,
                %(reason)s, %(created_by)s, COALESCE(%(created_at)s, now()), COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            link.model_dump(),
        ).fetchone()
        return dict(row)

    def link_signal_to_position(self, conn: Connection, link: SignalPositionLink) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_position_links (
                signal_id, position_id, market_id, link_type, link_status, confidence, reason,
                created_by, created_at, updated_at
            )
            VALUES (
                %(signal_id)s, %(position_id)s, %(market_id)s, %(link_type)s, %(link_status)s,
                %(confidence)s, %(reason)s, %(created_by)s, COALESCE(%(created_at)s, now()),
                COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            link.model_dump(),
        ).fetchone()
        return dict(row)

    def create_position_thesis_profile(self, conn: Connection, thesis: PositionThesisProfile) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO position_thesis_profiles (
                thesis_id, position_id, market_id, side, entry_thesis, profit_drivers_json,
                invalidation_drivers_json, watch_entities_json, danger_signals_json,
                take_profit_rules_json, partial_exit_rules_json, emergency_exit_rules_json,
                status, created_at, updated_at
            )
            VALUES (
                %(thesis_id)s, %(position_id)s, %(market_id)s, %(side)s, %(entry_thesis)s,
                %(profit_drivers_json)s, %(invalidation_drivers_json)s, %(watch_entities_json)s,
                %(danger_signals_json)s, %(take_profit_rules_json)s, %(partial_exit_rules_json)s,
                %(emergency_exit_rules_json)s, %(status)s, COALESCE(%(created_at)s, now()),
                COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            _thesis_params(thesis),
        ).fetchone()
        return dict(row)

    def get_position_thesis_profile(self, conn: Connection, position_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM position_thesis_profiles
            WHERE position_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (position_id,),
        ).fetchone()
        return dict(row) if row else None

    def create_impact_link(self, conn: Connection, link: ImpactLink) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO impact_links (
                impact_link_id, signal_id, event_id, entity_id, market_id, position_id, thesis_id,
                brain_output_id, coordinator_decision_id, impact_scope, impact_direction, impact_status,
                impact_strength, confidence, urgency, cortex_action_hint, reasoning_summary,
                created_by, ttl_seconds, expires_at, created_at, updated_at
            )
            VALUES (
                %(impact_link_id)s, %(signal_id)s, %(event_id)s, %(entity_id)s, %(market_id)s,
                %(position_id)s, %(thesis_id)s, %(brain_output_id)s, %(coordinator_decision_id)s,
                %(impact_scope)s, %(impact_direction)s, %(impact_status)s, %(impact_strength)s,
                %(confidence)s, %(urgency)s, %(cortex_action_hint)s, %(reasoning_summary)s,
                %(created_by)s, %(ttl_seconds)s, %(expires_at)s, COALESCE(%(created_at)s, now()),
                COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            link.model_dump(),
        ).fetchone()
        return dict(row)

    def get_impact_link(self, conn: Connection, impact_link_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM impact_links WHERE impact_link_id = %s", (impact_link_id,)).fetchone()
        return dict(row) if row else None

    def list_signal_market_links(self, conn: Connection, signal_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM signal_market_links
            WHERE signal_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (signal_id, limit),
        ).fetchall()

    def list_signal_position_links(self, conn: Connection, signal_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM signal_position_links
            WHERE signal_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (signal_id, limit),
        ).fetchall()

    def list_market_impacts(self, conn: Connection, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM impact_links
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

    def list_position_impacts(self, conn: Connection, position_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM impact_links
            WHERE position_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (position_id, limit),
        ).fetchall()

    def list_unlinked_signals(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT s.*
            FROM neuron_signals s
            LEFT JOIN signal_market_links sml ON sml.signal_id = s.signal_id
            LEFT JOIN signal_position_links spl ON spl.signal_id = s.signal_id
            WHERE sml.id IS NULL
              AND spl.id IS NULL
            ORDER BY s.created_at DESC, s.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def signal_exists(self, conn: Connection, signal_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM neuron_signals WHERE signal_id = %s", (signal_id,)).fetchone()
        return row is not None

    def entity_exists(self, conn: Connection, entity_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM event_entities WHERE entity_id = %s", (entity_id,)).fetchone()
        return row is not None

    def thesis_exists(self, conn: Connection, thesis_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM position_thesis_profiles WHERE thesis_id = %s", (thesis_id,)).fetchone()
        return row is not None

    def brain_output_exists(self, conn: Connection, brain_output_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM brain_outputs WHERE brain_output_id = %s", (brain_output_id,)).fetchone()
        return row is not None

    def coordinator_decision_exists(self, conn: Connection, coordinator_decision_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM coordinator_decisions WHERE coordinator_decision_id = %s",
            (coordinator_decision_id,),
        ).fetchone()
        return row is not None

    def summary(self, conn: Connection, *, limit: int = 10) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM event_entities) AS entities_total,
                (SELECT COUNT(*) FROM signal_market_links) AS signal_market_links_total,
                (SELECT COUNT(*) FROM signal_position_links) AS signal_position_links_total,
                (SELECT COUNT(*) FROM impact_links) AS impact_links_total,
                (SELECT COUNT(*) FROM position_thesis_profiles) AS positions_with_thesis,
                (
                    SELECT COUNT(*)
                    FROM neuron_signals s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM signal_market_links sml WHERE sml.signal_id = s.signal_id
                    )
                ) AS signals_without_market_link,
                (
                    SELECT COUNT(*)
                    FROM neuron_signals s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM signal_market_links sml WHERE sml.signal_id = s.signal_id
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM signal_position_links spl WHERE spl.signal_id = s.signal_id
                    )
                ) AS unlinked_signals
            """
        ).fetchone()
        links_by_status = conn.execute(
            """
            SELECT link_status, COUNT(*) AS count
            FROM (
                SELECT link_status FROM entity_market_links
                UNION ALL
                SELECT link_status FROM signal_market_links
                UNION ALL
                SELECT link_status FROM signal_position_links
            ) links
            GROUP BY link_status
            ORDER BY count DESC, link_status ASC
            """
        ).fetchall()
        impacts_by_direction = conn.execute(
            """
            SELECT impact_direction, COUNT(*) AS count
            FROM impact_links
            GROUP BY impact_direction
            ORDER BY count DESC, impact_direction ASC
            """
        ).fetchall()
        cortex_action_hints = conn.execute(
            """
            SELECT cortex_action_hint, COUNT(*) AS count
            FROM impact_links
            GROUP BY cortex_action_hint
            ORDER BY count DESC, cortex_action_hint ASC
            """
        ).fetchall()
        latest_impacts = conn.execute(
            """
            SELECT *
            FROM impact_links
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return {
            "entities_total": int(totals["entities_total"] or 0),
            "signal_market_links_total": int(totals["signal_market_links_total"] or 0),
            "signal_position_links_total": int(totals["signal_position_links_total"] or 0),
            "impact_links_total": int(totals["impact_links_total"] or 0),
            "unlinked_signals": int(totals["unlinked_signals"] or 0),
            "links_by_status": [dict(row) for row in links_by_status],
            "impacts_by_direction": [dict(row) for row in impacts_by_direction],
            "cortex_action_hints": [dict(row) for row in cortex_action_hints],
            "latest_impacts": [dict(row) for row in latest_impacts],
            "positions_with_thesis": int(totals["positions_with_thesis"] or 0),
            "signals_without_market_link": int(totals["signals_without_market_link"] or 0),
        }


def _entity_params(entity: EventEntity) -> dict[str, Any]:
    data = entity.model_dump()
    data["metadata_json"] = Jsonb(json.loads(json.dumps(data.pop("metadata", {}) or {}, default=str)))
    return data


def _thesis_params(thesis: PositionThesisProfile) -> dict[str, Any]:
    data = thesis.model_dump()
    for field in (
        "profit_drivers",
        "invalidation_drivers",
        "watch_entities",
        "danger_signals",
        "take_profit_rules",
        "partial_exit_rules",
        "emergency_exit_rules",
    ):
        data[f"{field}_json"] = Jsonb(json.loads(json.dumps(data.pop(field, []) or [], default=str)))
    return data
