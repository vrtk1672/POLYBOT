from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.neural_bus.repository import table_exists


PROMPT_VERSION = "ai_full_mesh_intelligence_v1"
DEFAULT_MODEL = "qwen3:4b"
DEFAULT_LIMIT = 12
RECOMMENDED_FAST_JSON_MODEL = "llama3.2:1b"
RECOMMENDED_FAST_JSON_PULL = "ollama pull llama3.2:1b"

INSIGHT_TYPES = {
    "EVENT_INTELLIGENCE",
    "MARKET_RECALL",
    "TRIGGER_INTERPRETATION",
    "TRADE_THESIS",
    "HOLD_TIME",
    "EXIT_PLAN",
    "INVALIDATION",
    "ALREADY_PRICED_IN",
    "WHY_NOT",
    "DECISION_CRITIQUE",
    "ALERT",
}


class LocalAIClient(Protocol):
    def status(self) -> dict[str, Any]:
        ...

    def complete_json(
        self,
        *,
        prompt: str,
        timeout_seconds: float,
        model: str | None = None,
        num_predict: int | None = None,
        task: str | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class AIMeshConfig:
    enabled: bool = True
    max_ai_calls: int = 1
    max_reasoning_calls: int = 0
    fast_timeout_seconds: float = 18.0
    reasoning_timeout_seconds: float = 18.0
    max_prompt_chars: int = 700
    fast_num_predict: int = 220
    reasoning_num_predict: int = 140
    model_name: str = DEFAULT_MODEL
    fast_json_model_name: str | None = None
    fast_model_name: str | None = None
    reasoning_model_name: str | None = None
    cache_ttl_hours: int = 6


class OllamaMeshClient:
    def __init__(self, *, base_urls: list[str] | None = None, model_name: str | None = None) -> None:
        self._base_urls = base_urls or _ollama_base_urls()
        self._model_name = model_name or os.getenv("AI_MESH_OLLAMA_MODEL") or os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL
        self._last_good_base_url: str | None = None

    def status(self) -> dict[str, Any]:
        latest_error = None
        for base_url in self._base_urls:
            try:
                with httpx.Client(timeout=3.0, follow_redirects=True) as client:
                    response = client.get(f"{base_url}/api/tags")
                    response.raise_for_status()
                    payload = response.json()
                models = [str(item.get("model") or item.get("name")) for item in payload.get("models") or [] if item.get("model") or item.get("name")]
                if models:
                    self._last_good_base_url = base_url
                return {
                    "available": bool(models),
                    "provider": "OLLAMA" if models else "NONE",
                    "base_url_label": _safe_url_label(base_url),
                    "models": models,
                    "fast_json_model": _select_model(os.getenv("AI_FAST_JSON_MODEL") or os.getenv("AI_FAST_MODEL") or os.getenv("OLLAMA_MODEL_FAST") or self._model_name, models),
                    "fast_model": _select_model(os.getenv("AI_FAST_JSON_MODEL") or os.getenv("AI_FAST_MODEL") or os.getenv("OLLAMA_MODEL_FAST") or self._model_name, models),
                    "reasoning_model": _select_model(os.getenv("AI_REASONING_MODEL") or os.getenv("OLLAMA_MODEL_REASONING") or self._model_name, models),
                    "latest_error": None,
                }
            except Exception as exc:
                latest_error = f"{type(exc).__name__}: {exc}"
                continue
        return {
            "available": False,
            "provider": "NONE",
            "base_url_label": None,
            "models": [],
            "fast_model": None,
            "reasoning_model": None,
            "latest_error": latest_error or "OLLAMA_UNAVAILABLE",
        }

    def complete_json(
        self,
        *,
        prompt: str,
        timeout_seconds: float,
        model: str | None = None,
        num_predict: int | None = None,
        task: str | None = None,
    ) -> dict[str, Any]:
        last_error = "OLLAMA_UNAVAILABLE"
        model_name = model or self._model_name
        ordered_bases = [self._last_good_base_url] if self._last_good_base_url else list(self._base_urls)
        for base_url in ordered_bases:
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "think": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0,
                    "top_p": 0.2,
                    "num_predict": int(num_predict or 80),
                    "num_ctx": 1024,
                },
            }
            try:
                with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                    response = client.post(f"{base_url}/api/generate", json=payload)
                    response.raise_for_status()
                    raw = response.json()
                text = str(raw.get("response") or raw.get("thinking") or "")
                parsed = _parse_json_object(text)
                parsed["_model_provider"] = "OLLAMA"
                parsed["_model_name"] = model_name
                parsed["_task"] = task
                return parsed
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        raise RuntimeError(last_error)


