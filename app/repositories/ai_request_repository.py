from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class AIRequestRepository:
    def insert_request(
        self,
        conn: Connection,
        *,
        ai_request_id: str,
        request_hash: str,
        correlation_id: str,
        source_service: str,
        task_type: str,
        model_route: str,
        status: str,
        market_id: str | None = None,
        event_id: str | None = None,
        selected_model: str | None = None,
        prompt_version_id: str | None = None,
        cache_key: str | None = None,
        cache_hit: bool = False,
        budget_allowed: bool = False,
        escalation_requested: bool = False,
        escalation_allowed: bool = False,
        estimated_cost: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ai_requests (
                ai_request_id, request_hash, market_id, event_id, correlation_id,
                source_service, task_type, model_route, selected_model, prompt_version_id,
                cache_key, cache_hit, budget_allowed, escalation_requested,
                escalation_allowed, status, estimated_cost, request_metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ai_request_id) DO NOTHING
            """,
            (
                ai_request_id,
                request_hash,
                market_id,
                event_id,
                correlation_id,
                source_service,
                task_type,
                model_route,
                selected_model,
                prompt_version_id,
                cache_key,
                cache_hit,
                budget_allowed,
                escalation_requested,
                escalation_allowed,
                status,
                estimated_cost,
                Jsonb(metadata or {}),
            ),
        )

    def finish_request(
        self,
        conn: Connection,
        *,
        ai_request_id: str,
        status: str,
        latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        estimated_cost: float = 0.0,
        error_message: str | None = None,
    ) -> None:
        conn.execute(
            """
            UPDATE ai_requests
            SET status = %s,
                finished_at = now(),
                latency_ms = %s,
                input_tokens = %s,
                output_tokens = %s,
                estimated_cost = %s,
                error_message = %s
            WHERE ai_request_id = %s
            """,
            (status, latency_ms, input_tokens, output_tokens, estimated_cost, error_message, ai_request_id),
        )

    def insert_response(
        self,
        conn: Connection,
        *,
        ai_response_id: str,
        ai_request_id: str,
        response_hash: str,
        model_name: str,
        task_type: str,
        structured_output: dict[str, Any],
        raw_output_redacted: str | None = None,
        confidence: float | None = None,
        recommended_action: str | None = None,
        risk_flags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ai_responses (
                ai_response_id, ai_request_id, response_hash, model_name, task_type,
                structured_output_json, raw_output_redacted, confidence,
                recommended_action, risk_flags_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ai_response_id) DO NOTHING
            """,
            (
                ai_response_id,
                ai_request_id,
                response_hash,
                model_name,
                task_type,
                Jsonb(structured_output),
                raw_output_redacted,
                confidence,
                recommended_action,
                Jsonb(risk_flags or []),
                Jsonb(metadata or {}),
            ),
        )

    def insert_escalation(
        self,
        conn: Connection,
        *,
        escalation_id: str,
        ai_request_id: str,
        task_type: str,
        to_model: str,
        reason: str,
        market_id: str | None = None,
        from_model: str | None = None,
        local_confidence: float | None = None,
        escalation_allowed: bool = False,
        status: str = "PENDING",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ai_escalations (
                escalation_id, ai_request_id, market_id, task_type, from_model,
                to_model, reason, local_confidence, escalation_allowed, status,
                completed_at, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s IN ('COMPLETED','FAILED','BLOCKED') THEN now() ELSE NULL END, %s)
            ON CONFLICT (escalation_id) DO NOTHING
            """,
            (
                escalation_id,
                ai_request_id,
                market_id,
                task_type,
                from_model,
                to_model,
                reason,
                local_confidence,
                escalation_allowed,
                status,
                status,
                Jsonb(metadata or {}),
            ),
        )

    def list_escalations(
        self,
        conn: Connection,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if status:
            return conn.execute(
                "SELECT * FROM ai_escalations WHERE status = %s ORDER BY created_at DESC, id DESC LIMIT %s",
                (status, limit),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM ai_escalations ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()
