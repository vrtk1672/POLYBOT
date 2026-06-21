from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.ai_brain.redaction import redact_dict, redact_text
from app.db.connection import DatabaseConnectionFactory
from app.neural_bus.repository import table_exists
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.repositories.ai_request_repository import AIRequestRepository
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.system_power import SystemPowerService


DEFAULT_PROVIDER_ORDER = ("ollama", "openai", "anthropic")
DEFAULT_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"


class AIContextHttpClient(Protocol):
    def post_json(
        self,
        url: str,
        *,
        json_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[Any, int]:
        ...


class HttpxAIContextClient:
    def post_json(
        self,
        url: str,
        *,
        json_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[Any, int]:
        started = time.perf_counter()
        with httpx.Client(timeout=timeout_seconds or _provider_timeout_seconds(), follow_redirects=True) as client:
            response = client.post(url, json=json_payload, headers=headers)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


@dataclass(frozen=True)
class AIContextRouterConfig:
    provider_order: tuple[str, ...]
    provider_timeout_seconds: float
    total_timeout_seconds: float
    max_prompt_chars: int
    max_response_tokens: int
    cloud_fallback_enabled: bool
    ai_required: bool
    ollama_timeout_fast_seconds: float = 60.0
    ollama_timeout_primary_seconds: float = 90.0
    ollama_timeout_reasoning_seconds: float = 120.0


class AIContextRouterService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        neural_bus: NeuralEventBusService | None = None,
        http_client: AIContextHttpClient | None = None,
        config: AIContextRouterConfig | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._bus = neural_bus or NeuralEventBusService(connection_factory=self._factory, system_power=self._system_power)
        self._http = http_client or HttpxAIContextClient()
        self._config = config or _config_from_env()
        self._ai_requests = AIRequestRepository()
        self._source_status = SourceStatusRepository()

    def route_context(
        self,
        *,
        prompt: str,
        source_component: str = "AI Context Brain",
        correlation_id: str | None = None,
        market_id: str | None = None,
        candidate_id: str | None = None,
        session_id: str | None = None,
        source_to_neuron: bool = False,
        enabled: bool = True,
        cloud_fallback_enabled: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        started_at = datetime.now(UTC)
        run_id = correlation_id or f"ai_context_router_{uuid4().hex}"
        bounded_prompt = _bounded_prompt(prompt, self._config.max_prompt_chars)
        prompt_hash = _digest(bounded_prompt)
        provider_order = self._config.provider_order
        cloud_allowed = self._config.cloud_fallback_enabled if cloud_fallback_enabled is None else bool(cloud_fallback_enabled)
        attempts: list[dict[str, Any]] = []

        if not enabled:
            result = self._finish_without_provider(
                run_id=run_id,
                source_component=source_component,
                status="DISABLED_BY_POLICY",
                final_reason="AI_CONTEXT_ROUTER_DISABLED_BY_POLICY",
                provider_order=provider_order,
                attempts=attempts,
                prompt_hash=prompt_hash,
                started_at=started_at,
                started=started,
                market_id=market_id,
                candidate_id=candidate_id,
                session_id=session_id,
                metadata=metadata,
            )
            return result

        power = self._system_power.get_power_state()
        if str(power.get("power") or "OFF").upper() != "ON" or not power.get("runtime_work_allowed"):
            return {
                "mock_data": False,
                "status": "SYSTEM_POWER_OFF",
                "run_id": run_id,
                "selected_provider": None,
                "final_reason": "SYSTEM_POWER_OFF",
                "providers_attempted": [],
                "runtime_continues": True,
                "secrets_exposed": False,
            }

        final_reason = "NO_PROVIDER_ATTEMPTED"
        for provider in provider_order:
            if provider in {"openai", "anthropic"} and not cloud_allowed:
                attempts.append({"provider": provider, "status": "SKIPPED", "reason": "CLOUD_FALLBACK_DISABLED"})
                continue
            elapsed = time.perf_counter() - started
            if elapsed >= self._config.total_timeout_seconds:
                final_reason = "AI_CONTEXT_TOTAL_TIMEOUT"
                attempts.append({"provider": provider, "status": "SKIPPED", "reason": final_reason})
                break
            try:
                attempt = self._attempt_provider(provider, prompt=bounded_prompt, remaining_seconds=max(0.1, self._config.total_timeout_seconds - elapsed))
                attempts.append(attempt)
                if attempt.get("status") == "OK":
                    return self._record_success(
                        run_id=run_id,
                        source_component=source_component,
                        provider_order=provider_order,
                        selected_provider=provider,
                        attempt=attempt,
                        attempts=attempts,
                        prompt=bounded_prompt,
                        prompt_hash=prompt_hash,
                        started_at=started_at,
                        started=started,
                        market_id=market_id,
                        candidate_id=candidate_id,
                        session_id=session_id,
                        source_to_neuron=source_to_neuron,
                        metadata=metadata,
                    )
                final_reason = str(attempt.get("reason") or f"{provider.upper()}_ERROR")
            except Exception as exc:
                reason = _classify_error(provider, exc)
                attempts.append({"provider": provider, "status": "FAILED", "reason": reason, "error_summary": _safe_error(exc)})
                final_reason = reason

        return self._record_unavailable(
            run_id=run_id,
            source_component=source_component,
            provider_order=provider_order,
            final_reason=final_reason,
            attempts=attempts,
            prompt_hash=prompt_hash,
            started_at=started_at,
            started=started,
            market_id=market_id,
            candidate_id=candidate_id,
            session_id=session_id,
            source_to_neuron=source_to_neuron,
            metadata=metadata,
        )

    def dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_dashboard("DB_UNAVAILABLE", self._config)
        with self._factory.connect() as conn:
            if not table_exists(conn, "ai_context_router_runs"):
                return _empty_dashboard("MISSING_TABLES", self._config)
            latest = [
                _json_safe(dict(row))
                for row in conn.execute(
                    """
                    SELECT *
                    FROM ai_context_router_runs
                    ORDER BY finished_at DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            ]
            counts = {
                str(row["status"]): int(row["count"] or 0)
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM ai_context_router_runs GROUP BY status"
                ).fetchall()
            }
            fallback_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM ai_context_router_runs
                    WHERE selected_provider IN ('openai', 'anthropic')
                    """
                ).fetchone()["count"]
                or 0
            )
            timeout_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM ai_context_router_runs
                    WHERE providers_attempted_json::text ILIKE '%%TIMEOUT%%'
                    """
                ).fetchone()["count"]
                or 0
            )
        latest_run = latest[0] if latest else None
        return {
            "mock_data": False,
            "status": "OK",
            "generated_at": datetime.now(UTC).isoformat(),
            "latest_status": latest_run.get("status") if latest_run else "NO_RUNS",
            "ai_required": self._config.ai_required,
            "selected_provider": latest_run.get("selected_provider") if latest_run else None,
            "provider_order": list(self._config.provider_order),
            "ollama_status": _provider_status_from_latest(latest, "ollama"),
            "openai_status": _provider_status_from_latest(latest, "openai"),
            "anthropic_status": _provider_status_from_latest(latest, "anthropic"),
            "fallback_count": fallback_count,
            "timeout_count": timeout_count,
            "success_count": counts.get("OK", 0),
            "unavailable_count": counts.get("AI_CONTEXT_UNAVAILABLE", 0),
            "latest_runs": latest,
            "secrets_exposed": False,
        }

    def _attempt_provider(self, provider: str, *, prompt: str, remaining_seconds: float) -> dict[str, Any]:
        timeout_seconds = min(self._config.provider_timeout_seconds, remaining_seconds)
        if provider == "ollama":
            return self._attempt_ollama(prompt=prompt, remaining_seconds=remaining_seconds)
        if provider == "openai":
            return self._attempt_openai(prompt=prompt, timeout_seconds=timeout_seconds)
        if provider == "anthropic":
            return self._attempt_anthropic(prompt=prompt, timeout_seconds=timeout_seconds)
        return {"provider": provider, "status": "FAILED", "reason": "AI_PROVIDER_UNKNOWN"}

    def _attempt_ollama(self, *, prompt: str, remaining_seconds: float) -> dict[str, Any]:
        base_url = os.getenv("OLLAMA_BASE_URL")
        models = _ollama_generation_models()
        if not base_url or not models:
            return {"provider": "ollama", "status": "FAILED", "reason": "OLLAMA_MODEL_MISSING", "models_checked": models}
        last_reason = "OLLAMA_ERROR"
        checked: list[dict[str, Any]] = []
        for endpoint_base in _ollama_bases(base_url):
            for model in models:
                payload = {
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "think": False,
                        "keep_alive": _ollama_keep_alive(),
                        "options": {
                            "temperature": 0,
                            "num_predict": min(self._config.max_response_tokens, 48),
                            "num_ctx": 512,
                    },
                }
                try:
                    timeout_seconds = min(_ollama_timeout_for_model(self._config, model), remaining_seconds)
                    checked.append({"endpoint": _safe_endpoint_label(endpoint_base), "model": model, "timeout_seconds": timeout_seconds})
                    raw, latency_ms = _post_json(self._http, f"{endpoint_base}/api/generate", json_payload=payload, timeout_seconds=timeout_seconds)
                    text = _extract_ollama_text(raw)
                    return _success_attempt("ollama", model, text, latency_ms)
                except Exception as exc:
                    last_reason = _classify_error("ollama", exc)
                    checked[-1]["reason"] = last_reason
                    continue
        return {"provider": "ollama", "status": "FAILED", "reason": last_reason, "attempts": checked}

    def _attempt_openai(self, *, prompt: str, timeout_seconds: float) -> dict[str, Any]:
        key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("AI_CONTEXT_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        if not key:
            return {"provider": "openai", "status": "FAILED", "reason": "OPENAI_AUTH_ERROR"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": self._config.max_response_tokens,
        }
        raw, latency_ms = _post_json(
            self._http,
            os.getenv("AI_CONTEXT_OPENAI_ENDPOINT") or DEFAULT_OPENAI_ENDPOINT,
            json_payload=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout_seconds=timeout_seconds,
        )
        text = _extract_openai_text(raw)
        return _success_attempt("openai", model, text, latency_ms)

    def _attempt_anthropic(self, *, prompt: str, timeout_seconds: float) -> dict[str, Any]:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            return {"provider": "anthropic", "status": "FAILED", "reason": "ANTHROPIC_AUTH_ERROR"}
        last_reason = "ANTHROPIC_DEGRADED"
        checked: list[dict[str, Any]] = []
        for model in _anthropic_generation_models():
            payload = {
                "model": model,
                "max_tokens": self._config.max_response_tokens,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }
            try:
                raw, latency_ms = _post_json(
                    self._http,
                    os.getenv("AI_CONTEXT_ANTHROPIC_ENDPOINT") or DEFAULT_ANTHROPIC_ENDPOINT,
                    json_payload=payload,
                    headers={
                        "x-api-key": key,
                        "anthropic-version": os.getenv("ANTHROPIC_VERSION") or "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    timeout_seconds=timeout_seconds,
                )
                text = _extract_anthropic_text(raw)
                attempt = _success_attempt("anthropic", model, text, latency_ms)
                if checked:
                    attempt["model_attempts"] = checked
                return attempt
            except Exception as exc:
                last_reason = _classify_error("anthropic", exc)
                checked.append({"model": model, "reason": last_reason})
                if last_reason in {"ANTHROPIC_AUTH_ERROR", "ANTHROPIC_TIMEOUT"}:
                    break
                continue
        return {"provider": "anthropic", "status": "FAILED", "reason": last_reason, "model_attempts": checked}

    def _record_success(
        self,
        *,
        run_id: str,
        source_component: str,
        provider_order: tuple[str, ...],
        selected_provider: str,
        attempt: dict[str, Any],
        attempts: list[dict[str, Any]],
        prompt: str,
        prompt_hash: str,
        started_at: datetime,
        started: float,
        market_id: str | None,
        candidate_id: str | None,
        session_id: str | None,
        source_to_neuron: bool,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        text = str(attempt.get("raw_output_redacted") or "")
        structured = _parse_ai_response(text)
        ai_request_id = f"ai_req_context_router_{_digest(run_id + selected_provider)[:24]}"
        ai_response_id = f"ai_resp_context_router_{_digest(run_id + text)[:24]}"
        response_hash = _digest(text)
        latency_ms = int((time.perf_counter() - started) * 1000)
        event: dict[str, Any] | None = None
        with self._factory.connect() as conn, conn.transaction():
            self._ai_requests.insert_request(
                conn,
                ai_request_id=ai_request_id,
                request_hash=prompt_hash,
                correlation_id=run_id,
                source_service=source_component,
                task_type="CONTEXT_SUMMARY",
                model_route="LOCAL_FAST" if selected_provider == "ollama" else "CLOUD_FALLBACK",
                selected_model=str(attempt.get("model") or selected_provider),
                status="PENDING",
                market_id=market_id,
                budget_allowed=True,
                escalation_requested=selected_provider != "ollama",
                escalation_allowed=selected_provider != "ollama",
                metadata={"provider": selected_provider, "source_to_neuron": source_to_neuron, "router_run_id": run_id},
            )
            self._ai_requests.finish_request(
                conn,
                ai_request_id=ai_request_id,
                status="LOCAL_COMPLETED" if selected_provider == "ollama" else "CLOUD_COMPLETED",
                latency_ms=latency_ms,
                input_tokens=max(1, len(prompt) // 4),
                output_tokens=max(1, len(text) // 4),
            )
            self._ai_requests.insert_response(
                conn,
                ai_response_id=ai_response_id,
                ai_request_id=ai_request_id,
                response_hash=response_hash,
                model_name=str(attempt.get("model") or selected_provider),
                task_type="CONTEXT_SUMMARY",
                structured_output=structured,
                raw_output_redacted=redact_text(text),
                confidence=float(structured.get("confidence") or 0.5),
                recommended_action="OBSERVE",
                risk_flags=[],
                metadata={"provider": selected_provider, "source_to_neuron": source_to_neuron, "router_run_id": run_id},
            )
            self._insert_decision_log(
                conn,
                run_id=run_id,
                ai_request_id=ai_request_id,
                market_id=market_id,
                task_type="CONTEXT_SUMMARY",
                decision_type="AI_CONTEXT_UPDATED",
                output={
                    "provider": selected_provider,
                    "summary": structured.get("summary"),
                    "confidence": structured.get("confidence", 0.5),
                    "source_refs": [{"source_table": "ai_responses", "source_record_id": ai_response_id}],
                },
                confidence=float(structured.get("confidence") or 0.5),
                risk_flags=[],
                cannot_trade_reason="AI_CONTEXT_IS_SUPPORTING_EVIDENCE_ONLY",
                metadata={"router_run_id": run_id, "source_to_neuron": source_to_neuron},
            )
            self._insert_router_run(
                conn,
                run_id=run_id,
                source_component=source_component,
                session_id=session_id,
                market_id=market_id,
                candidate_id=candidate_id,
                provider_order=provider_order,
                selected_provider=selected_provider,
                status="OK",
                final_reason="AI_CONTEXT_UPDATED",
                attempts=attempts,
                started_at=started_at,
                latency_ms=latency_ms,
                prompt_hash=prompt_hash,
                response_hash=response_hash,
                metadata=metadata,
            )
            self._upsert_source_status(
                conn,
                selected_provider=selected_provider,
                status="ACTIVE",
                latency_ms=latency_ms,
                notes="AI context router completed with first successful provider.",
                attempts=attempts,
            )

        event = self._bus.publish_event(
            NeuralEventType.AI_CONTEXT_UPDATED,
            source_component=source_component,
            source_type="brain",
            market_id=market_id,
            candidate_id=candidate_id,
            payload={
                "provider": selected_provider,
                "model": attempt.get("model"),
                "status": "COMPLETED",
                "summary": structured.get("summary"),
                "confidence": structured.get("confidence", 0.5),
                "attempts": _safe_attempts(attempts),
                "source_refs": [{"source_table": "ai_responses", "source_record_id": ai_response_id}],
            },
            source_table="ai_responses",
            source_record_id=ai_response_id,
            correlation_id=run_id,
            metadata={"source_to_neuron": source_to_neuron, "provider": selected_provider, "router": "ai_context_fallback"},
        )
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "run_id": run_id,
                "selected_provider": selected_provider,
                "final_reason": "AI_CONTEXT_UPDATED",
                "providers_attempted": _safe_attempts(attempts),
                "event": event,
                "ai_request_id": ai_request_id,
                "ai_response_id": ai_response_id,
                "latency_ms": latency_ms,
                "secrets_exposed": False,
            }
        )

    def _record_unavailable(
        self,
        *,
        run_id: str,
        source_component: str,
        provider_order: tuple[str, ...],
        final_reason: str,
        attempts: list[dict[str, Any]],
        prompt_hash: str,
        started_at: datetime,
        started: float,
        market_id: str | None,
        candidate_id: str | None,
        session_id: str | None,
        source_to_neuron: bool,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        latency_ms = int((time.perf_counter() - started) * 1000)
        with self._factory.connect() as conn, conn.transaction():
            self._insert_router_run(
                conn,
                run_id=run_id,
                source_component=source_component,
                session_id=session_id,
                market_id=market_id,
                candidate_id=candidate_id,
                provider_order=provider_order,
                selected_provider=None,
                status="AI_CONTEXT_UNAVAILABLE",
                final_reason=final_reason,
                attempts=attempts,
                started_at=started_at,
                latency_ms=latency_ms,
                prompt_hash=prompt_hash,
                response_hash=None,
                metadata=metadata,
            )
            self._insert_decision_log(
                conn,
                run_id=run_id,
                ai_request_id=None,
                market_id=market_id,
                task_type="CONTEXT_SUMMARY",
                decision_type="AI_CONTEXT_UNAVAILABLE",
                output={"final_reason": final_reason, "attempts": _safe_attempts(attempts)},
                confidence=None,
                risk_flags=["AI_DEGRADED"],
                cannot_trade_reason="AI_CONTEXT_UNAVAILABLE_RUNTIME_CONTINUES",
                metadata={"router_run_id": run_id, "source_to_neuron": source_to_neuron},
            )
            self._upsert_source_status(
                conn,
                selected_provider=None,
                status="DEGRADED",
                latency_ms=latency_ms,
                notes=final_reason,
                attempts=attempts,
            )
        event = self._bus.publish_event(
            NeuralEventType.AI_CONTEXT_UNAVAILABLE,
            source_component=source_component,
            source_type="brain",
            market_id=market_id,
            candidate_id=candidate_id,
            payload={"status": "AI_CONTEXT_UNAVAILABLE", "final_reason": final_reason, "attempts": _safe_attempts(attempts), "runtime_continues": True},
            source_table="ai_context_router_runs",
            source_record_id=run_id,
            correlation_id=run_id,
            metadata={"source_to_neuron": source_to_neuron, "router": "ai_context_fallback"},
        )
        return _json_safe(
            {
                "mock_data": False,
                "status": "AI_CONTEXT_UNAVAILABLE",
                "run_id": run_id,
                "selected_provider": None,
                "final_reason": final_reason,
                "providers_attempted": _safe_attempts(attempts),
                "event": event,
                "latency_ms": latency_ms,
                "runtime_continues": True,
                "secrets_exposed": False,
            }
        )

    def _finish_without_provider(
        self,
        *,
        run_id: str,
        source_component: str,
        status: str,
        final_reason: str,
        provider_order: tuple[str, ...],
        attempts: list[dict[str, Any]],
        prompt_hash: str,
        started_at: datetime,
        started: float,
        market_id: str | None,
        candidate_id: str | None,
        session_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        latency_ms = int((time.perf_counter() - started) * 1000)
        with self._factory.connect() as conn, conn.transaction():
            self._insert_router_run(
                conn,
                run_id=run_id,
                source_component=source_component,
                session_id=session_id,
                market_id=market_id,
                candidate_id=candidate_id,
                provider_order=provider_order,
                selected_provider=None,
                status=status,
                final_reason=final_reason,
                attempts=attempts,
                started_at=started_at,
                latency_ms=latency_ms,
                prompt_hash=prompt_hash,
                response_hash=None,
                metadata=metadata,
            )
        return {
            "mock_data": False,
            "status": status,
            "run_id": run_id,
            "selected_provider": None,
            "final_reason": final_reason,
            "providers_attempted": [],
            "runtime_continues": True,
            "secrets_exposed": False,
        }

    def _insert_router_run(self, conn: Any, **kwargs: Any) -> None:
        if not table_exists(conn, "ai_context_router_runs"):
            return
        conn.execute(
            """
            INSERT INTO ai_context_router_runs (
                run_id, source_component, session_id, market_id, candidate_id,
                provider_order_json, selected_provider, status, final_reason,
                providers_attempted_json, started_at, finished_at, latency_ms,
                prompt_hash, response_hash, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                selected_provider = EXCLUDED.selected_provider,
                status = EXCLUDED.status,
                final_reason = EXCLUDED.final_reason,
                providers_attempted_json = EXCLUDED.providers_attempted_json,
                finished_at = now(),
                latency_ms = EXCLUDED.latency_ms,
                response_hash = EXCLUDED.response_hash,
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                kwargs["run_id"],
                kwargs["source_component"],
                kwargs.get("session_id"),
                kwargs.get("market_id"),
                kwargs.get("candidate_id"),
                Jsonb(list(kwargs["provider_order"])),
                kwargs.get("selected_provider"),
                kwargs["status"],
                kwargs["final_reason"],
                Jsonb(_safe_attempts(kwargs["attempts"])),
                kwargs["started_at"],
                kwargs["latency_ms"],
                kwargs["prompt_hash"],
                kwargs.get("response_hash"),
                Jsonb(redact_dict(kwargs.get("metadata") or {})),
            ),
        )

    def _insert_decision_log(
        self,
        conn: Any,
        *,
        run_id: str,
        ai_request_id: str | None,
        market_id: str | None,
        task_type: str,
        decision_type: str,
        output: dict[str, Any],
        confidence: float | None,
        risk_flags: list[str],
        cannot_trade_reason: str,
        metadata: dict[str, Any],
    ) -> None:
        if not table_exists(conn, "ai_decision_logs"):
            return
        conn.execute(
            """
            INSERT INTO ai_decision_logs (
                ai_decision_id, ai_request_id, market_id, correlation_id,
                task_type, decision_type, output_json, confidence,
                risk_flags_json, cannot_trade_reason, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ai_decision_id) DO NOTHING
            """,
            (
                f"ai_decision_context_router_{_digest(run_id + decision_type)[:24]}",
                ai_request_id,
                market_id,
                run_id,
                task_type,
                decision_type,
                Jsonb(redact_dict(output)),
                confidence,
                Jsonb(risk_flags),
                cannot_trade_reason,
                Jsonb(redact_dict(metadata)),
            ),
        )

    def _upsert_source_status(
        self,
        conn: Any,
        *,
        selected_provider: str | None,
        status: str,
        latency_ms: int,
        notes: str,
        attempts: list[dict[str, Any]],
    ) -> None:
        if not table_exists(conn, "source_status"):
            return
        self._source_status.upsert_status(
            conn,
            {
                "source_name": "ai_context_router",
                "source_type": "ai_context",
                "configured": True,
                "key_required": False,
                "key_present": bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
                "key_name": "OPENAI_API_KEY/ANTHROPIC_API_KEY",
                "endpoint_url": "local/cloud AI context providers",
                "runtime_status": status,
                "freshness_status": "FRESH" if status == "ACTIVE" else "STALE",
                "latency_ms": latency_ms,
                "details_json": {"selected_provider": selected_provider, "attempts": _safe_attempts(attempts)},
                "notes": notes,
            },
        )


def _config_from_env() -> AIContextRouterConfig:
    provider_timeout = _bounded_timeout(_float_env("AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS", 90.0), default=90.0, minimum=1.0, maximum=120.0)
    fast_timeout = _specific_ollama_timeout("FAST", provider_timeout, default=60.0)
    primary_timeout = _specific_ollama_timeout("PRIMARY", provider_timeout, default=90.0)
    reasoning_timeout = _specific_ollama_timeout("REASONING", provider_timeout, default=120.0)
    total_default = max(120.0, provider_timeout, fast_timeout, primary_timeout, reasoning_timeout)
    return AIContextRouterConfig(
        provider_order=_provider_order(),
        provider_timeout_seconds=provider_timeout,
        total_timeout_seconds=_bounded_timeout(
            _float_env("AI_CONTEXT_TOTAL_TIMEOUT_SECONDS", total_default),
            default=total_default,
            minimum=1.0,
            maximum=120.0,
        ),
        max_prompt_chars=max(64, int(_float_env("AI_CONTEXT_MAX_PROMPT_CHARS", 2000.0))),
        max_response_tokens=max(16, int(_float_env("AI_CONTEXT_MAX_RESPONSE_TOKENS", 300.0))),
        cloud_fallback_enabled=_bool_env("AI_CONTEXT_ENABLE_CLOUD_FALLBACK", True),
        ai_required=_bool_env("AI_REQUIRED", False),
        ollama_timeout_fast_seconds=fast_timeout,
        ollama_timeout_primary_seconds=primary_timeout,
        ollama_timeout_reasoning_seconds=reasoning_timeout,
    )


def _provider_order() -> tuple[str, ...]:
    raw = os.getenv("AI_CONTEXT_PROVIDER_ORDER")
    if not raw:
        return DEFAULT_PROVIDER_ORDER
    allowed = {"ollama", "openai", "anthropic"}
    providers = tuple(item.strip().lower() for item in raw.split(",") if item.strip().lower() in allowed)
    return providers or DEFAULT_PROVIDER_ORDER


def _provider_timeout_seconds() -> float:
    return _bounded_timeout(_float_env("AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS", 90.0), default=90.0, minimum=1.0, maximum=120.0)


def _specific_ollama_timeout(tier: str, global_timeout: float, *, default: float) -> float:
    specific = os.getenv(f"OLLAMA_TIMEOUT_{tier}_SECONDS")
    legacy_global = os.getenv("OLLAMA_TIMEOUT_SECONDS")
    if specific:
        raw = _float_env(f"OLLAMA_TIMEOUT_{tier}_SECONDS", default)
    elif legacy_global:
        raw = _float_env("OLLAMA_TIMEOUT_SECONDS", global_timeout)
    else:
        raw = default
    return _bounded_timeout(raw, default=default, minimum=1.0, maximum=120.0)


def _ollama_timeout_for_model(config: AIContextRouterConfig, model: str) -> float:
    models = _ollama_generation_models()
    if model == (models[0] if len(models) > 0 else None):
        return config.ollama_timeout_fast_seconds
    if model == (models[1] if len(models) > 1 else None):
        return config.ollama_timeout_primary_seconds
    if model == (models[2] if len(models) > 2 else None):
        return config.ollama_timeout_reasoning_seconds
    return min(config.provider_timeout_seconds, 120.0)


def _bounded_timeout(value: float, *, default: float, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except Exception:
        numeric = default
    if numeric < minimum:
        return default
    return min(numeric, maximum)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except Exception:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_prompt(prompt: str, max_chars: int) -> str:
    base = (prompt or "").strip()
    if not base:
        base = "Return compact JSON summarizing source-backed prediction-market context. Do not recommend trades."
    base = base[:max_chars]
    return (
        "You are POLYBOT AI Context Brain. AI is supporting evidence only and cannot create trades or bypass Risk, Exit, "
        "Capital, Coordinator, or State Governor. Return only the final answer as compact JSON with keys status, summary, confidence. "
        "Do not include hidden reasoning, analysis preambles, markdown, trades, intents, orders, fills, positions, fake opportunities, or fake PnL. "
        "If data is missing, say missing.\n\n"
        f"Source-backed input:\n{base}"
    )[:max_chars]


def _ollama_bases(base_url: str) -> list[str]:
    normalized = base_url.rstrip("/")
    if normalized in {"http://localhost:11434", "http://127.0.0.1:11434"}:
        host_base = "http://host.docker.internal:11434"
        if Path("/.dockerenv").exists():
            return [host_base, normalized]
        return [normalized, host_base]
    return [normalized]


def _ollama_keep_alive() -> str:
    return os.getenv("AI_CONTEXT_OLLAMA_KEEP_ALIVE") or os.getenv("OLLAMA_KEEP_ALIVE") or "5m"


def _ollama_generation_models() -> list[str]:
    configured = (
        os.getenv("OLLAMA_MODEL_FAST"),
        os.getenv("OLLAMA_MODEL_PRIMARY"),
        os.getenv("OLLAMA_MODEL_REASONING"),
    )
    return list(dict.fromkeys(str(item).strip() for item in configured if str(item or "").strip()))


def _anthropic_generation_models() -> list[str]:
    configured = (
        os.getenv("AI_CONTEXT_ANTHROPIC_MODEL"),
        os.getenv("ANTHROPIC_MODEL"),
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6",
        "claude-3-5-haiku-latest",
        "claude-3-haiku-20240307",
    )
    return list(dict.fromkeys(str(item).strip() for item in configured if str(item or "").strip()))


def _extract_ollama_text(raw: Any) -> str:
    if isinstance(raw, dict):
        response = raw.get("response")
        if response:
            return str(response)
        thinking = raw.get("thinking")
        if thinking:
            return str(thinking)
    return str(raw)


def _post_json(
    client: AIContextHttpClient,
    url: str,
    *,
    json_payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[Any, int]:
    try:
        return client.post_json(url, json_payload=json_payload, headers=headers, timeout_seconds=timeout_seconds)
    except TypeError:
        return client.post_json(url, json_payload=json_payload, headers=headers)


def _success_attempt(provider: str, model: str, text: str, latency_ms: int) -> dict[str, Any]:
    cleaned = _clean_operator_ai_output(text)
    return {
        "provider": provider,
        "status": "OK",
        "reason": "COMPLETED",
        "model": model,
        "latency_ms": latency_ms,
        "raw_output_redacted": redact_text(cleaned),
        "response_hash": _digest(cleaned),
    }


def _extract_openai_text(payload: Any) -> str:
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                return str(message.get("content") or "")
    return str(payload)


def _extract_anthropic_text(payload: Any) -> str:
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "\n".join(part for part in parts if part)
    return str(payload)


def _parse_ai_response(text: str) -> dict[str, Any]:
    text = _clean_operator_ai_output(text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            safe = redact_dict(parsed)
            safe.setdefault("status", "OK")
            safe.setdefault("confidence", 0.5)
            return safe
    except Exception:
        pass
    extracted = _extract_first_json_object(text)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                safe = redact_dict(parsed)
                safe.setdefault("status", "OK")
                safe.setdefault("confidence", 0.5)
                return safe
        except Exception:
            pass
    return {"status": "OK", "summary": redact_text(text), "confidence": 0.5}


def _clean_operator_ai_output(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return cleaned
    extracted = _extract_first_json_object(cleaned)
    if extracted:
        return extracted
    lower = cleaned.lower()
    preamble_markers = (
        "\nfinal answer:",
        "\nfinal:",
        "\nanswer:",
        "\njson:",
        "\noutput:",
    )
    for marker in preamble_markers:
        index = lower.rfind(marker)
        if index >= 0:
            candidate = cleaned[index + len(marker) :].strip()
            if candidate:
                return candidate
    reasoning_starts = (
        "okay, the user",
        "ok, the user",
        "the user wants",
        "we need",
        "we are to",
        "let's think",
        "hmm,",
        "first, i",
        "i need to",
    )
    if lower.startswith(reasoning_starts):
        paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
        for paragraph in reversed(paragraphs):
            para_lower = paragraph.lower()
            if not para_lower.startswith(reasoning_starts):
                return paragraph
    return cleaned


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1].strip()
    return None


def _classify_error(provider: str, exc: Exception) -> str:
    name = provider.upper()
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return f"{name}_TIMEOUT"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if provider == "openai" and code == 429:
            body = ""
            try:
                body = exc.response.text.lower()
            except Exception:
                body = ""
            if "insufficient_quota" in body or "exceeded your current quota" in body:
                return "OPENAI_QUOTA_EXCEEDED"
            return "OPENAI_RATE_LIMITED"
        if code in {401, 403}:
            return f"{name}_AUTH_ERROR"
        if provider == "ollama" and code == 404:
            return "OLLAMA_MODEL_MISSING"
        if provider == "anthropic" and code == 404:
            return "ANTHROPIC_DEGRADED"
    text = str(exc).lower()
    if provider == "openai" and ("insufficient_quota" in text or "exceeded your current quota" in text):
        return "OPENAI_QUOTA_EXCEEDED"
    if provider == "openai" and ("429" in text or "rate limit" in text or "too many requests" in text):
        return "OPENAI_RATE_LIMITED"
    if provider == "anthropic" and ("404" in text or "not found" in text):
        return "ANTHROPIC_DEGRADED"
    if "timeout" in text or "timed out" in text:
        return f"{name}_TIMEOUT"
    if "401" in text or "403" in text or "auth" in text or "api key" in text:
        return f"{name}_AUTH_ERROR"
    if provider == "ollama" and ("model" in text and ("missing" in text or "not found" in text)):
        return "OLLAMA_MODEL_MISSING"
    return f"{name}_ERROR"


def _safe_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for attempt in attempts:
        item = redact_dict({key: value for key, value in attempt.items() if key not in {"raw_output_redacted"}})
        if "endpoint" in item:
            item["endpoint"] = _safe_endpoint_label(str(item["endpoint"]))
        safe.append(item)
    return safe


def _safe_endpoint_label(value: str) -> str:
    return value.replace(os.getenv("OPENAI_API_KEY") or "__never__", "[REDACTED]").replace(os.getenv("ANTHROPIC_API_KEY") or "__never__", "[REDACTED]")


def _safe_error(exc: Exception) -> str:
    return redact_text(str(exc))[:300]


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _provider_status_from_latest(latest: list[dict[str, Any]], provider: str) -> dict[str, Any]:
    for run in latest:
        for attempt in run.get("providers_attempted_json") or []:
            if attempt.get("provider") == provider:
                return {"status": attempt.get("status"), "reason": attempt.get("reason"), "last_run_id": run.get("run_id")}
    return {"status": "NO_RUNS", "reason": None, "last_run_id": None}


def _empty_dashboard(status: str, config: AIContextRouterConfig) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "latest_status": "NO_RUNS",
        "ai_required": config.ai_required,
        "selected_provider": None,
        "provider_order": list(config.provider_order),
        "ollama_status": {"status": "NO_RUNS"},
        "openai_status": {"status": "NO_RUNS"},
        "anthropic_status": {"status": "NO_RUNS"},
        "fallback_count": 0,
        "timeout_count": 0,
        "success_count": 0,
        "unavailable_count": 0,
        "latest_runs": [],
        "secrets_exposed": False,
    }
