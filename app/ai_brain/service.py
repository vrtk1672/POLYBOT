from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.ai_brain.budget_governor import AIBudgetGovernor
from app.ai_brain.cache import AICache, stable_hash
from app.ai_brain.case_file_builder import AICaseFileBuilder
from app.ai_brain.cloud_escalation_worker import CloudEscalationWorker
from app.ai_brain.contracts import AICaseFile, AIRequest, AIResponse, AITaskType
from app.ai_brain.cost_ledger import AICostLedger
from app.ai_brain.decision_log import AIDecisionLog
from app.ai_brain.local_ai_worker import AIWorkerResult, LocalAIWorker
from app.ai_brain.model_performance import AIModelPerformanceTracker
from app.ai_brain.model_router import AIModelRouter
from app.ai_brain.prompt_versions import PromptVersionRegistry
from app.ai_brain.redaction import redact_dict, redact_text
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.ai_request_repository import AIRequestRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class HybridAIBrainService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        local_worker: LocalAIWorker | None = None,
        cloud_worker: CloudEscalationWorker | None = None,
        state_governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._cache = AICache(connection_factory=self._factory)
        self._budget = AIBudgetGovernor(connection_factory=self._factory)
        self._router = AIModelRouter()
        self._prompt_versions = PromptVersionRegistry(connection_factory=self._factory)
        self._case_files = AICaseFileBuilder(connection_factory=self._factory)
        self._local_worker = local_worker or LocalAIWorker()
        self._cloud_worker = cloud_worker or CloudEscalationWorker(connection_factory=self._factory)
        self._costs = AICostLedger(connection_factory=self._factory)
        self._decisions = AIDecisionLog(connection_factory=self._factory)
        self._performance = AIModelPerformanceTracker(connection_factory=self._factory)
        self._requests = AIRequestRepository()
        self._state_governor = state_governor or StateGovernor(connection_factory=self._factory)

    def analyze(self, request: AIRequest, *, allow_cloud: bool = False, reason: str = "ai analysis") -> AIResponse:
        started = time.perf_counter()
        ai_request_id = f"ai_req_{uuid4().hex}"
        if not self._runtime_allows_analysis(allow_cloud=allow_cloud):
            response = self._blocked_response(ai_request_id, request, "runtime_mode_blocks_ai")
            self._store_request_and_response(
                request=request,
                response=response,
                ai_request_id=ai_request_id,
                request_hash=stable_hash(request.safe_payload()),
                model_route="blocked",
                status="BUDGET_BLOCKED",
                budget_allowed=False,
                cache_key=None,
                latency_ms=_elapsed_ms(started),
            )
            return response

        case_file = self._build_case_file_if_possible(request)
        prompt = self._prompt_versions.get_active_prompt(request.task_type)
        route = self._router.route(
            request.task_type,
            allow_cloud=allow_cloud,
            data_completeness_score=case_file.data_completeness_score if case_file else None,
            budget_cloud_allowed=False,
            case_file=case_file,
        )
        input_payload = self._build_model_input(request, case_file)
        request_hash = stable_hash({"task_type": request.task_type.value, "input": input_payload, "prompt": prompt.prompt_version_id})
        cache_key = self._cache.build_cache_key(
            task_type=request.task_type,
            market_id=request.market_id,
            input_hash=request_hash,
            prompt_version_id=prompt.prompt_version_id,
            model_name=route.selected_model,
            extra_hashes={
                "case_file": stable_hash(case_file.compact_dict()) if case_file else None,
            },
        )
        cached = self._cache.get_cached_response(cache_key) if self._cache.should_use_cache(request.task_type) else None
        if cached:
            response = AIResponse(**cached["response_json"])
            response.ai_request_id = ai_request_id
            self._store_request_and_response(
                request=request,
                response=response,
                ai_request_id=ai_request_id,
                request_hash=request_hash,
                model_route=route.selected_tier.value,
                status="CACHE_HIT",
                cache_key=cache_key,
                cache_hit=True,
                budget_allowed=False,
                latency_ms=_elapsed_ms(started),
            )
            self._publish(EventType.AI_CACHE_HIT.value, {"ai_request_id": ai_request_id, "task_type": request.task_type.value}, request)
            return response

        budget = self._budget.evaluate(
            task_type=request.task_type,
            case_file=case_file,
            cloud_requested=allow_cloud,
            estimated_cost=0.0,
        )
        route = self._router.route(
            request.task_type,
            allow_cloud=allow_cloud,
            data_completeness_score=case_file.data_completeness_score if case_file else None,
            budget_cloud_allowed=budget.cloud_allowed,
            case_file=case_file,
        )
        if not budget.allowed or (case_file is not None and not case_file.allowed_for_ai and request.task_type != AITaskType.CASE_FILE_BUILD):
            blocked_reason = budget.blocked_reason or (case_file.blocked_reason if case_file else "ai_blocked")
            response = self._blocked_response(ai_request_id, request, blocked_reason)
            self._store_request_and_response(
                request=request,
                response=response,
                ai_request_id=ai_request_id,
                request_hash=request_hash,
                model_route=route.selected_tier.value,
                status="BUDGET_BLOCKED",
                cache_key=cache_key,
                budget_allowed=False,
                latency_ms=_elapsed_ms(started),
            )
            self._publish(EventType.AI_BUDGET_BLOCKED.value, {"ai_request_id": ai_request_id, "blocked_reason": blocked_reason}, request)
            return response

        self._insert_request(
            request=request,
            ai_request_id=ai_request_id,
            request_hash=request_hash,
            model_route=route.selected_tier.value,
            selected_model=route.selected_model,
            prompt_version_id=prompt.prompt_version_id,
            cache_key=cache_key,
            budget_allowed=True,
            escalation_requested=allow_cloud,
            escalation_allowed=budget.cloud_allowed,
            status="PENDING",
            metadata={"reason": reason, "case_file_blocked_reason": case_file.blocked_reason if case_file else None},
        )
        self._publish(EventType.AI_REQUEST_CREATED.value, {"ai_request_id": ai_request_id, "task_type": request.task_type.value}, request)

        if route.provider == "deterministic":
            worker_result = AIWorkerResult(status="COMPLETED", output={"summary": "case file built", "case_file": input_payload}, confidence=1.0)
            provider = "local"
        elif route.provider == "cloud":
            local_result = None
            worker_result = self._cloud_worker.escalate(
                request=request,
                ai_request_id=ai_request_id,
                case_file=case_file or _input_only_case_file(request),
                budget_decision=budget,
                local_result=local_result,
            )
            provider = "cloud"
        else:
            worker_result = self._local_worker.generate_json(
                model_name=route.selected_model,
                prompt=prompt.template_text,
                input_payload=input_payload,
                timeout_seconds=30,
            )
            provider = "local"

        response = self._response_from_worker(ai_request_id, request, route.selected_model, worker_result)
        status = "LOCAL_COMPLETED" if provider == "local" and worker_result.status == "COMPLETED" else "CLOUD_COMPLETED" if provider == "cloud" and worker_result.status == "COMPLETED" else "FAILED"
        latency_ms = _elapsed_ms(started)
        self._finish_request_and_response(
            request=request,
            response=response,
            ai_request_id=ai_request_id,
            status=status,
            latency_ms=latency_ms,
            input_tokens=worker_result.input_tokens,
            output_tokens=worker_result.output_tokens,
            estimated_cost=0.0 if provider == "local" else 0.01,
            error_message=worker_result.error_message,
        )
        self._costs.record_cost(
            ai_request_id=ai_request_id,
            model_name=route.selected_model,
            provider=provider,
            task_type=request.task_type.value,
            input_tokens=worker_result.input_tokens,
            output_tokens=worker_result.output_tokens,
            estimated_cost=0.0 if provider == "local" else 0.01,
        )
        self._publish(EventType.AI_COST_RECORDED.value, {"ai_request_id": ai_request_id, "provider": provider}, request)
        if worker_result.status == "COMPLETED":
            self._cache.store_cached_response(
                cache_key=cache_key,
                request_hash=request_hash,
                task_type=request.task_type,
                response=response,
                market_id=request.market_id,
                prompt_version_id=prompt.prompt_version_id,
                model_name=route.selected_model,
                expires_at=datetime.now(UTC) + timedelta(hours=6),
            )
        self._decisions.log_decision(request=request, response=response, ai_request_id=ai_request_id)
        self._publish(EventType.AI_DECISION_LOGGED.value, {"ai_request_id": ai_request_id, "task_type": request.task_type.value}, request)
        self._performance.record_result(
            model_name=route.selected_model,
            provider=provider,
            task_type=request.task_type.value,
            latency_ms=latency_ms,
            confidence=response.confidence,
            estimated_cost=0.0 if provider == "local" else 0.01,
            failure=status == "FAILED",
            escalation=provider == "cloud",
        )
        self._publish(EventType.AI_MODEL_PERFORMANCE_UPDATED.value, {"model_name": route.selected_model, "task_type": request.task_type.value}, request)
        self._publish(
            EventType.AI_CLOUD_COMPLETED.value if provider == "cloud" else EventType.AI_LOCAL_COMPLETED.value,
            {"ai_request_id": ai_request_id, "status": worker_result.status},
            request,
        )
        return response

    def health(self) -> dict[str, Any]:
        cost_summary = self._costs.summarize_costs()
        return {
            "local_ai_available": self._local_worker.health()["status"] == "AVAILABLE",
            "local_models": self._local_worker.health().get("available_models", []),
            "cloud_enabled": self._cloud_worker.health()["cloud_enabled"],
            "daily_cost": cost_summary["total_estimated_cost"],
            "cloud_cost": cost_summary["cloud_cost_today"],
            "cache_hit_rate": self._cache.hit_rate(),
            "last_error": self._local_worker.health().get("last_error") or self._cloud_worker.health().get("last_error"),
            "status": "HEALTHY",
        }

    def _runtime_allows_analysis(self, *, allow_cloud: bool) -> bool:
        if not self._factory.enabled:
            return True
        try:
            if allow_cloud and not self._state_governor.can_execute(RuntimeAction.CALL_CLOUD_AI):
                return False
            return self._state_governor.can_execute(RuntimeAction.RUN_INTELLIGENCE)
        except Exception:
            return False

    def _build_case_file_if_possible(self, request: AIRequest) -> AICaseFile | None:
        if not request.market_id:
            return None
        try:
            return self._case_files.build_case_file(request.market_id, task_type=request.task_type, event_id=request.event_id, correlation_id=request.correlation_id)
        except Exception:
            return AICaseFile(
                market_id=request.market_id,
                data_completeness_score=0.0,
                missing_fields=["market_record"],
                allowed_for_ai=False,
                blocked_reason="case_file_unavailable",
            )

    def _build_model_input(self, request: AIRequest, case_file: AICaseFile | None) -> dict[str, Any]:
        return redact_dict({"request_payload": request.input_payload, "case_file": case_file.compact_dict() if case_file else None})

    def _blocked_response(self, ai_request_id: str, request: AIRequest, reason: str | None) -> AIResponse:
        return AIResponse(
            ai_request_id=ai_request_id,
            task_type=request.task_type,
            model_name="none",
            structured_output={"status": "BLOCKED", "summary": "AI analysis blocked by safety policy", "blocked_reason": reason},
            confidence=0.0,
            risk_flags=[str(reason or "blocked")],
            recommended_action="NO_TRADE",
            raw_output_redacted=None,
            metadata={"cannot_trade_reason": "AI is interpretation only and cannot create orders"},
        )

    def _response_from_worker(self, ai_request_id: str, request: AIRequest, model_name: str, result: AIWorkerResult) -> AIResponse:
        if result.status != "COMPLETED":
            return AIResponse(
                ai_request_id=ai_request_id,
                task_type=request.task_type,
                model_name=model_name,
                structured_output={"status": result.status, "summary": "AI model unavailable or failed", "error": result.error_message},
                confidence=0.0,
                risk_flags=[result.status.lower()],
                recommended_action="NO_TRADE",
                raw_output_redacted=result.raw_output_redacted,
                metadata={"cannot_trade_reason": "AI unavailable; no trading action allowed"},
            )
        return AIResponse(
            ai_request_id=ai_request_id,
            task_type=request.task_type,
            model_name=model_name,
            structured_output=redact_dict(result.output),
            confidence=result.confidence,
            risk_flags=result.risk_flags,
            recommended_action=result.output.get("recommended_action"),
            raw_output_redacted=result.raw_output_redacted,
            metadata={"status": "COMPLETED"},
        )

    def _insert_request(self, **kwargs: Any) -> None:
        if not self._factory.enabled:
            return
        request = kwargs.pop("request")
        try:
            with self._factory.connect() as conn:
                self._requests.insert_request(
                    conn,
                    ai_request_id=kwargs["ai_request_id"],
                    request_hash=kwargs["request_hash"],
                    market_id=request.market_id,
                    event_id=request.event_id,
                    correlation_id=request.correlation_id,
                    source_service="ai_brain",
                    task_type=request.task_type.value,
                    model_route=kwargs["model_route"],
                    selected_model=kwargs.get("selected_model"),
                    prompt_version_id=kwargs.get("prompt_version_id"),
                    cache_key=kwargs.get("cache_key"),
                    cache_hit=kwargs.get("cache_hit", False),
                    budget_allowed=kwargs.get("budget_allowed", False),
                    escalation_requested=kwargs.get("escalation_requested", False),
                    escalation_allowed=kwargs.get("escalation_allowed", False),
                    status=kwargs.get("status", "PENDING"),
                    estimated_cost=kwargs.get("estimated_cost", 0.0),
                    metadata=kwargs.get("metadata"),
                )
                conn.commit()
        except Exception:
            return

    def _store_request_and_response(self, **kwargs: Any) -> None:
        self._insert_request(**{k: v for k, v in kwargs.items() if k not in {"response", "latency_ms"}})
        self._finish_request_and_response(**kwargs, input_tokens=None, output_tokens=None, estimated_cost=0.0, error_message=None)

    def _finish_request_and_response(
        self,
        *,
        request: AIRequest,
        response: AIResponse,
        ai_request_id: str,
        status: str,
        latency_ms: int | None,
        input_tokens: int | None,
        output_tokens: int | None,
        estimated_cost: float,
        error_message: str | None,
        **_extra: Any,
    ) -> None:
        if not self._factory.enabled:
            return
        try:
            with self._factory.connect() as conn:
                self._requests.finish_request(
                    conn,
                    ai_request_id=ai_request_id,
                    status=status,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost=estimated_cost,
                    error_message=error_message,
                )
                self._requests.insert_response(
                    conn,
                    ai_response_id=f"ai_resp_{uuid4().hex}",
                    ai_request_id=ai_request_id,
                    response_hash=stable_hash(response.structured_output),
                    model_name=response.model_name,
                    task_type=request.task_type.value,
                    structured_output=response.structured_output,
                    raw_output_redacted=response.raw_output_redacted,
                    confidence=response.confidence,
                    recommended_action=response.recommended_action,
                    risk_flags=response.risk_flags,
                    metadata=response.metadata,
                )
                conn.commit()
        except Exception:
            return

    def _publish(self, event_type: str, payload: dict[str, Any], request: AIRequest) -> None:
        try:
            self._event_bus.publish(
                event_type,
                redact_dict(payload),
                source_service="ai_brain",
                aggregate_type="market" if request.market_id else "ai_request",
                aggregate_id=request.market_id,
                correlation_id=request.correlation_id,
                metadata={"task_type": request.task_type.value},
            )
        except Exception:
            return


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _input_only_case_file(request: AIRequest) -> AICaseFile:
    return AICaseFile(
        market_id=request.market_id,
        data_completeness_score=100.0,
        orderbook_missing=True,
        rules_missing=True,
        allowed_for_ai=True,
        metadata={"input_only": True},
    )