class AIMarketIntelligenceMeshOrgan:
    """Persisted DATA_ONLY AI Mesh organ.

    AI insights are advisory Mesh evidence only. They never create paper intents,
    orders, fills, positions, live orders, execution candidates, or permission
    flags. Hard safety domains remain owned by Risk/Capital/Exit/Lifecycle.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        local_ai: LocalAIClient | None = None,
        config: AIMeshConfig | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._config = config or _config_from_env()
        self._local_ai = local_ai or OllamaMeshClient(model_name=self._config.model_name)

    def refresh(self, *, limit: int = DEFAULT_LIMIT, force: bool = False) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"ai_mesh_intelligence_{uuid4().hex}"
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "run_id": run_id, "insights_created": 0}
        limit = max(1, min(int(limit or DEFAULT_LIMIT), 100))
        model_status = self._safe_model_status()
        calls_attempted = 0
        calls_succeeded = 0
        calls_failed = 0
        calls_timed_out = 0
        invalid_json_count = 0
        schema_invalid_count = 0
        repaired_json_count = 0
        fallback_count = 0
        valid_json_count = 0
        latest_invalid_json_task = None
        latest_invalid_json_model = None
        skipped_budget = 0
        skipped_cached = 0
        skipped_low_priority = 0
        reasoning_calls_attempted = 0
        latencies: list[int] = []
        prompt_sizes: list[int] = []
        latest_error = None
        insight_rows: list[dict[str, Any]] = []
        with self._factory.connect() as conn, conn.transaction():
            ensure_tables(conn)
            candidate_selection = _candidate_context_selection(conn, limit=limit, force=force, cache_ttl_hours=self._config.cache_ttl_hours)
            event_selection = _recent_event_selection(conn, limit=min(3, limit), force=force, cache_ttl_hours=max(1, self._config.cache_ttl_hours * 2))
            candidates = candidate_selection["rows"]
            event_rows = event_selection["rows"]
            skipped_cached += int(candidate_selection.get("cache_hits") or 0) + int(event_selection.get("cache_hits") or 0)
            skipped_budget += int(candidate_selection.get("budget_skipped") or 0) + int(event_selection.get("budget_skipped") or 0)
            for row in candidates:
                context = build_candidate_context(row)
                task_kind = _candidate_task_kind(context)
                use_reasoning = task_kind in {"THESIS", "EXIT"} and reasoning_calls_attempted < self._config.max_reasoning_calls
                should_call = self._config.enabled and model_status.get("available") and calls_attempted < self._config.max_ai_calls
                if _skip_for_ai_hard_identity(context):
                    skipped_low_priority += 1
                    should_call = False
                if should_call:
                    calls_attempted += 1
                    if use_reasoning:
                        reasoning_calls_attempted += 1
                    started = time.perf_counter()
                    prompt = _candidate_prompt(context, reasoning=use_reasoning, max_chars=self._config.max_prompt_chars)
                    prompt_sizes.append(len(prompt))
                    try:
                        ai = self._local_ai.complete_json(
                            prompt=prompt,
                            timeout_seconds=self._config.reasoning_timeout_seconds if use_reasoning else self._config.fast_timeout_seconds,
                            model=str((model_status.get("reasoning_model") if use_reasoning else model_status.get("fast_model")) or self._config.model_name),
                            num_predict=self._config.reasoning_num_predict if use_reasoning else self._config.fast_num_predict,
                            task=task_kind,
                        )
                        ai, schema_repaired = _validate_ai_contract(ai, task=task_kind)
                        valid_json_count += 1
                        if schema_repaired:
                            repaired_json_count += 1
                        calls_succeeded += 1
                        latencies.append(int((time.perf_counter() - started) * 1000))
                    except Exception as exc:
                        calls_failed += 1
                        latest_error = f"{type(exc).__name__}: {exc}"
                        if _is_timeout_error(latest_error):
                            calls_timed_out += 1
                        if "AI_INVALID_JSON" in latest_error:
                            invalid_json_count += 1
                            latest_invalid_json_task = task_kind
                            latest_invalid_json_model = str(model_status.get("fast_model") or self._config.model_name)
                        if "AI_SCHEMA_INVALID" in latest_error:
                            schema_invalid_count += 1
                        fallback_count += 1
                        ai = deterministic_candidate_insight(context, ai_unavailable=False, error=latest_error, fallback_reason="model_output_invalid")
                else:
                    ai = deterministic_candidate_insight(context, ai_unavailable=not bool(model_status.get("available")))
                    fallback_count += 1
                for insight in build_candidate_insights(context, ai, run_id=run_id):
                    self._upsert_insight(conn, insight)
                    insight_rows.append(insight)
            for row in event_rows:
                context = build_event_context(row)
                if self._config.enabled and model_status.get("available") and calls_attempted < self._config.max_ai_calls:
                    calls_attempted += 1
                    started = time.perf_counter()
                    prompt = _event_prompt(context, max_chars=min(self._config.max_prompt_chars, 700))
                    prompt_sizes.append(len(prompt))
                    try:
                        ai = self._local_ai.complete_json(
                            prompt=prompt,
                            timeout_seconds=self._config.fast_timeout_seconds,
                            model=str(model_status.get("fast_model") or self._config.model_name),
                            num_predict=self._config.fast_num_predict,
                            task="EVENT",
                        )
                        ai, schema_repaired = _validate_ai_contract(ai, task="EVENT")
                        valid_json_count += 1
                        if schema_repaired:
                            repaired_json_count += 1
                        calls_succeeded += 1
                        latencies.append(int((time.perf_counter() - started) * 1000))
                    except Exception as exc:
                        calls_failed += 1
                        latest_error = f"{type(exc).__name__}: {exc}"
                        if _is_timeout_error(latest_error):
                            calls_timed_out += 1
                        if "AI_INVALID_JSON" in latest_error:
                            invalid_json_count += 1
                            latest_invalid_json_task = "EVENT"
                            latest_invalid_json_model = str(model_status.get("fast_model") or self._config.model_name)
                        if "AI_SCHEMA_INVALID" in latest_error:
                            schema_invalid_count += 1
                        fallback_count += 1
                        ai = deterministic_event_insight(context, ai_unavailable=False, error=latest_error, fallback_reason="model_output_invalid")
                else:
                    if self._config.enabled and model_status.get("available"):
                        skipped_budget += 1
                    ai = deterministic_event_insight(context, ai_unavailable=not bool(model_status.get("available")))
                    fallback_count += 1
                for insight in build_event_insights(context, ai, run_id=run_id):
                    self._upsert_insight(conn, insight)
                    insight_rows.append(insight)
            latest_error = latest_error if calls_succeeded == 0 and calls_failed else None
            self._insert_run(
                conn,
                run_id=run_id,
                status=_run_status(
                    model_available=bool(model_status.get("available")),
                    calls_attempted=calls_attempted,
                    calls_succeeded=calls_succeeded,
                    insights_created=len(insight_rows),
                    latest_error=latest_error,
                ),
                started_at=started_at,
                completed_at=datetime.now(UTC),
                model_status=model_status,
                insights_created=len(insight_rows),
                calls_attempted=calls_attempted,
                calls_succeeded=calls_succeeded,
                calls_failed=calls_failed,
                avg_latency_ms=int(sum(latencies) / len(latencies)) if latencies else 0,
                latest_error=latest_error,
                metadata={
                    "data_only": True,
                    "is_execution_authority": False,
                    "force": force,
                    "limit": limit,
                    "local_ai_available": bool(model_status.get("available")),
                    "ai_mode": _ai_mode(model_status, self._config, calls_succeeded, calls_timed_out),
                    "call_budget": _call_budget(self._config),
                    "calls_timed_out": calls_timed_out,
                    "invalid_json_count": invalid_json_count,
                    "schema_invalid_count": schema_invalid_count,
                    "repaired_json_count": repaired_json_count,
                    "fallback_count": fallback_count,
                    "valid_json_count": valid_json_count,
                    "valid_json_rate": _rate(valid_json_count, calls_attempted),
                    "latest_invalid_json_task": latest_invalid_json_task,
                    "latest_invalid_json_model": latest_invalid_json_model,
                    "skipped_budget": skipped_budget,
                    "skipped_cached": skipped_cached,
                    "skipped_low_priority": skipped_low_priority,
                    "reasoning_calls_attempted": reasoning_calls_attempted,
                    "prompt_chars_avg": int(sum(prompt_sizes) / len(prompt_sizes)) if prompt_sizes else 0,
                    "prompt_chars_max": max(prompt_sizes) if prompt_sizes else 0,
                    "p95_latency_ms": _p95(latencies),
                    "safety": {
                        "paper_intents_created": False,
                        "orders_created": False,
                        "live_orders_created": False,
                        "hard_blockers_overridden": False,
                    },
                },
            )
        return {
            "status": _run_status(
                model_available=bool(model_status.get("available")),
                calls_attempted=calls_attempted,
                calls_succeeded=calls_succeeded,
                insights_created=len(insight_rows),
                latest_error=latest_error,
            ),
            "run_id": run_id,
            "local_model_status": model_status,
            "insights_created": len(insight_rows),
            "calls_attempted": calls_attempted,
            "calls_succeeded": calls_succeeded,
            "calls_failed": calls_failed,
            "calls_timed_out": calls_timed_out,
            "invalid_json_count": invalid_json_count,
            "schema_invalid_count": schema_invalid_count,
            "repaired_json_count": repaired_json_count,
            "fallback_count": fallback_count,
            "valid_json_count": valid_json_count,
            "valid_json_rate": _rate(valid_json_count, calls_attempted),
            "skipped_budget": skipped_budget,
            "skipped_cached": skipped_cached,
            "skipped_low_priority": skipped_low_priority,
            "latest_error": latest_error,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def summary(self, *, limit: int = 20) -> dict[str, Any]:
        now = datetime.now(UTC)
        model_status = self._safe_model_status()
        if not self._factory.enabled:
            return _empty_summary("DATABASE_UNAVAILABLE", now, model_status)
        with self._factory.connect() as conn:
            ensure_tables(conn)
            counts = _summary_counts(conn)
            latest_run = _latest_run(conn)
            recent = _latest_insights(conn, limit=limit)
            alerts = _latest_insights(conn, limit=limit, where="insight_type='ALERT'")
            why_not = _top_json_values(conn, "why_not_json", limit=10)
            latest_successful_insight = _latest_successful_insight(conn)
        return {
            "status": "REAL" if counts["total_insights"] else "MISSING",
            "ai_enabled": self._config.enabled,
            "ai_mode": _ai_mode(
                model_status,
                self._config,
                int((latest_run or {}).get("calls_succeeded") or 0),
                int(((latest_run or {}).get("metadata_json") or {}).get("calls_timed_out") or 0),
            ),
            "local_model_status": model_status,
            "model_names": {
                "fast_json_model": model_status.get("fast_json_model") or self._config.fast_json_model_name or self._config.fast_model_name or self._config.model_name,
                "fast_model": model_status.get("fast_model") or self._config.fast_model_name or self._config.model_name,
                "reasoning_model": model_status.get("reasoning_model") or self._config.reasoning_model_name or self._config.model_name,
                "fallback_model": None,
            },
            "provider_reachable": bool(model_status.get("available")),
            "local_model_list": model_status.get("models") or [],
            "call_budget": _call_budget(self._config),
            **counts,
            "recent_event_insights": [item for item in recent if item.get("insight_type") == "EVENT_INTELLIGENCE"][:limit],
            "recent_thesis_insights": [item for item in recent if item.get("insight_type") == "TRADE_THESIS"][:limit],
            "recent_hold_time_insights": [item for item in recent if item.get("insight_type") == "HOLD_TIME"][:limit],
            "recent_exit_insights": [item for item in recent if item.get("insight_type") in {"EXIT_PLAN", "INVALIDATION"}][:limit],
            "recent_insights": recent,
            "ai_alerts": alerts,
            "ai_errors": [latest_run.get("latest_error")] if latest_run and latest_run.get("latest_error") else [],
            "average_latency_ms": int((latest_run or {}).get("avg_latency_ms") or 0),
            "p95_latency_ms": int(((latest_run or {}).get("metadata_json") or {}).get("p95_latency_ms") or 0),
            "success_count": int((latest_run or {}).get("calls_succeeded") or 0),
            "failure_count": int((latest_run or {}).get("calls_failed") or 0),
            "timeout_count": int(((latest_run or {}).get("metadata_json") or {}).get("calls_timed_out") or 0),
            "invalid_json_count": int(((latest_run or {}).get("metadata_json") or {}).get("invalid_json_count") or 0),
            "schema_invalid_count": int(((latest_run or {}).get("metadata_json") or {}).get("schema_invalid_count") or 0),
            "repaired_json_count": int(((latest_run or {}).get("metadata_json") or {}).get("repaired_json_count") or 0),
            "fallback_count": int(((latest_run or {}).get("metadata_json") or {}).get("fallback_count") or 0),
            "valid_json_count": int(((latest_run or {}).get("metadata_json") or {}).get("valid_json_count") or 0),
            "valid_json_rate": float(((latest_run or {}).get("metadata_json") or {}).get("valid_json_rate") or 0),
            "json_reliability_status": _json_reliability_status(latest_run),
            "fast_json_model": model_status.get("fast_json_model") or self._config.fast_json_model_name or self._config.fast_model_name or self._config.model_name,
            "reasoning_model": model_status.get("reasoning_model") or self._config.reasoning_model_name or self._config.model_name,
            "latest_invalid_json_task": ((latest_run or {}).get("metadata_json") or {}).get("latest_invalid_json_task"),
            "latest_invalid_json_model": ((latest_run or {}).get("metadata_json") or {}).get("latest_invalid_json_model"),
            "latest_timeout": latest_run.get("latest_error") if latest_run and int(((latest_run or {}).get("metadata_json") or {}).get("calls_timed_out") or 0) > 0 and _is_timeout_error(str(latest_run.get("latest_error") or "")) else None,
            "latest_invalid_json": latest_run.get("latest_error") if latest_run and "AI_INVALID_JSON" in str(latest_run.get("latest_error") or "") else None,
            "skipped_budget": int(((latest_run or {}).get("metadata_json") or {}).get("skipped_budget") or 0),
            "skipped_cached": int(((latest_run or {}).get("metadata_json") or {}).get("skipped_cached") or 0),
            "skipped_low_priority": int(((latest_run or {}).get("metadata_json") or {}).get("skipped_low_priority") or 0),
            "latest_successful_insight": latest_successful_insight,
            "candidates_upgraded_by_ai": counts["candidates_with_thesis_or_exit_suggestions"],
            "candidates_kept_blocked_by_ai": counts["candidates_kept_blocked_count"],
            "top_why_not_reasons": why_not,
            "latest_run": latest_run,
            "generated_at": now.isoformat(),
        }

    def diagnostics(self) -> dict[str, Any]:
        summary = self.summary(limit=5)
        benchmark = self.benchmark(run_model_tests=False)
        return {
            "status": summary.get("status"),
            "ai_mode": summary.get("ai_mode"),
            "provider_reachable": summary.get("provider_reachable"),
            "local_model_status": summary.get("local_model_status"),
            "call_budget": summary.get("call_budget"),
            "average_latency_ms": summary.get("average_latency_ms"),
            "p95_latency_ms": summary.get("p95_latency_ms"),
            "timeout_count": summary.get("timeout_count"),
            "latest_timeout": summary.get("latest_timeout"),
            "latest_invalid_json": summary.get("latest_invalid_json"),
            "json_reliability_status": summary.get("json_reliability_status"),
            "valid_json_rate": summary.get("valid_json_rate"),
            "invalid_json_count": summary.get("invalid_json_count"),
            "schema_invalid_count": summary.get("schema_invalid_count"),
            "repaired_json_count": summary.get("repaired_json_count"),
            "fallback_count": summary.get("fallback_count"),
            "skipped_budget": summary.get("skipped_budget"),
            "skipped_cached": summary.get("skipped_cached"),
            "benchmark": benchmark,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def benchmark(self, *, run_model_tests: bool = True) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        model_status = self._safe_model_status()
        tests: list[dict[str, Any]] = []
        if not model_status.get("available") or not run_model_tests:
            return {
                "status": "SKIPPED" if not run_model_tests else "AI_UNAVAILABLE",
                "provider_reachable": bool(model_status.get("available")),
                "model_status": model_status,
                "timeout_threshold_seconds": self._config.fast_timeout_seconds,
                "tests": tests,
                "recommended_mode": _ai_mode(model_status, self._config, 0, 0),
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
            }
        fast_model = str(model_status.get("fast_model") or self._config.fast_model_name or self._config.model_name)
        reasoning_model = str(model_status.get("reasoning_model") or self._config.reasoning_model_name or fast_model)
        tests.append(self._benchmark_prompt("tiny_json", '{"task":"ping"} Return {"status":"OK"}.', fast_model, self._config.fast_timeout_seconds, 24))
        tests.append(self._benchmark_prompt("event_classification", _compact_event_prompt({"summary": "Market-relevant news happened.", "source_type": "NEWS"}), fast_model, self._config.fast_timeout_seconds, self._config.fast_num_predict))
        tests.append(self._benchmark_prompt("thesis", _compact_candidate_prompt({"trigger_type": "PAYOUT_DISCREPANCY", "thesis_state": "THESIS_MISSING", "exit_state": "EXIT_NOT_READY", "side": "YES"}, reasoning=True), reasoning_model, self._config.reasoning_timeout_seconds, self._config.reasoning_num_predict))
        failures = [item for item in tests if not item.get("success")]
        return {
            "status": "OK" if not failures else "PARTIAL",
            "provider_reachable": True,
            "model_status": model_status,
            "timeout_threshold_seconds": self._config.fast_timeout_seconds,
            "tests": tests,
            "recommended_mode": "ENABLED" if not failures else "FAST_ONLY" if any(item.get("success") for item in tests) else "DEGRADED",
            "latest_error": failures[-1].get("error") if failures else None,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
        }

    def benchmark_json(self, *, run_model_tests: bool = True) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        model_status = self._safe_model_status()
        models = list(model_status.get("models") or [])
        tests: list[dict[str, Any]] = []
        if not model_status.get("available") or not run_model_tests:
            return {
                "status": "SKIPPED" if not run_model_tests else "AI_UNAVAILABLE",
                "provider_reachable": bool(model_status.get("available")),
                "models": models,
                "tests": tests,
                "recommended_fast_json_model": None,
                "recommended_reasoning_model": None,
                "recommended_ai_mode": "DISABLED" if not model_status.get("available") else "FAST_ONLY_DEGRADED",
                "recommended_pull_command": RECOMMENDED_FAST_JSON_PULL,
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
            }
        for model in models:
            for task_name, task_kind, prompt, num_predict in _json_benchmark_specs():
                tests.append(self._benchmark_json_prompt(model, task_name, task_kind, prompt, num_predict))
        by_model: dict[str, list[dict[str, Any]]] = {}
        for item in tests:
            by_model.setdefault(str(item["model"]), []).append(item)
        passing_models = [
            model
            for model, items in by_model.items()
            if items and all(item.get("valid_json") and item.get("schema_valid") for item in items)
        ]
        partial_models = [
            model
            for model, items in by_model.items()
            if items and any(item.get("valid_json") and item.get("schema_valid") for item in items)
        ]
        recommended_fast = passing_models[0] if passing_models else None
        recommended_reasoning = recommended_fast or (partial_models[0] if partial_models else None)
        if recommended_fast:
            mode = "FAST_JSON_ONLY" if recommended_fast == recommended_reasoning else "ENABLED"
        elif partial_models:
            mode = "FAST_ONLY_DEGRADED"
        else:
            mode = "DISABLED"
        failures = [item for item in tests if not (item.get("valid_json") and item.get("schema_valid"))]
        return {
            "status": "OK" if not failures else "PARTIAL" if partial_models else "FAILED",
            "provider_reachable": True,
            "models": models,
            "tests": tests,
            "recommended_fast_json_model": recommended_fast,
            "recommended_reasoning_model": recommended_reasoning,
            "recommended_ai_mode": mode,
            "recommended_pull_command": None if recommended_fast else RECOMMENDED_FAST_JSON_PULL,
            "latest_error": failures[-1].get("error") if failures else None,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
        }

    def _benchmark_json_prompt(self, model: str, task_name: str, task_kind: str, prompt: str, num_predict: int) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            payload = self._local_ai.complete_json(
                prompt=prompt,
                timeout_seconds=self._config.fast_timeout_seconds,
                model=model,
                num_predict=num_predict,
                task=f"JSON_BENCHMARK_{task_name}",
            )
            validated, repaired = _validate_ai_contract(payload, task=task_kind)
            return {
                "model": model,
                "task": task_name,
                "success": True,
                "valid_json": True,
                "schema_valid": True,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "output_length": len(json.dumps(_json_safe(validated), separators=(",", ":"))),
                "error_type": None,
                "extra_prose": bool(payload.get("_json_extracted")),
                "repair_succeeded": repaired,
                "fallback_used": False,
            }
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            fallback = _deterministic_schema_fallback(task_kind, error)
            return {
                "model": model,
                "task": task_name,
                "success": False,
                "valid_json": "AI_INVALID_JSON" not in error,
                "schema_valid": False,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "output_length": 0,
                "error_type": _ai_error_type(error),
                "error": error,
                "extra_prose": False,
                "repair_succeeded": False,
                "fallback_used": True,
                "fallback": fallback,
            }

    def _benchmark_prompt(self, name: str, prompt: str, model: str, timeout: float, num_predict: int) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            payload = self._local_ai.complete_json(
                prompt=prompt,
                timeout_seconds=timeout,
                model=model,
                num_predict=num_predict,
                task=f"BENCHMARK_{name}",
            )
            return {
                "name": name,
                "success": True,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": model,
                "prompt_chars": len(prompt),
                "response_keys": sorted([str(key) for key in payload.keys() if not str(key).startswith("_")])[:12],
            }
        except Exception as exc:
            return {
                "name": name,
                "success": False,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "model": model,
                "prompt_chars": len(prompt),
                "error": f"{type(exc).__name__}: {exc}",
            }

    def _safe_model_status(self) -> dict[str, Any]:
        try:
            status = self._local_ai.status()
            return status if isinstance(status, dict) else {"available": False, "provider": "NONE", "latest_error": "INVALID_STATUS"}
        except Exception as exc:
            return {"available": False, "provider": "NONE", "models": [], "latest_error": f"{type(exc).__name__}: {exc}"}

    def _upsert_insight(self, conn: Any, insight: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO ai_mesh_insights (
                ai_mesh_insight_id, run_id, insight_type, market_id, condition_id, side, token_id,
                source_event_id, multi_trigger_id, proactive_candidate_seed_id, seed_mesh_inquiry_id,
                opportunity_score_id, model_provider, model_name, prompt_version, summary, reasoning_brief,
                entities_json, topics_json, related_markets_json, direction_hint, direction_confidence,
                thesis_type, thesis_confidence, expected_hold_time_seconds, exit_target, time_stop_seconds,
                invalidation_condition, already_priced_in_state, missing_evidence_json,
                supporting_evidence_ids_json, contradicting_evidence_ids_json, confidence, risk_notes_json,
                why_not_json, recommended_mesh_action, is_execution_authority, metadata_json
            ) VALUES (
                %(ai_mesh_insight_id)s, %(run_id)s, %(insight_type)s, %(market_id)s, %(condition_id)s, %(side)s, %(token_id)s,
                %(source_event_id)s, %(multi_trigger_id)s, %(proactive_candidate_seed_id)s, %(seed_mesh_inquiry_id)s,
                %(opportunity_score_id)s, %(model_provider)s, %(model_name)s, %(prompt_version)s, %(summary)s, %(reasoning_brief)s,
                %(entities_json)s, %(topics_json)s, %(related_markets_json)s, %(direction_hint)s, %(direction_confidence)s,
                %(thesis_type)s, %(thesis_confidence)s, %(expected_hold_time_seconds)s, %(exit_target)s, %(time_stop_seconds)s,
                %(invalidation_condition)s, %(already_priced_in_state)s, %(missing_evidence_json)s,
                %(supporting_evidence_ids_json)s, %(contradicting_evidence_ids_json)s, %(confidence)s, %(risk_notes_json)s,
                %(why_not_json)s, %(recommended_mesh_action)s, FALSE, %(metadata_json)s
            )
            ON CONFLICT (ai_mesh_insight_id) DO UPDATE SET
                summary=EXCLUDED.summary,
                reasoning_brief=EXCLUDED.reasoning_brief,
                missing_evidence_json=EXCLUDED.missing_evidence_json,
                risk_notes_json=EXCLUDED.risk_notes_json,
                why_not_json=EXCLUDED.why_not_json,
                recommended_mesh_action=EXCLUDED.recommended_mesh_action,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            _sql_params(insight),
        )

    def _insert_run(self, conn: Any, **kwargs: Any) -> None:
        conn.execute(
            """
            INSERT INTO ai_mesh_intelligence_runs (
                run_id, status, started_at, completed_at, insights_created,
                calls_attempted, calls_succeeded, calls_failed, avg_latency_ms,
                local_model_status_json, latest_error, metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (run_id) DO UPDATE SET
                status=EXCLUDED.status,
                completed_at=EXCLUDED.completed_at,
                insights_created=EXCLUDED.insights_created,
                calls_attempted=EXCLUDED.calls_attempted,
                calls_succeeded=EXCLUDED.calls_succeeded,
                calls_failed=EXCLUDED.calls_failed,
                avg_latency_ms=EXCLUDED.avg_latency_ms,
                local_model_status_json=EXCLUDED.local_model_status_json,
                latest_error=EXCLUDED.latest_error,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now()
            """,
            (
                kwargs["run_id"],
                kwargs["status"],
                kwargs["started_at"],
                kwargs["completed_at"],
                int(kwargs.get("insights_created") or 0),
                int(kwargs.get("calls_attempted") or 0),
                int(kwargs.get("calls_succeeded") or 0),
                int(kwargs.get("calls_failed") or 0),
                int(kwargs.get("avg_latency_ms") or 0),
                Jsonb(_json_safe(kwargs.get("model_status") or {})),
                kwargs.get("latest_error"),
                Jsonb(_json_safe(kwargs.get("metadata") or {})),
            ),
        )


def ensure_tables(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_mesh_insights (
            id BIGSERIAL PRIMARY KEY,
            ai_mesh_insight_id TEXT NOT NULL UNIQUE,
            run_id TEXT,
            insight_type TEXT NOT NULL,
            market_id TEXT,
            condition_id TEXT,
            side TEXT,
            token_id TEXT,
            source_event_id TEXT,
            multi_trigger_id TEXT,
            proactive_candidate_seed_id TEXT,
            seed_mesh_inquiry_id TEXT,
            opportunity_score_id TEXT,
            model_provider TEXT NOT NULL DEFAULT 'NONE',
            model_name TEXT,
            prompt_version TEXT NOT NULL,
            summary TEXT,
            reasoning_brief TEXT,
            entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            related_markets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            direction_hint TEXT NOT NULL DEFAULT 'UNKNOWN',
            direction_confidence NUMERIC NOT NULL DEFAULT 0,
            thesis_type TEXT NOT NULL DEFAULT 'UNKNOWN',
            thesis_confidence NUMERIC NOT NULL DEFAULT 0,
            expected_hold_time_seconds INTEGER,
            exit_target TEXT,
            time_stop_seconds INTEGER,
            invalidation_condition TEXT,
            already_priced_in_state TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
            missing_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            supporting_evidence_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            contradicting_evidence_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            confidence NUMERIC NOT NULL DEFAULT 0,
            risk_notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            why_not_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            recommended_mesh_action TEXT NOT NULL DEFAULT 'NO_ACTION',
            is_execution_authority BOOLEAN NOT NULL DEFAULT FALSE,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_mesh_insights_market_side ON ai_mesh_insights (market_id, side)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_mesh_insights_seed ON ai_mesh_insights (proactive_candidate_seed_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_mesh_insights_type ON ai_mesh_insights (insight_type, created_at DESC)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_mesh_intelligence_runs (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            insights_created INTEGER NOT NULL DEFAULT 0,
            calls_attempted INTEGER NOT NULL DEFAULT 0,
            calls_succeeded INTEGER NOT NULL DEFAULT 0,
            calls_failed INTEGER NOT NULL DEFAULT 0,
            avg_latency_ms INTEGER NOT NULL DEFAULT 0,
            local_model_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            latest_error TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def build_candidate_context(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "market_id": row.get("market_id"),
        "condition_id": row.get("condition_id"),
        "side": row.get("side") or "SIDE_UNKNOWN",
        "token_id": row.get("token_id"),
        "source_event_id": row.get("source_event_id"),
        "multi_trigger_id": row.get("multi_trigger_id"),
        "proactive_candidate_seed_id": row.get("proactive_candidate_seed_id"),
        "seed_mesh_inquiry_id": row.get("seed_mesh_inquiry_id"),
        "opportunity_score_id": row.get("opportunity_score_id"),
        "trigger_type": row.get("trigger_type") or row.get("seed_type") or "UNKNOWN",
        "seed_type": row.get("seed_type"),
        "edge_state": row.get("edge_state"),
        "thesis_state": row.get("thesis_state"),
        "opportunity_score": _float(row.get("opportunity_score")),
        "risk_state": row.get("risk_state"),
        "capital_state": row.get("capital_state"),
        "exit_state": row.get("exit_state"),
        "lifecycle_state": row.get("lifecycle_state"),
        "orderbook_state": row.get("orderbook_state"),
        "token_verification_state": row.get("token_verification_state"),
        "policy_state": row.get("observation_policy_state"),
        "policy_blockers": _list(row.get("policy_blockers_json")),
        "required_to_pass": _list(row.get("required_to_pass_json")),
        "soft_blockers": _list(row.get("soft_blockers_json")),
        "hard_blockers": _list(row.get("hard_blockers_json")),
        "lineage": _dict(row.get("lineage_json")),
    }


def build_event_context(row: dict[str, Any]) -> dict[str, Any]:
    title = str(row.get("title") or row.get("event_title") or "")
    body = str(row.get("summary") or row.get("content") or "")
    text = f"{title} {body}".strip()[:1200]
    return {
        "source_event_id": row.get("source_event_id"),
        "title": row.get("title") or row.get("event_title"),
        "summary": text,
        "source_type": row.get("source_type") or row.get("event_type"),
        "created_at": row.get("created_at"),
        "event_timestamp": row.get("event_timestamp"),
    }


def deterministic_candidate_insight(
    context: dict[str, Any],
    *,
    ai_unavailable: bool,
    error: str | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    blockers = [str(item) for item in context.get("policy_blockers") or []]
    missing = _missing_from_context(context)
    trigger_type = str(context.get("trigger_type") or "UNKNOWN").upper()
    thesis_type = _thesis_type_for_trigger(trigger_type)
    no_valid = bool(blockers) or "side_clarity" in missing or "token_id" in missing or thesis_type == "UNKNOWN"
    return {
        "status": "AI_UNAVAILABLE" if ai_unavailable else "DETERMINISTIC_FALLBACK" if error else "DETERMINISTIC_CONTEXT_ONLY",
        "summary": "Local AI unavailable; deterministic Mesh context preserved." if ai_unavailable else "Deterministic fallback used; model output was not trusted." if error else "Deterministic Mesh context captured without model call.",
        "reasoning_brief": "AI did not create execution authority. Existing blockers remain authoritative.",
        "direction_hint": context.get("side") if context.get("side") in {"YES", "NO"} else "UNKNOWN",
        "direction_confidence": 0.0,
        "thesis_type": "NO_VALID_THESIS" if no_valid else thesis_type,
        "thesis_confidence": 0.0 if ai_unavailable else 0.35,
        "expected_hold_time_seconds": _default_hold_seconds(trigger_type) if not ai_unavailable else None,
        "time_stop_seconds": _default_hold_seconds(trigger_type) if not ai_unavailable else None,
        "exit_target": None,
        "invalidation_condition": None if ai_unavailable else "Invalidate if source-backed edge, trigger evidence, or orderbook support deteriorates.",
        "already_priced_in_state": "UNKNOWN",
        "missing_evidence": missing,
        "risk_notes": [],
        "why_not": _dedupe([*(blockers or missing or []), *(["AI_UNAVAILABLE"] if ai_unavailable else []), *(["valid_ai_json_unavailable"] if error else [])]),
        "recommended_mesh_action": "BUILD_THESIS" if not ai_unavailable and missing else "WATCH_ONLY",
        "confidence": 0.0 if ai_unavailable or error else 0.35,
        "_generated_by": "DETERMINISTIC_FALLBACK" if error or ai_unavailable else "DETERMINISTIC_CONTEXT_ONLY",
        "_fallback_reason": fallback_reason or ("ai_unavailable" if ai_unavailable else None),
        "_fallback_error": error,
        "_model_provider": "NONE",
        "_model_name": None,
    }


def deterministic_event_insight(
    context: dict[str, Any],
    *,
    ai_unavailable: bool,
    error: str | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    text = str(context.get("summary") or context.get("title") or "")
    keywords = _keywords(text)
    return {
        "status": "AI_UNAVAILABLE" if ai_unavailable else "DETERMINISTIC_FALLBACK" if error else "DETERMINISTIC_CONTEXT_ONLY",
        "summary": "Local AI unavailable; event retained for deterministic recall." if ai_unavailable else "Deterministic event fallback used; model output was not trusted." if error else "Event context extracted for market recall assistance.",
        "reasoning_brief": text[:300],
        "entities": keywords[:8],
        "topics": keywords[:8],
        "related_markets": [],
        "direction_hint": "UNKNOWN",
        "direction_confidence": 0.0,
        "missing_evidence": ["local_ai_model_output"] if ai_unavailable or error else [],
        "why_not": _dedupe([*(["AI_UNAVAILABLE"] if ai_unavailable else []), *(["valid_ai_json_unavailable"] if error else [])]),
        "recommended_mesh_action": "WATCH_ONLY" if keywords else "NO_ACTION",
        "confidence": 0.0 if ai_unavailable or error else 0.25,
        "_generated_by": "DETERMINISTIC_FALLBACK" if error or ai_unavailable else "DETERMINISTIC_CONTEXT_ONLY",
        "_fallback_reason": fallback_reason or ("ai_unavailable" if ai_unavailable else None),
        "_fallback_error": error,
        "_model_provider": "NONE",
        "_model_name": None,
    }


def build_candidate_insights(context: dict[str, Any], ai: dict[str, Any], *, run_id: str) -> list[dict[str, Any]]:
    insight_types = ["DECISION_CRITIQUE", "WHY_NOT"]
    if _upper(context.get("thesis_state")) in {"THESIS_WATCH", "THESIS_MISSING", "UNKNOWN"}:
        insight_types.append("TRADE_THESIS")
    if ai.get("expected_hold_time_seconds") or "missing_dynamic_hold_time" in {str(item) for item in context.get("policy_blockers") or context.get("required_to_pass") or []}:
        insight_types.append("HOLD_TIME")
    if _upper(context.get("exit_state")) not in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}:
        insight_types.extend(["EXIT_PLAN", "INVALIDATION"])
    if _upper(context.get("orderbook_state")) == "FRESH":
        insight_types.append("ALREADY_PRICED_IN")
    return [_base_insight(context, ai, insight_type=item, run_id=run_id) for item in _dedupe(insight_types)]


def build_event_insights(context: dict[str, Any], ai: dict[str, Any], *, run_id: str) -> list[dict[str, Any]]:
    return [
        _base_insight(context, ai, insight_type="EVENT_INTELLIGENCE", run_id=run_id),
        _base_insight(context, ai, insight_type="MARKET_RECALL", run_id=run_id),
    ]


def _base_insight(context: dict[str, Any], ai: dict[str, Any], *, insight_type: str, run_id: str) -> dict[str, Any]:
    provider = str(ai.get("_model_provider") or ai.get("model_provider") or "NONE").upper()
    model_name = ai.get("_model_name") or ai.get("model_name")
    seed_id = context.get("proactive_candidate_seed_id")
    base = "|".join(str(context.get(key) or "") for key in ("source_event_id", "multi_trigger_id", "proactive_candidate_seed_id", "seed_mesh_inquiry_id", "market_id", "side"))
    insight_id = "ai_mesh_insight_" + hashlib.sha256(f"{insight_type}|{base}".encode("utf-8")).hexdigest()[:32]
    missing = _dedupe([*_list(ai.get("missing_evidence")), *_missing_from_context(context)])
    why_not = _dedupe([*_list(ai.get("why_not")), *_list(context.get("policy_blockers")), *_list(context.get("required_to_pass"))])
    return {
        "ai_mesh_insight_id": insight_id,
        "run_id": run_id,
        "insight_type": insight_type,
        "market_id": context.get("market_id"),
        "condition_id": context.get("condition_id"),
        "side": _side(ai.get("direction_hint") or context.get("side")),
        "token_id": context.get("token_id"),
        "source_event_id": context.get("source_event_id"),
        "multi_trigger_id": context.get("multi_trigger_id"),
        "proactive_candidate_seed_id": seed_id,
        "seed_mesh_inquiry_id": context.get("seed_mesh_inquiry_id"),
        "opportunity_score_id": context.get("opportunity_score_id"),
        "model_provider": provider,
        "model_name": model_name,
        "prompt_version": PROMPT_VERSION,
        "summary": str(ai.get("summary") or f"{insight_type} insight generated."),
        "reasoning_brief": str(ai.get("reasoning_brief") or ai.get("reason") or ""),
        "entities_json": _list(ai.get("entities")),
        "topics_json": _list(ai.get("topics")),
        "related_markets_json": _validated_related_markets(ai.get("related_markets")),
        "direction_hint": _direction(ai.get("direction_hint") or context.get("side")),
        "direction_confidence": _bounded(ai.get("direction_confidence")),
        "thesis_type": _thesis_type(ai.get("thesis_type")),
        "thesis_confidence": _bounded(ai.get("thesis_confidence")),
        "expected_hold_time_seconds": _int_or_none(ai.get("expected_hold_time_seconds")),
        "exit_target": _text(ai.get("exit_target")),
        "time_stop_seconds": _int_or_none(ai.get("time_stop_seconds")),
        "invalidation_condition": _text(ai.get("invalidation_condition")),
        "already_priced_in_state": _already_priced_in(ai.get("already_priced_in_state")),
        "missing_evidence_json": missing,
        "supporting_evidence_ids_json": _list(ai.get("supporting_evidence_ids")),
        "contradicting_evidence_ids_json": _list(ai.get("contradicting_evidence_ids")),
        "confidence": _bounded(ai.get("confidence")),
        "risk_notes_json": _list(ai.get("risk_notes")),
        "why_not_json": why_not,
        "recommended_mesh_action": _mesh_action(ai.get("recommended_mesh_action")),
        "is_execution_authority": False,
        "metadata_json": {
            "ai_is_full_mesh_organ": True,
            "generated_by": ai.get("_generated_by") or ("MODEL" if provider != "NONE" else "DETERMINISTIC_FALLBACK"),
            "fallback_reason": ai.get("_fallback_reason"),
            "fallback_error": ai.get("_fallback_error"),
            "schema_repaired": bool(ai.get("_schema_repaired")),
            "schema_valid": bool(ai.get("_schema_valid")) if "_schema_valid" in ai else provider != "NONE",
            "data_only": True,
            "is_execution_authority": False,
            "execution_allowed": False,
            "paper_allowed": False,
            "shadow_allowed": False,
            "live_allowed": False,
            "does_not_override_hard_blockers": True,
            "context": _json_safe(context),
        },
    }


def _candidate_context_selection(conn: Any, *, limit: int, force: bool, cache_ttl_hours: int) -> dict[str, Any]:
    if not table_exists(conn, "paper_observation_policy_reviews"):
        return {"rows": [], "cache_hits": 0, "budget_skipped": 0}
    total_eligible = int((conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM paper_observation_policy_reviews
        WHERE observation_policy_state IN ('OBSERVATION_POLICY_WATCH','OBSERVATION_POLICY_INCOMPLETE','OBSERVATION_POLICY_BLOCKED','OBSERVATION_POLICY_ELIGIBLE')
        """
    ).fetchone() or {}).get("count") or 0)
    recent_filter = "" if force or not table_exists(conn, "ai_mesh_insights") else """
        AND NOT EXISTS (
            SELECT 1 FROM ai_mesh_insights ami
            WHERE ami.proactive_candidate_seed_id=popr.proactive_candidate_seed_id
              AND ami.updated_at >= now() - (%s::int * interval '1 hour')
        )
    """
    params: list[Any] = []
    if recent_filter:
        params.append(cache_ttl_hours)
    params.append(limit)
    rows = conn.execute(
        f"""
        WITH market_side_counts AS (
            SELECT market_id, side, COUNT(*) AS market_side_count
            FROM paper_observation_policy_reviews
            GROUP BY market_id, side
        )
        SELECT
            popr.*,
            pcs.seed_type,
            pcs.trigger_type,
            pcs.source_event_id,
            pcs.multi_trigger_id,
            psr.metadata_json AS mesh_metadata_json,
            COALESCE(msc.market_side_count, 0) AS market_side_policy_count
        FROM paper_observation_policy_reviews popr
        LEFT JOIN market_side_counts msc ON msc.market_id=popr.market_id AND msc.side=popr.side
        LEFT JOIN proactive_candidate_seeds pcs ON pcs.proactive_candidate_seed_id=popr.proactive_candidate_seed_id
        LEFT JOIN proactive_seed_mesh_results psr ON psr.seed_mesh_inquiry_id=popr.seed_mesh_inquiry_id
        WHERE popr.observation_policy_state IN ('OBSERVATION_POLICY_WATCH','OBSERVATION_POLICY_INCOMPLETE','OBSERVATION_POLICY_BLOCKED','OBSERVATION_POLICY_ELIGIBLE')
          {recent_filter}
        ORDER BY
            CASE
                WHEN popr.edge_state='EDGE_SUPPORTED'
                 AND popr.market_id IS NOT NULL
                 AND popr.side IN ('YES','NO')
                 AND popr.token_id IS NOT NULL THEN 0
                ELSE 1
            END,
            CASE popr.observation_policy_state
                WHEN 'OBSERVATION_POLICY_INCOMPLETE' THEN 0
                WHEN 'OBSERVATION_POLICY_WATCH' THEN 1
                WHEN 'OBSERVATION_POLICY_BLOCKED' THEN 2
                ELSE 3
            END,
            COALESCE(msc.market_side_count, 0) ASC,
            popr.opportunity_score DESC,
            popr.updated_at DESC,
            popr.id DESC
        LIMIT %s
        """,
        tuple(params),
    ).fetchall()
    selected = [_json_safe(dict(row)) for row in rows]
    return {
        "rows": selected,
        "cache_hits": max(0, total_eligible - len(selected)) if not force else 0,
        "budget_skipped": max(0, len(selected) - limit),
    }


