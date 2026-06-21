from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from app.ai_brain.redaction import redact_dict, redact_text


@dataclass(slots=True)
class AIWorkerResult:
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    risk_flags: list[str] = field(default_factory=list)
    raw_output_redacted: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class LocalAIWorker:
    def __init__(
        self,
        *,
        transport: Callable[[str, str, dict[str, Any], int], dict[str, Any] | str] | None = None,
        available_models: list[str] | None = None,
    ) -> None:
        self._transport = transport
        self._available_models = available_models or ["qwen3:8b", "qwen3:14b", "deepseek-r1:14b"]
        self._last_error: str | None = None

    def is_available(self, model_name: str) -> bool:
        return self._transport is not None and model_name in self._available_models

    def generate_json(
        self,
        *,
        model_name: str,
        prompt: str,
        input_payload: dict[str, Any],
        timeout_seconds: int = 30,
    ) -> AIWorkerResult:
        if not self.is_available(model_name):
            self._last_error = f"local model unavailable: {model_name}"
            return AIWorkerResult(status="UNAVAILABLE", error_message=self._last_error)
        try:
            result = self._transport(model_name, redact_text(prompt) or "", redact_dict(input_payload), timeout_seconds)
        except TimeoutError:
            self._last_error = "local ai timeout"
            return AIWorkerResult(status="TIMEOUT", error_message=self._last_error)
        except Exception as exc:
            self._last_error = str(exc)
            return AIWorkerResult(status="FAILED", error_message="local ai call failed")

        try:
            parsed = json.loads(result) if isinstance(result, str) else dict(result)
        except (TypeError, ValueError) as exc:
            self._last_error = "invalid local ai json"
            return AIWorkerResult(status="FAILED", error_message=self._last_error, raw_output_redacted=redact_text(str(result)))
        output = redact_dict(parsed)
        return AIWorkerResult(
            status="COMPLETED",
            output=output,
            confidence=_confidence(output),
            risk_flags=[str(item) for item in output.get("risk_flags", [])] if isinstance(output.get("risk_flags"), list) else [],
            raw_output_redacted=redact_text(json.dumps(output, sort_keys=True, default=str)),
            input_tokens=_rough_tokens(prompt) + _rough_tokens(json.dumps(input_payload, default=str)),
            output_tokens=_rough_tokens(json.dumps(output, default=str)),
        )

    def health(self) -> dict[str, Any]:
        return {
            "status": "AVAILABLE" if self._transport is not None else "UNAVAILABLE",
            "available_models": self._available_models if self._transport is not None else [],
            "last_error": self._last_error,
        }


def _confidence(output: dict[str, Any]) -> float | None:
    value = output.get("confidence")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _rough_tokens(text: str) -> int:
    return max(1, int(len(text) / 4)) if text else 0
