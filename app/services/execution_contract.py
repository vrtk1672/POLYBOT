from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(slots=True)
class ExecutionIntent:
    intent_id: str
    correlation_id: str
    market_id: str
    side: str
    order_type: str
    size: float
    price_limit: float | None
    reason_code: str
    reason_text: str
    risk_metadata: dict[str, object]
    source_context: dict[str, object]
    execution_mode: str
    backend_target: str
    created_at: datetime

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ExecutionIntent":
        created_at_raw = payload.get("created_at")
        if isinstance(created_at_raw, datetime):
            created_at = created_at_raw
        else:
            created_at = datetime.fromisoformat(str(created_at_raw))
        return cls(
            intent_id=str(payload["intent_id"]),
            correlation_id=str(payload["correlation_id"]),
            market_id=str(payload["market_id"]),
            side=str(payload["side"]),
            order_type=str(payload["order_type"]),
            size=float(payload["size"]),
            price_limit=float(payload["price_limit"]) if payload.get("price_limit") is not None else None,
            reason_code=str(payload["reason_code"]),
            reason_text=str(payload["reason_text"]),
            risk_metadata=dict(payload.get("risk_metadata") or {}),
            source_context=dict(payload.get("source_context") or {}),
            execution_mode=str(payload["execution_mode"]),
            backend_target=str(payload["backend_target"]),
            created_at=created_at,
        )


@dataclass(slots=True)
class ExecutionResult:
    intent_id: str
    correlation_id: str
    accepted: bool
    result_status: str
    filled_size: float
    avg_fill_price: float | None
    remaining_size: float
    external_order_id: str | None
    error_code: str | None
    error_text: str | None
    raw_result_json: dict[str, object]
    processed_at: datetime

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["processed_at"] = self.processed_at.isoformat()
        return payload


class ExecutionAdapter:
    def submit_intent(self, intent: ExecutionIntent) -> ExecutionResult:
        raise NotImplementedError
