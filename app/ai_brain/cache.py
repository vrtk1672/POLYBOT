from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.ai_brain.contracts import AITaskType, AIResponse, normalize_task_type
from app.ai_brain.redaction import redact_dict
from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_cache_repository import AICacheRepository


def stable_hash(value: Any) -> str:
    payload = json.dumps(redact_dict(value if isinstance(value, dict) else {"value": value}), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AICache:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: AICacheRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or AICacheRepository()

    def build_cache_key(
        self,
        *,
        task_type: AITaskType | str,
        market_id: str | None,
        input_hash: str,
        prompt_version_id: str | None,
        model_name: str | None,
        extra_hashes: dict[str, str | None] | None = None,
    ) -> str:
        task = normalize_task_type(task_type).value
        return stable_hash(
            {
                "task_type": task,
                "market_id": market_id,
                "input_hash": input_hash,
                "prompt_version_id": prompt_version_id,
                "model_name": model_name,
                "extra_hashes": extra_hashes or {},
            }
        )

    def get_cached_response(self, cache_key: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        try:
            with self._factory.connect() as conn:
                row = self._repository.get_cached_response(conn, cache_key)
                if row is not None:
                    self._repository.increment_hit(conn, cache_key)
                    conn.commit()
                return dict(row) if row else None
        except Exception:
            return None

    def store_cached_response(
        self,
        *,
        cache_key: str,
        request_hash: str,
        task_type: AITaskType | str,
        response: AIResponse | dict[str, Any],
        market_id: str | None = None,
        prompt_version_id: str | None = None,
        model_name: str | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._factory.enabled:
            return
        response_json = response.model_dump(mode="json") if isinstance(response, AIResponse) else dict(response)
        try:
            with self._factory.connect() as conn:
                self._repository.store_cached_response(
                    conn,
                    cache_key=cache_key,
                    request_hash=request_hash,
                    task_type=normalize_task_type(task_type).value,
                    market_id=market_id,
                    prompt_version_id=prompt_version_id,
                    model_name=model_name,
                    response_json=redact_dict(response_json),
                    confidence=response_json.get("confidence"),
                    expires_at=expires_at,
                    metadata=metadata,
                )
                conn.commit()
        except Exception:
            return

    def should_use_cache(self, task_type: AITaskType | str) -> bool:
        task = normalize_task_type(task_type)
        return task != AITaskType.CASE_FILE_BUILD

    def list_cache(self, *, task_type: str | None = None, market_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        try:
            with self._factory.connect() as conn:
                return [dict(row) for row in self._repository.list_cache(conn, task_type=task_type, market_id=market_id, limit=limit)]
        except Exception:
            return []

    def hit_rate(self) -> float:
        if not self._factory.enabled:
            return 0.0
        try:
            with self._factory.connect() as conn:
                return self._repository.cache_hit_rate(conn)
        except Exception:
            return 0.0


def is_expired(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at <= datetime.now(UTC)