def _candidate_context_rows(conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
    return list(_candidate_context_selection(conn, limit=limit, force=force, cache_ttl_hours=6)["rows"])


def _recent_event_selection(conn: Any, *, limit: int, force: bool, cache_ttl_hours: int) -> dict[str, Any]:
    if not table_exists(conn, "source_event_memory"):
        return {"rows": [], "cache_hits": 0, "budget_skipped": 0}
    cols = _table_columns(conn, "source_event_memory")
    time_col = "event_timestamp" if "event_timestamp" in cols else "created_at" if "created_at" in cols else "updated_at" if "updated_at" in cols else None
    order_expr = f"{time_col} DESC NULLS LAST, id DESC" if time_col else "id DESC"
    total_eligible = int((conn.execute("SELECT COUNT(*) AS count FROM source_event_memory").fetchone() or {}).get("count") or 0)
    recent_filter = "" if force or not table_exists(conn, "ai_mesh_insights") else """
        AND NOT EXISTS (
            SELECT 1 FROM ai_mesh_insights ami
            WHERE ami.source_event_id=sem.source_event_id
              AND ami.insight_type='EVENT_INTELLIGENCE'
              AND ami.updated_at >= now() - (%s::int * interval '1 hour')
        )
    """
    params: list[Any] = []
    if recent_filter:
        params.append(cache_ttl_hours)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT *
        FROM source_event_memory sem
        WHERE true {recent_filter}
        ORDER BY {order_expr}
        LIMIT %s
        """,
        tuple(params),
    ).fetchall()
    selected = [_json_safe(dict(row)) for row in rows]
    return {"rows": selected, "cache_hits": max(0, total_eligible - len(selected)) if not force else 0, "budget_skipped": 0}


def _recent_event_rows(conn: Any, *, limit: int, force: bool) -> list[dict[str, Any]]:
    return list(_recent_event_selection(conn, limit=limit, force=force, cache_ttl_hours=12)["rows"])


def _table_columns(conn: Any, table: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema()
          AND table_name=%s
        """,
        (table,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


def _summary_counts(conn: Any) -> dict[str, Any]:
    if not table_exists(conn, "ai_mesh_insights"):
        return {
            "total_insights": 0,
            "insights_by_type": {},
            "candidates_upgraded_by_ai": 0,
            "candidates_with_thesis_or_exit_suggestions": 0,
            "candidates_kept_blocked_count": 0,
        }
    total = int((conn.execute("SELECT COUNT(*) AS count FROM ai_mesh_insights").fetchone() or {}).get("count") or 0)
    by_type = {
        str(row["insight_type"]): int(row["count"] or 0)
        for row in conn.execute("SELECT insight_type, COUNT(*) AS count FROM ai_mesh_insights GROUP BY insight_type ORDER BY count DESC").fetchall()
    }
    suggestions = int(
        (conn.execute(
            """
            SELECT COUNT(DISTINCT proactive_candidate_seed_id) AS count
            FROM ai_mesh_insights
            WHERE proactive_candidate_seed_id IS NOT NULL
              AND (
                insight_type IN ('TRADE_THESIS','HOLD_TIME','EXIT_PLAN','INVALIDATION')
                OR expected_hold_time_seconds IS NOT NULL
                OR COALESCE(invalidation_condition,'') <> ''
              )
            """
        ).fetchone() or {}).get("count") or 0
    )
    kept_blocked = int(
        (conn.execute(
            """
            SELECT COUNT(DISTINCT proactive_candidate_seed_id) AS count
            FROM ai_mesh_insights
            WHERE proactive_candidate_seed_id IS NOT NULL
              AND (why_not_json <> '[]'::jsonb OR missing_evidence_json <> '[]'::jsonb)
            """
        ).fetchone() or {}).get("count") or 0
    )
    return {
        "total_insights": total,
        "insights_by_type": by_type,
        "candidates_upgraded_by_ai": suggestions,
        "candidates_with_thesis_or_exit_suggestions": suggestions,
        "candidates_kept_blocked_count": kept_blocked,
    }


def _latest_run(conn: Any) -> dict[str, Any] | None:
    if not table_exists(conn, "ai_mesh_intelligence_runs"):
        return None
    row = conn.execute("SELECT * FROM ai_mesh_intelligence_runs ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
    return _json_safe(dict(row)) if row else None


def _latest_insights(conn: Any, *, limit: int, where: str = "true") -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT *
        FROM ai_mesh_insights
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_json_safe(dict(row)) for row in rows]


def _top_json_values(conn: Any, column: str, *, limit: int) -> list[str]:
    rows = conn.execute(
        f"""
        SELECT value, COUNT(*) AS count
        FROM ai_mesh_insights, LATERAL jsonb_array_elements_text({column}) AS value
        GROUP BY value
        ORDER BY count DESC, value
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [f"{row['value']}: {row['count']}" for row in rows]


def _latest_successful_insight(conn: Any) -> dict[str, Any] | None:
    if not table_exists(conn, "ai_mesh_insights"):
        return None
    row = conn.execute(
        """
        SELECT ai_mesh_insight_id, insight_type, market_id, side, model_provider, model_name,
               summary, recommended_mesh_action, created_at
        FROM ai_mesh_insights
        WHERE model_provider <> 'NONE'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    return _json_safe(dict(row)) if row else None


def _empty_summary(status: str, now: datetime, model_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "ai_enabled": False,
        "ai_mode": "ENABLED" if model_status.get("available") else "DEGRADED",
        "local_model_status": model_status,
        "provider_reachable": bool(model_status.get("available")),
        "local_model_list": model_status.get("models") or [],
        "call_budget": _call_budget(_config_from_env()),
        "total_insights": 0,
        "insights_by_type": {},
        "recent_insights": [],
        "ai_alerts": [],
        "ai_errors": [],
        "json_reliability_status": "UNKNOWN",
        "fast_json_model": model_status.get("fast_json_model"),
        "reasoning_model": model_status.get("reasoning_model"),
        "invalid_json_count": 0,
        "schema_invalid_count": 0,
        "repaired_json_count": 0,
        "fallback_count": 0,
        "valid_json_count": 0,
        "valid_json_rate": 0.0,
        "generated_at": now.isoformat(),
    }


def _run_status(*, model_available: bool, calls_attempted: int, calls_succeeded: int, insights_created: int, latest_error: str | None) -> str:
    if not insights_created and not model_available:
        return "AI_UNAVAILABLE"
    if calls_attempted and calls_succeeded == 0 and latest_error:
        return "PARTIAL"
    return "OK"


def _rate(numerator: int, denominator: int) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _json_reliability_status(latest_run: dict[str, Any] | None) -> str:
    if not latest_run:
        return "UNKNOWN"
    metadata = latest_run.get("metadata_json") if isinstance(latest_run, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    attempted = int(latest_run.get("calls_attempted") or 0)
    valid_rate = float(metadata.get("valid_json_rate") or 0)
    invalid = int(metadata.get("invalid_json_count") or 0)
    schema_invalid = int(metadata.get("schema_invalid_count") or 0)
    if not attempted:
        return "NO_MODEL_CALLS"
    if valid_rate >= 0.99 and invalid == 0 and schema_invalid == 0:
        return "RELIABLE"
    if valid_rate > 0:
        return "PARTIAL"
    return "UNRELIABLE"


def _ai_mode(model_status: dict[str, Any], config: AIMeshConfig, calls_succeeded: int, calls_timed_out: int) -> str:
    if not config.enabled:
        return "DISABLED"
    if not model_status.get("available"):
        return "DEGRADED"
    if calls_timed_out and not calls_succeeded:
        return "FAST_ONLY"
    return "ENABLED"


def _ai_error_type(error: str) -> str:
    upper = str(error or "").upper()
    if "AI_INVALID_JSON" in upper:
        return "AI_INVALID_JSON"
    if "AI_SCHEMA_INVALID" in upper:
        return "AI_SCHEMA_INVALID"
    if "TIMEOUT" in upper:
        return "TIMEOUT"
    return "MODEL_ERROR"


def _call_budget(config: AIMeshConfig) -> dict[str, Any]:
    return {
        "max_ai_calls_per_cycle": config.max_ai_calls,
        "max_reasoning_calls_per_cycle": config.max_reasoning_calls,
        "fast_timeout_seconds": config.fast_timeout_seconds,
        "reasoning_timeout_seconds": config.reasoning_timeout_seconds,
        "fast_num_predict": config.fast_num_predict,
        "reasoning_num_predict": config.reasoning_num_predict,
        "max_prompt_chars": config.max_prompt_chars,
        "cache_ttl_hours": config.cache_ttl_hours,
    }


def _candidate_task_kind(context: dict[str, Any]) -> str:
    if _upper(context.get("exit_state")) not in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}:
        return "EXIT"
    if _upper(context.get("thesis_state")) in {"THESIS_MISSING", "THESIS_WATCH", "UNKNOWN", ""}:
        return "THESIS"
    return "WHY_NOT"


def _skip_for_ai_hard_identity(context: dict[str, Any]) -> bool:
    if context.get("side") not in {"YES", "NO"}:
        return True
    if not context.get("market_id") or not context.get("token_id"):
        return True
    hard = {str(item).upper() for item in _list(context.get("hard_blockers")) + _list(context.get("policy_blockers"))}
    return bool(hard & {"TOKEN_MISMATCH", "MISSING_TOKEN", "MARKET_UNRESOLVED", "TOKEN_SIDE_CONFLICT"})


def _is_timeout_error(error: str) -> bool:
    return "TIMEOUT" in str(error or "").upper() or "READTIMEOUT" in str(error or "").upper()


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return int(ordered[index])


def _select_model(preferred: str | None, models: list[str]) -> str | None:
    if preferred and preferred in models:
        return preferred
    return models[0] if models else None


def _candidate_prompt(context: dict[str, Any], *, reasoning: bool = False, max_chars: int | None = None) -> str:
    return _bounded_prompt(_compact_candidate_prompt(context, reasoning=reasoning), max_chars or _config_from_env().max_prompt_chars)


def _event_prompt(context: dict[str, Any], *, max_chars: int | None = None) -> str:
    return _bounded_prompt(_compact_event_prompt(context), max_chars or _config_from_env().max_prompt_chars)


def _compact_candidate_prompt(context: dict[str, Any], *, reasoning: bool = False) -> str:
    compact = {
        "m": context.get("market_id"),
        "s": context.get("side"),
        "tok": bool(context.get("token_id")),
        "trig": context.get("trigger_type"),
        "edge": context.get("edge_state"),
        "thesis": context.get("thesis_state"),
        "score": context.get("opportunity_score"),
        "risk": context.get("risk_state"),
        "cap": context.get("capital_state"),
        "exit": context.get("exit_state"),
        "life": context.get("lifecycle_state"),
        "ob": context.get("orderbook_state"),
        "policy": context.get("policy_state"),
        "blockers": _short_list(context.get("policy_blockers"), limit=2, chars=40),
        "required": _short_list(context.get("required_to_pass"), limit=2, chars=60),
    }
    fields = (
        "summary,direction_hint,thesis_type,thesis_confidence,expected_hold_time_seconds,"
        "time_stop_seconds,invalidation_condition,missing_evidence,why_not,recommended_mesh_action,confidence"
        if reasoning
        else "summary,confidence"
    )
    mode = "thesis/exit" if reasoning else "fast"
    if not reasoning:
        return (
            'Return JSON only: {"summary":"watch reason <=8 words","confidence":0.0}. '
            "No markdown. No extra keys. Do not invent facts or ids. Advisory only. "
            f"ctx={json.dumps(_json_safe(compact), separators=(',', ':'), sort_keys=True)}"
        )
    return (
        "POLYBOT AI Mesh organ. Advisory only; never execution authority. "
        "Use only ctx; do not invent ids/sources/probabilities/prices. "
        f"Mode={mode}. Return compact JSON only with keys: {fields}. "
        f"ctx={json.dumps(_json_safe(compact), separators=(',', ':'), sort_keys=True)}"
    )


def _compact_event_prompt(context: dict[str, Any]) -> str:
    compact = {
        "source_event_id": context.get("source_event_id"),
        "type": context.get("source_type"),
        "text": str(context.get("summary") or context.get("title") or "")[:500],
    }
    return (
        "POLYBOT event AI organ. Advisory only. Do not invent market ids or facts. "
        "Return compact JSON only with keys: summary,entities,topics,confidence. "
        f"event={json.dumps(_json_safe(compact), separators=(',', ':'), sort_keys=True)}"
    )


def _json_benchmark_specs() -> list[tuple[str, str, str, int]]:
    event_prompt = (
        'Return JSON only. Schema {"summary":"short","entities":[],"topics":[],"confidence":0.0}. '
        'No prose. Do not invent facts. ctx={"event":"market relevant news"}'
    )
    trigger_prompt = (
        'Return JSON only. Schema {"summary":"short","direction_hint":"UNKNOWN","confidence":0.0}. '
        'No prose. Do not invent ids. ctx={"trigger":"MARKET_MOVEMENT","side":"YES"}'
    )
    thesis_prompt = (
        'Return JSON only. Schema {"status":"OK","thesis_type":"UNKNOWN","confidence":0.0,'
        '"direction_hint":"UNKNOWN","hold_time_seconds":0,"time_stop_seconds":0,'
        '"exit_logic":"short","invalidation":"short","missing_evidence":[],"why_not":[]}. '
        'No prose. Advisory only. ctx={"trigger":"PAYOUT_DISCREPANCY","thesis":"THESIS_MISSING"}'
    )
    hold_prompt = (
        'Return JSON only. Schema {"status":"OK","hold_time_seconds":0,"time_stop_seconds":0,'
        '"missing_evidence":[],"why_not":[],"confidence":0.0}. '
        'No prose. ctx={"trigger":"MARKET_MOVEMENT","exit":"EXIT_NOT_READY"}'
    )
    exit_prompt = (
        'Return JSON only. Schema {"status":"OK","exit_logic":"short","invalidation":"short",'
        '"time_stop_seconds":0,"missing_evidence":[],"why_not":[],"confidence":0.0}. '
        'No prose. ctx={"side":"NO","orderbook":"FRESH"}'
    )
    why_prompt = (
        'Return JSON only. Schema {"summary":"short","why_not":[],"missing_evidence":[],"confidence":0.0}. '
        'No prose. ctx={"blockers":["exit_not_ready"]}'
    )
    return [
        ("tiny_json", "PING", 'Return JSON only: {"status":"OK"}.', 24),
        ("event_classification", "EVENT", event_prompt, 72),
        ("trigger_interpretation", "WHY_NOT", trigger_prompt, 72),
        ("thesis_skeleton", "THESIS", thesis_prompt, 96),
        ("hold_time", "HOLD_TIME", hold_prompt, 72),
        ("exit_invalidation", "EXIT", exit_prompt, 72),
        ("why_not", "WHY_NOT", why_prompt, 72),
    ]


def _validate_ai_contract(payload: dict[str, Any], *, task: str | None) -> tuple[dict[str, Any], bool]:
    if not isinstance(payload, dict):
        raise ValueError("AI_SCHEMA_INVALID: payload was not an object")
    out = dict(payload)
    task_name = str(task or "WHY_NOT").upper()
    repaired = False

    def ensure(key: str, default: Any) -> None:
        nonlocal repaired
        if key not in out or out.get(key) is None:
            out[key] = default
            repaired = True

    ensure("summary", "AI advisory insight.")
    ensure("confidence", 0.0)
    out["confidence"] = _bounded(out.get("confidence"))
    if out.get("confidence") != payload.get("confidence"):
        repaired = True

    if task_name == "EVENT":
        ensure("entities", [])
        ensure("topics", [])
        out["entities"] = [str(item)[:80] for item in _list(out.get("entities"))[:8]]
        out["topics"] = [str(item)[:80] for item in _list(out.get("topics"))[:8]]
    else:
        ensure("why_not", [])
        ensure("missing_evidence", [])
        out["why_not"] = [str(item)[:120] for item in _list(out.get("why_not"))[:6]]
        out["missing_evidence"] = [str(item)[:120] for item in _list(out.get("missing_evidence"))[:6]]

    if task_name in {"THESIS", "EXIT", "HOLD_TIME"}:
        ensure("direction_hint", "UNKNOWN")
        ensure("thesis_type", "UNKNOWN")
        ensure("recommended_mesh_action", "WATCH_ONLY")
        raw_direction = str(out.get("direction_hint") or "").upper()
        raw_thesis = str(out.get("thesis_type") or "").upper()
        direction = _direction(out.get("direction_hint"))
        thesis_type = _thesis_type(out.get("thesis_type"))
        action = _mesh_action(out.get("recommended_mesh_action"))
        if direction != str(out.get("direction_hint") or "").upper():
            repaired = True
        if thesis_type != str(out.get("thesis_type") or "").upper():
            repaired = True
        if action != str(out.get("recommended_mesh_action") or "").upper():
            repaired = True
        out["direction_hint"] = direction
        out["thesis_type"] = thesis_type
        out["recommended_mesh_action"] = action
        out["thesis_confidence"] = _bounded(out.get("thesis_confidence", out.get("confidence")))
        if "hold_time_seconds" in out and "expected_hold_time_seconds" not in out:
            out["expected_hold_time_seconds"] = out.get("hold_time_seconds")
            repaired = True
        if "exit_logic" in out and "summary" not in payload:
            out["summary"] = str(out.get("exit_logic") or out.get("summary") or "")[:160]
            repaired = True
        if "invalidation" in out and "invalidation_condition" not in out:
            out["invalidation_condition"] = out.get("invalidation")
            repaired = True
        out["expected_hold_time_seconds"] = _int_or_none(out.get("expected_hold_time_seconds"))
        out["time_stop_seconds"] = _int_or_none(out.get("time_stop_seconds"))
        if task_name == "THESIS" and raw_thesis and raw_thesis not in {
            "MISPRICING_REVERSION",
            "MOMENTUM_CONTINUATION",
            "NEWS_REACTION",
            "EARLY_EXIT",
            "ORDERBOOK_PRESSURE",
            "PAYOUT_DISCREPANCY",
            "SIGNAL_QUALITY",
            "NO_VALID_THESIS",
            "UNKNOWN",
        }:
            raise ValueError("AI_SCHEMA_INVALID: critical thesis_type invalid")
    elif task_name in {"WHY_NOT", "PING"}:
        out["why_not"] = [str(item)[:120] for item in _list(out.get("why_not"))[:6]]

    out["_schema_valid"] = True
    out["_schema_repaired"] = repaired
    return out, repaired


def _deterministic_schema_fallback(task: str | None, error: str) -> dict[str, Any]:
    task_name = str(task or "WHY_NOT").upper()
    fallback = {
        "status": "WATCH",
        "summary": "Deterministic fallback: valid AI JSON unavailable.",
        "confidence": 0.0,
        "missing_evidence": ["valid_ai_json"],
        "why_not": [error[:160]],
        "generated_by": "DETERMINISTIC_FALLBACK",
        "is_execution_authority": False,
    }
    if task_name in {"THESIS", "EXIT", "HOLD_TIME"}:
        fallback.update(
            {
                "thesis_type": "NO_VALID_THESIS",
                "direction_hint": "UNKNOWN",
                "hold_time_seconds": 0,
                "time_stop_seconds": 0,
                "exit_logic": "valid AI exit unavailable",
                "invalidation": "valid AI invalidation unavailable",
            }
        )
    return fallback


def _config_from_env() -> AIMeshConfig:
    base_model = os.getenv("AI_MESH_OLLAMA_MODEL") or os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL
    fast_json_model = os.getenv("AI_FAST_JSON_MODEL") or os.getenv("AI_FAST_MODEL") or os.getenv("OLLAMA_MODEL_FAST") or base_model
    return AIMeshConfig(
        enabled=str(os.getenv("AI_MESH_ENABLED", "true")).lower() not in {"0", "false", "no"},
        max_ai_calls=max(0, int(os.getenv("AI_MAX_CALLS_PER_CYCLE") or os.getenv("AI_MESH_MAX_CALLS", "1") or "1")),
        max_reasoning_calls=max(0, int(os.getenv("AI_MAX_REASONING_CALLS_PER_CYCLE") or os.getenv("AI_MESH_MAX_REASONING_CALLS", "0") or "0")),
        fast_timeout_seconds=max(1.0, float(os.getenv("AI_FAST_TIMEOUT_SECONDS") or os.getenv("AI_MESH_FAST_TIMEOUT_SECONDS", "18") or "18")),
        reasoning_timeout_seconds=max(1.0, float(os.getenv("AI_REASONING_TIMEOUT_SECONDS") or os.getenv("AI_MESH_REASONING_TIMEOUT_SECONDS", "18") or "18")),
        max_prompt_chars=max(400, int(os.getenv("AI_MESH_MAX_PROMPT_CHARS", "700") or "700")),
        fast_num_predict=max(16, int(os.getenv("AI_NUM_PREDICT_FAST") or os.getenv("AI_MESH_NUM_PREDICT_FAST", "220") or "220")),
        reasoning_num_predict=max(16, int(os.getenv("AI_NUM_PREDICT_REASONING") or os.getenv("AI_MESH_NUM_PREDICT_REASONING", "140") or "140")),
        model_name=base_model,
        fast_json_model_name=fast_json_model,
        fast_model_name=fast_json_model,
        reasoning_model_name=os.getenv("AI_REASONING_MODEL") or os.getenv("OLLAMA_MODEL_REASONING") or base_model,
        cache_ttl_hours=max(1, int(os.getenv("AI_MESH_CACHE_TTL_HOURS", "6") or "6")),
    )


def _ollama_base_urls() -> list[str]:
    env = os.getenv("OLLAMA_BASE_URL")
    bases = [env] if env else []
    bases.extend(["http://host.docker.internal:11434", "http://ollama:11434", "http://localhost:11434"])
    out: list[str] = []
    for item in bases:
        if item and item.rstrip("/") not in out:
            out.append(item.rstrip("/"))
    return out


def _parse_json_object(text: str) -> dict[str, Any]:
    first_error = None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("AI_INVALID_JSON: response was not a JSON object")
    except Exception as first_exc:
        first_error = first_exc
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                if isinstance(parsed, dict):
                    parsed["_json_extracted"] = True
                    return parsed
            except Exception as extract_exc:
                raise ValueError(f"AI_INVALID_JSON: {extract_exc}") from extract_exc
    raise ValueError(f"AI_INVALID_JSON: {first_error}") from first_error


def _sql_params(insight: dict[str, Any]) -> dict[str, Any]:
    out = dict(insight)
    for key in (
        "entities_json",
        "topics_json",
        "related_markets_json",
        "missing_evidence_json",
        "supporting_evidence_ids_json",
        "contradicting_evidence_ids_json",
        "risk_notes_json",
        "why_not_json",
        "metadata_json",
    ):
        out[key] = Jsonb(_json_safe(out.get(key) or ([] if key.endswith("_json") and key != "metadata_json" else {})))
    return out


def _missing_from_context(context: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if _upper(context.get("thesis_state")) in {"THESIS_MISSING", "UNKNOWN", ""}:
        missing.append("supported_trade_thesis")
    if _upper(context.get("thesis_state")) == "THESIS_WATCH":
        missing.append("stronger_thesis_confirmation")
    if _upper(context.get("exit_state")) not in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}:
        missing.append("exit_or_time_stop")
    if context.get("side") not in {"YES", "NO"}:
        missing.append("side_clarity")
    if not context.get("token_id"):
        missing.append("token_id")
    return _dedupe([*missing, *_list(context.get("policy_blockers"))])


def _thesis_type_for_trigger(trigger_type: str) -> str:
    trigger = trigger_type.upper()
    if "PAYOUT" in trigger or "MISPRICING" in trigger:
        return "MISPRICING_REVERSION"
    if "MOMENTUM" in trigger or "MARKET_MOVEMENT" in trigger:
        return "MOMENTUM_CONTINUATION"
    if "NEWS" in trigger or "EVENT" in trigger:
        return "NEWS_REACTION"
    if "ORDERBOOK" in trigger:
        return "ORDERBOOK_PRESSURE"
    if "SIGNAL" in trigger:
        return "SIGNAL_QUALITY"
    return "UNKNOWN"


def _default_hold_seconds(trigger_type: str) -> int | None:
    trigger = trigger_type.upper()
    if "ORDERBOOK" in trigger:
        return 3 * 3600
    if "MOMENTUM" in trigger or "MARKET_MOVEMENT" in trigger:
        return 4 * 3600
    if "NEWS" in trigger:
        return 6 * 3600
    if "PAYOUT" in trigger or "MISPRICING" in trigger:
        return 48 * 3600
    if "EVENT_WINDOW" in trigger:
        return 12 * 3600
    return None


def _validated_related_markets(value: Any) -> list[Any]:
    # AI may propose semantic recall terms, but not canonical market ids.
    out: list[Any] = []
    for item in _list(value):
        if isinstance(item, dict):
            out.append({"query": str(item.get("query") or item.get("topic") or item.get("name") or "")[:120]})
        else:
            out.append({"query": str(item)[:120]})
    return [item for item in out if item.get("query")]


def _keywords(text: str) -> list[str]:
    words = []
    for raw in text.replace("/", " ").replace("-", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum()).strip()
        if len(word) >= 4 and word.lower() not in {"this", "that", "with", "from", "will", "market"}:
            words.append(word[:40])
    return _dedupe(words)[:12]


def _direction(value: Any) -> str:
    text = str(value or "UNKNOWN").upper()
    return text if text in {"YES", "NO", "NEUTRAL", "MIXED", "UNKNOWN"} else "UNKNOWN"


def _side(value: Any) -> str:
    text = str(value or "SIDE_UNKNOWN").upper()
    return text if text in {"YES", "NO", "SIDE_UNKNOWN"} else "SIDE_UNKNOWN"


def _thesis_type(value: Any) -> str:
    text = str(value or "UNKNOWN").upper()
    allowed = {
        "MISPRICING_REVERSION",
        "MOMENTUM_CONTINUATION",
        "NEWS_REACTION",
        "EARLY_EXIT",
        "ORDERBOOK_PRESSURE",
        "PAYOUT_DISCREPANCY",
        "SIGNAL_QUALITY",
        "NO_VALID_THESIS",
        "UNKNOWN",
    }
    return text if text in allowed else "UNKNOWN"


def _already_priced_in(value: Any) -> str:
    text = str(value or "NOT_EVALUATED").upper()
    return text if text in {"YES", "NO", "UNKNOWN", "NOT_EVALUATED"} else "UNKNOWN"


def _mesh_action(value: Any) -> str:
    text = str(value or "NO_ACTION").upper()
    allowed = {"REFRESH_MARKET", "CREATE_WATCH", "BUILD_THESIS", "RUN_DEEP_MESH", "WATCH_ONLY", "NO_ACTION"}
    return text if text in allowed else "NO_ACTION"


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [value] if value else []
    return [value]


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _bounded(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(float(value))
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value) if value is not None else ""
        if text and text not in out:
            out.append(text)
    return out


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple) or isinstance(value, set):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _bounded_prompt(prompt: str, max_chars: int) -> str:
    if len(prompt) <= max_chars:
        return prompt
    return prompt[: max(400, max_chars)]


def _short_list(value: Any, *, limit: int, chars: int) -> list[str]:
    return [str(item)[:chars] for item in _list(value)[:limit] if str(item)]


def _safe_url_label(url: str) -> str:
    if "host.docker.internal" in url:
        return "host.docker.internal"
    if "localhost" in url:
        return "localhost"
    if "ollama" in url:
        return "ollama"
    return "configured"
